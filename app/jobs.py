"""Bounded local worker queue with persisted, resumable live event streams.

Job state and events survive a page reload. On process restart unfinished jobs
are marked interrupted; they are never silently re-executed. Use one server worker.
"""

import hashlib
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .models import DomainError
from .core.events import AgentCancelled

TERMINAL = {"done", "failed", "cancelled", "interrupted"}


JobCancelled = AgentCancelled


class JobManager:
    def __init__(self, db, service, pacing_seconds=0.8):
        self.db, self.service = db, service
        self.pacing = pacing_seconds
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agentflow")
        self.slots = threading.BoundedSemaphore(8)

    def initialize(self):
        with self.db.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
              workflow_id TEXT, request_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
              request_key TEXT UNIQUE, guided INTEGER NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0,
              error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS job_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
              kind TEXT NOT NULL, agent TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS job_event_order ON job_events(job_id,id);
            CREATE INDEX IF NOT EXISTS jobs_workflow ON jobs(workflow_id);
            """)
        with self.db.connect(write=True) as c:
            for row in c.execute(
                "SELECT id FROM jobs WHERE status IN ('queued','running')"
            ).fetchall():
                self._event(
                    c,
                    row["id"],
                    "interrupted",
                    "Orchestrator",
                    {
                        "message": "Server restarted before this job finished. Inspect workflow history before retrying."
                    },
                )
            c.execute(
                "UPDATE jobs SET status='interrupted',error='Server restarted; inspect history before retrying.' WHERE status IN ('queued','running')"
            )

    @staticmethod
    def stamp():
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def _event(self, c, jid, kind, agent, detail):
        c.execute(
            "INSERT INTO job_events(job_id,kind,agent,detail_json,created_at) VALUES(?,?,?,?,?)",
            (jid, kind, agent, json.dumps(detail), self.stamp()),
        )

    def emit(self, jid, kind, agent, detail):
        with self.db.connect(write=True) as c:
            self._event(c, jid, kind, agent, detail)

    def events(self, jid, after=0):
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM job_events WHERE job_id=? AND id>? ORDER BY id",
                (jid, after),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "job_id": jid,
                "kind": r["kind"],
                "agent": r["agent"],
                "detail": json.loads(r["detail_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get(self, jid):
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not row:
            raise DomainError("Job not found.", 404)
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result["events"] = self.events(jid)
        return result

    def for_workflow(self, wid):
        with self.db.connect() as c:
            ids = [
                r[0]
                for r in c.execute(
                    "SELECT id FROM jobs WHERE workflow_id=? ORDER BY rowid", (wid,)
                )
            ]
        return [self.get(jid) for jid in ids]

    def submit(self, kind, body, guided=True, workflow_id=None):
        payload = body.model_dump()
        hash_payload = dict(payload)
        if kind == "run" and not hash_payload.get("use_rag"):
            hash_payload.pop("use_rag", None)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "kind": kind,
                    "body": hash_payload,
                    "workflow_id": workflow_id,
                    "guided": guided,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        key = (
            ("run:" + body.request_key) if kind == "run" and body.request_key else None
        )
        if not self.slots.acquire(blocking=False):
            raise DomainError(
                "The local queue is full. Wait for an active run to finish.", 429
            )
        jid = "JOB-" + uuid.uuid4().hex[:12].upper()
        owns_slot = True
        try:
            existing = None
            with self.db.connect(write=True) as c:
                if key:
                    existing = c.execute(
                        "SELECT id,fingerprint FROM jobs WHERE request_key=?", (key,)
                    ).fetchone()
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise DomainError(
                            "Request key was used with different input.", 409
                        )
                else:
                    stamp = self.stamp()
                    c.execute(
                        "INSERT INTO jobs(id,kind,status,workflow_id,request_json,fingerprint,request_key,guided,created_at,updated_at) VALUES(?,?,'queued',?,?,?,?,?,?,?)",
                        (
                            jid,
                            kind,
                            workflow_id,
                            json.dumps(payload),
                            fingerprint,
                            key,
                            int(guided),
                            stamp,
                            stamp,
                        ),
                    )
                    self._event(
                        c,
                        jid,
                        "queued",
                        "Orchestrator",
                        {
                            "message": "Request accepted into the local worker queue.",
                            "kind": kind,
                        },
                    )
            if existing:
                self.slots.release()
                owns_slot = False
                return self.get(existing["id"])
            self.pool.submit(self._work, jid, kind, body, guided, workflow_id)
            owns_slot = False  # the worker releases the slot, even if this read fails
            return self.get(jid)
        except Exception:
            if owns_slot:
                self.slots.release()
            raise

    def stop(self, jid):
        with self.db.connect(write=True) as c:
            row = c.execute(
                "SELECT kind,status FROM jobs WHERE id=?", (jid,)
            ).fetchone()
            if not row:
                raise DomainError("Job not found.", 404)
            if row["kind"] != "run":
                raise DomainError("An approval transaction cannot be interrupted.", 409)
            if row["status"] in TERMINAL:
                raise DomainError("This job has already finished.", 409)
            c.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (jid,))
            self._event(
                c,
                jid,
                "stop_requested",
                "Orchestrator",
                {
                    "message": "Stop requested. It takes effect at the next agent boundary."
                },
            )
        return self.get(jid)

    def _cancel_check(self, jid):
        with self.db.connect() as c:
            if c.execute(
                "SELECT cancel_requested FROM jobs WHERE id=?", (jid,)
            ).fetchone()[0]:
                raise JobCancelled()

    def _finish(self, jid, status, detail, workflow_id=None):
        with self.db.connect(write=True) as c:
            c.execute(
                "UPDATE jobs SET status=?,workflow_id=COALESCE(?,workflow_id),error=?,updated_at=? WHERE id=?",
                (status, workflow_id, detail.get("error"), self.stamp(), jid),
            )
            self._event(c, jid, status, "Orchestrator", detail)

    def _work(self, jid, kind, body, guided, wid):
        try:
            with self.db.connect(write=True) as c:
                c.execute(
                    "UPDATE jobs SET status='running',updated_at=? WHERE id=?",
                    (self.stamp(), jid),
                )

            def progress(event, agent, detail):
                if kind == "run" and event in {"agent_started", "agent_completed"}:
                    self._cancel_check(jid)
                self.emit(
                    jid,
                    event,
                    agent,
                    {
                        **detail,
                        "presentation_delay_ms": (
                            int(self.pacing * 1000)
                            if guided and event == "agent_started"
                            else 0
                        ),
                    },
                )
                if guided and event == "agent_started":
                    time.sleep(self.pacing)
                    if kind == "run":
                        self._cancel_check(jid)

            if kind == "run":
                self._cancel_check(jid)
                result = self.service.create(body, progress=progress, job_id=jid)
                state = (
                    "waiting" if result["status"] == "pending_approval" else "skipped"
                )
                self.emit(
                    jid,
                    "agent_" + state,
                    "Action Agent",
                    {
                        "reason": (
                            "Waiting for human approval."
                            if state == "waiting"
                            else "No approved business mutation to execute."
                        )
                    },
                )
            else:
                result = self.service.review(wid, body, progress=progress, job_id=jid)
                executed = any(e["event"] == "tool_executed" for e in result["events"])
                if not executed:
                    self.emit(jid, "agent_skipped", "Action Agent", {"result": result["response"], "status": result["status"]})
            self._finish(
                jid,
                "done",
                {
                    "workflow_id": result["id"],
                    "workflow_status": result["status"],
                    "message": result["response"],
                },
                result["id"],
            )
        except JobCancelled:
            self._finish(
                jid,
                "cancelled",
                {
                    "message": "Stopped at an agent boundary. No business action was performed."
                },
            )
        except Exception as error:
            message = (
                error.message
                if isinstance(error, DomainError)
                else "Run failed. Review the server log and retry with a new request."
            )
            if not isinstance(error, DomainError):
                logging.exception("AgentFlow job %s failed", jid)
            self._finish(jid, "failed", {"error": message})
        finally:
            self.slots.release()

    def shutdown(self):
        self.pool.shutdown(wait=True, cancel_futures=False)
