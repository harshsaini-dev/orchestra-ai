"""Bounded DAG executor reusing the Phase 2 typed bus and states."""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
from .store import pack, now
from .operations import analytics, active_policy, scan
from .policies import simulate, Rules
from ..core.message_bus import MessageBus
from ..core.events import AgentState


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: Literal["weekly", "qa", "scan", "refund", "inventory", "simulate"] = (
        "weekly"
    )
    question: str = Field(default="", max_length=2000)
    proposed: dict = Field(default_factory=dict)
    fail_once: bool = False


class StepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str


class Engine:
    def __init__(self, store):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orchestra")
        self.slots = threading.BoundedSemaphore(10)
        with store.tx() as s:
            from sqlalchemy import select
            from .store import Item

            for r in s.scalars(select(Item).where(Item.kind == "run")).all():
                if r.data["status"] in {"queued", "running"}:
                    r.data = {
                        **r.data,
                        "status": "interrupted",
                        "error": "Server restarted; mutations were not replayed",
                    }

    def submit(self, company, actor, body):
        if not self.slots.acquire(blocking=False):
            raise HTTPException(429, "Execution queue is full")
        try:
            with self.store.tx() as s:
                run = self.store.put(
                    s,
                    company,
                    "run",
                    {
                        "workflow": body.workflow,
                        "request": body.model_dump(),
                        "status": "queued",
                        "actor": actor,
                        "result": None,
                        "started": now(),
                    },
                )
                rid = run.id
                self.store.audit(
                    s,
                    company,
                    actor,
                    "run.submitted",
                    {"run": rid, "workflow": body.workflow},
                )
            self.pool.submit(self.execute, company, actor, rid, body)
            return {"id": rid, "status": "queued"}
        except Exception:
            self.slots.release()
            raise

    def execute(self, company, actor, rid, body):
        sequence = 0
        outputs = {}
        failed = False

        def emit(kind, agent, detail):
            nonlocal sequence
            sequence += 1
            with self.store.tx() as s:
                self.store.put(
                    s,
                    company,
                    "event",
                    {
                        "run_id": rid,
                        "seq": sequence,
                        "type": kind,
                        "agent": agent,
                        "detail": detail,
                        "at": now(),
                    },
                )

        bus = MessageBus(rid, emit)

        def data(_):
            nonlocal failed
            if body.fail_once and not failed:
                failed = True
                raise RuntimeError("Deterministic transient demonstration fault")
            with self.store.tx() as s:
                datasets = [pack(d) for d in self.store.items(company, "dataset", s)]
            outputs["datasets"] = datasets
            return analytics(datasets, weekly=body.workflow == "weekly")

        def enquiry(_):
            return self.store.answer(company, body.question)

        def policy(_):
            with self.store.tx() as s:
                p = pack(active_policy(self.store, s, company))
            if body.workflow == "simulate":
                return {
                    **simulate(
                        outputs["datasets"],
                        p["rules"],
                        Rules.model_validate(body.proposed).model_dump(),
                    ),
                    "current": p["rules"],
                    "proposed": Rules.model_validate(body.proposed).model_dump(),
                    "source_document": p["source_document"],
                    "policy_version": p["version"],
                }
            return scan(self.store, company, actor)

        def task(_):
            issues = self.store.items(company, "issue")
            selected = [
                i
                for i in issues
                if i["status"] == "open"
                and (body.workflow == "scan" or i["code"] == body.workflow)
            ]
            return {
                "proposals": selected,
                "requires_approval": bool([i for i in selected if i["action"]]),
                "note": "Use Issues to review. No business mutation has occurred.",
            }

        def report(_):
            content = outputs.get("Policy", outputs.get("Data", {}))
            with self.store.tx() as s:
                r = self.store.put(
                    s,
                    company,
                    "report",
                    {
                        "title": "Policy impact report"
                        if body.workflow == "simulate"
                        else "Weekly sales report",
                        "content": content,
                        "run": rid,
                        "status": "draft",
                    },
                )
            return {"report_id": r.id, "content": content}

        def auditor(_):
            if body.workflow == "qa":
                source = outputs["Enquiry"]
                docs = {d["id"]: d for d in self.store.items(company, "document")}
                valid = all(
                    c["document_id"] in docs
                    and any(
                        x["key"] == c["key"] and x["text"] == c["text"]
                        for x in docs[c["document_id"]]["chunks"]
                    )
                    for c in source["citations"]
                )
                if not valid:
                    raise RuntimeError("Citation verification failed")
                return {
                    "verified": True,
                    "citation_count": len(source["citations"]),
                    "answer_supported": not source["abstained"],
                }
            if body.workflow in {"weekly", "simulate"}:
                result = outputs["Report"]
                if body.workflow == "weekly":
                    expected = analytics(outputs["datasets"], weekly=True)
                    if expected != result["content"]:
                        raise RuntimeError("Report total mismatch")
                with self.store.tx() as s:
                    r = self.store.get(s, company, result["report_id"], "report")
                    r.data = {**r.data, "status": "published", "audited": True}
                    r.version += 1
                return {"verified": True, "report_id": result["report_id"]}
            return {
                "verified": True,
                "check": "Proposals only; no financial or inventory writes",
            }

        def notification(_):
            with self.store.tx() as s:
                n = self.store.put(
                    s,
                    company,
                    "notification",
                    {
                        "title": body.workflow.title() + " completed",
                        "run": rid,
                        "channel": "internal inbox",
                        "read": False,
                    },
                )
            return {
                "notification_id": n.id,
                "channel": "internal inbox",
                "external_sent": False,
            }

        handlers = {
            "Data": data,
            "Enquiry": enquiry,
            "Policy": policy,
            "Task": task,
            "Report": report,
            "Auditor": auditor,
            "Notification": notification,
        }
        dags = {
            "weekly": ["Data", "Report", "Auditor", "Notification"],
            "qa": ["Enquiry", "Auditor"],
            "scan": ["Data", "Policy", "Task", "Auditor"],
            "refund": ["Data", "Policy", "Task", "Auditor"],
            "inventory": ["Data", "Policy", "Task", "Auditor"],
            "simulate": ["Data", "Policy", "Report", "Auditor", "Notification"],
        }
        try:
            with self.store.tx() as s:
                run = self.store.get(s, company, rid, "run")
                run.data = {**run.data, "status": "running", "dag": dags[body.workflow]}
            emit("run_started", "Orchestrator", {"dag": dags[body.workflow]})
            for agent in dags[body.workflow]:
                bus.register(
                    agent,
                    "execute",
                    StepInput,
                    handlers[agent],
                    retrieving=agent in {"Enquiry", "Policy"},
                )
                try:
                    outputs[agent] = bus.request(
                        agent, "execute", {"run_id": rid}, purpose=body.workflow
                    )
                except RuntimeError:
                    if agent != "Data" or not body.fail_once or not failed:
                        raise
                    bus.transition(agent, AgentState.RECOVERING)
                    emit(
                        "retry",
                        "Orchestrator",
                        {
                            "agent": agent,
                            "attempt": 2,
                            "reason": "Injected fail-once read fault",
                        },
                    )
                    outputs[agent] = bus.request(
                        agent, "execute", {"run_id": rid}, purpose=body.workflow
                    )
            result = {k: v for k, v in outputs.items() if k != "datasets"}
            emit("run_done", "Orchestrator", {"result": result})
            with self.store.tx() as s:
                run = self.store.get(s, company, rid, "run")
                run.data = {
                    **run.data,
                    "status": "done",
                    "result": result,
                    "finished": now(),
                }
                self.store.audit(
                    s,
                    company,
                    actor,
                    "run.completed",
                    {"run": rid, "retry_recovered": failed},
                )
        except Exception as error:
            import logging

            logging.getLogger(__name__).exception("Run %s failed", rid)
            emit("run_error", "Orchestrator", {"message": "Execution stopped safely"})
            with self.store.tx() as s:
                run = self.store.get(s, company, rid, "run")
                run.data = {
                    **run.data,
                    "status": "error",
                    "error": error.detail
                    if isinstance(error, HTTPException)
                    else "Agent failed; check inputs and server log",
                    "finished": now(),
                }
        finally:
            self.slots.release()

    def shutdown(self):
        self.pool.shutdown(wait=True, cancel_futures=False)
