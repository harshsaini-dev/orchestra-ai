"""O2/O4: durable event records, including validated bus envelopes."""
import json
from uuid import uuid4

from ..database import now
from ..models import DomainError


class TraceStore:
    def __init__(self, db):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS execution_traces (
                id TEXT PRIMARY KEY, workflow_id TEXT REFERENCES workflows(id),
                job_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL REFERENCES execution_traces(id),
                kind TEXT NOT NULL, agent TEXT NOT NULL,
                detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS trace_event_order ON trace_events(trace_id,id);
            CREATE INDEX IF NOT EXISTS trace_workflow ON execution_traces(workflow_id);
            """)
        # Trace records are evidence, never a durable queue to replay mutations from.
        with self.db.connect(write=True) as c:
            c.execute("UPDATE execution_traces SET status='interrupted' WHERE status='running'")

    def create(self, job_id: str | None = None) -> str:
        trace_id = "TRACE-" + uuid4().hex
        with self.db.connect(write=True) as c:
            c.execute("INSERT INTO execution_traces VALUES(?,NULL,?,'running',?)",
                      (trace_id, job_id, now()))
        return trace_id

    def append(self, trace_id: str, kind: str, agent: str, detail: dict) -> None:
        with self.db.connect(write=True) as c:
            c.execute("INSERT INTO trace_events(trace_id,kind,agent,detail_json,created_at) VALUES(?,?,?,?,?)",
                      (trace_id, kind, agent, json.dumps(detail, allow_nan=False), now()))

    def finish(self, trace_id: str, status: str, workflow_id: str | None = None) -> None:
        with self.db.connect(write=True) as c:
            c.execute("UPDATE execution_traces SET status=?,workflow_id=COALESCE(?,workflow_id) WHERE id=?",
                      (status, workflow_id, trace_id))

    def get(self, trace_id: str) -> dict:
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM execution_traces WHERE id=?", (trace_id,)).fetchone()
            if row is None:
                raise DomainError("Trace not found.", 404)
            events = c.execute("SELECT * FROM trace_events WHERE trace_id=? ORDER BY id", (trace_id,)).fetchall()
        return {**dict(row), "events": [{**dict(e), "detail": json.loads(e["detail_json"])} for e in events]}

    def for_workflow(self, workflow_id: str) -> list[dict]:
        with self.db.connect() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM execution_traces WHERE workflow_id=? ORDER BY rowid", (workflow_id,))]
        return [self.get(trace_id) for trace_id in ids]
