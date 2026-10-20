"""O1/O2/O4: bus-routed workflow orchestration and transactional approvals."""
import hashlib
import json
import uuid
from contextlib import contextmanager

from .agents import PlannerAgent, DataAgent, RetrievalAgent, DecisionAgent, ActionAgent
from .agents.contracts import DataRequest, PolicyRequest, DecisionRequest, ReviewRequest
from .core.eligibility import evaluate_eligibility
from .core.events import AgentCancelled, AgentState
from .core.message_bus import MessageBus
from .core.trace_store import TraceStore
from .database import now
from .gemini import GeminiClient, GeminiUnavailable
from .models import DomainError, WorkflowRequest


class WorkflowService:
    def __init__(self, db, index, gemini=None):
        self.db, self.index = db, index
        self.gemini = gemini or GeminiClient()
        self.planner, self.data = PlannerAgent(), DataAgent()
        self.retriever, self.decider, self.action = RetrievalAgent(), DecisionAgent(), ActionAgent()
        self.rag = None
        self.traces = TraceStore(db)

    @contextmanager
    def execution(self, progress=None, job_id=None):
        trace_id = self.traces.create(job_id)
        def emit(kind, agent, detail):
            self.traces.append(trace_id, kind, agent, detail)
            if progress:
                progress(kind, agent, detail)
        bus = MessageBus(trace_id, emit)
        bus.register(self.planner.name, "plan", WorkflowRequest, self._plan)
        bus.register(self.data.name, "read_order", DataRequest, self._read_order)
        bus.register(self.retriever.name, "retrieve_policy", PolicyRequest, self._retrieve, retrieving=True)
        bus.register(self.decider.name, "evaluate", DecisionRequest, self._decide)
        bus.register(self.action.name, "review", ReviewRequest,
                     lambda payload: self._review_transaction(payload.workflow_id, payload.review))
        try:
            yield bus
        except Exception as error:
            self.traces.finish(trace_id, "cancelled" if isinstance(error, AgentCancelled) else "failed")
            raise

    def _plan(self, request):
        intent, mode, warnings = request.intent, "offline_rules", []
        if intent == "auto":
            intent = self.planner.infer_intent(request.message)
            if request.use_gemini:
                try:
                    intent = self.gemini.classify(request.message)
                    mode = "gemini_assisted"
                except GeminiUnavailable as error:
                    warnings.append(str(error))
                    mode = "offline_fallback"
        return {"intent": intent, "mode": mode, "warnings": warnings,
                "steps": ["read_order", "retrieve_policy", "evaluate", "approve_if_required", "execute_and_log"]}

    def _read_order(self, request):
        return {"tool": "get_order_status", "order": self.data.invoke("get_order_status", self.db, request.order_id)}

    def _retrieve(self, request):
        evidence, digest = self.retriever.retrieve(self.index, request.message, request.intent)
        retrieval = None
        if request.use_rag:
            if self.rag is None:
                raise DomainError("Document RAG is not configured.", 503)
            retrieval = self.rag.retrieve(request.message + " Operation: " + request.intent, scope="policy", top_k=4)
        return {"excerpts": evidence, "policy_hash": digest, "rag_retrieval": retrieval,
                "method": "BM25 lexical search + intent routing" if retrieval is None else
                "Chroma semantic retrieval for generation; BM25 + intent routing for governing action rules",
                "sources": [{"id": item["id"], "score": item["score"]} for item in evidence]}

    def _decide(self, payload):
        request, order, evidence = payload.request, payload.order, payload.evidence
        mode, warnings = payload.mode, list(payload.warnings)
        decision = self.decider.decide(order, payload.intent, evidence)
        if request.use_rag:
            decision["rag"] = self.rag.generate(request.message, payload.rag_retrieval,
                                                decision={"order": order, "decision": dict(decision)})
            mode = "gemini_rag"
        elif request.use_gemini:
            try:
                decision["ai_explanation"] = self.gemini.explain({"order": order, "decision": decision,
                    "policies": [{"id": item["id"], "text": item["text"]} for item in evidence]})
                mode = "gemini_assisted" if not warnings else "gemini_partial"
            except GeminiUnavailable as error:
                warnings.append(str(error))
                mode = "gemini_partial" if mode == "gemini_assisted" else "offline_fallback"
        decision["warnings"] = list(dict.fromkeys(warnings))
        return {"decision": decision, "mode": mode}

    def create(self, request, progress=None, job_id=None):
        payload = request.model_dump(exclude={"request_key"})
        if not request.use_rag:
            payload.pop("use_rag", None)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if request.request_key:
            existing = self._existing(request.request_key, fingerprint)
            if existing:
                return existing
        with self.execution(progress, job_id) as bus:
            plan = bus.request(self.planner.name, "plan", request.model_dump(),
                               purpose="Understand the task and plan the controlled workflow.")
            data = bus.request(self.data.name, "read_order", {"order_id": request.order_id},
                               purpose="Read the order through the allowlisted database tool.")
            bus.emit("tool_called", self.data.name, {"trace_id": bus.trace_id, "tool": "get_order_status", "order_id": request.order_id})
            policy = bus.request(self.retriever.name, "retrieve_policy", {"message": request.message,
                    "intent": plan["intent"], "use_rag": request.use_rag}, purpose="Retrieve governing policy evidence.")
            bus.emit("retrieval_done", self.retriever.name, {"trace_id": bus.trace_id, "sources": policy["sources"]})
            result = bus.request(self.decider.name, "evaluate", {"request": request.model_dump(),
                    "intent": plan["intent"], "order": data["order"], "evidence": policy["excerpts"],
                    "rag_retrieval": policy["rag_retrieval"], "mode": plan["mode"], "warnings": plan["warnings"]},
                    purpose="Apply deterministic business rules; model explanations are advisory.")
            decision, mode, order = result["decision"], result["mode"], data["order"]
            status = "pending_approval" if decision["requires_approval"] else "escalated" if decision["action"] == "escalate" else "completed"
            events = [(self.planner.name, "plan_created", plan), (self.data.name, "tool_result", data),
                      (self.retriever.name, "policies_retrieved", policy), (self.decider.name, "decision_made", decision),
                      ("Orchestrator", "workflow_" + status, {"status": status, "mode": mode, "trace_id": bus.trace_id})]
            workflow_id = "WF-" + uuid.uuid4().hex[:12].upper()
            with self.db.connect(write=True) as c:
                row = c.execute("SELECT id,request_hash FROM workflows WHERE request_key=?", (request.request_key,)).fetchone() if request.request_key else None
                if row:
                    if row["request_hash"] != fingerprint:
                        raise DomainError("Request key was already used with different input.", 409)
                    workflow_id = row["id"]
                else:
                    self._insert(c, workflow_id, request, fingerprint, order, plan["intent"], status,
                                 mode, decision, policy["excerpts"], policy["policy_hash"], events)
            bus.transition(self.action.name, AgentState.WAITING_APPROVAL if decision["requires_approval"] else AgentState.DONE)
            if decision["requires_approval"]:
                bus.emit("approval_requested", self.action.name, {"trace_id": bus.trace_id,
                         "workflow_id": workflow_id, "reason": "Human approval is required before any mutation."})
            self.traces.finish(bus.trace_id, "waiting_approval" if decision["requires_approval"] else "done", workflow_id)
            return self.db.workflow(workflow_id)

    def review(self, workflow_id, request, progress=None, job_id=None):
        if self.db.workflow(workflow_id) is None:
            raise DomainError("Workflow not found.", 404)
        with self.execution(progress, job_id) as bus:
            result = bus.request(self.action.name, "review", {"workflow_id": workflow_id, "review": request.model_dump()},
                                 purpose="Revalidate policy and state; commit the human decision atomically.")
            self.traces.finish(bus.trace_id, "done", workflow_id)
            # A completed review resolves the original approval checkpoint.
            with self.db.connect(write=True) as c:
                c.execute("UPDATE execution_traces SET status='done' WHERE workflow_id=? AND status='waiting_approval'", (workflow_id,))
            return result

    def _existing(self, key, fingerprint):
        with self.db.connect() as c:
            row = c.execute(
                "SELECT id,request_hash FROM workflows WHERE request_key=?", (key,)
            ).fetchone()
        if row:
            if row["request_hash"] != fingerprint:
                raise DomainError(
                    "Request key was already used with different input.", 409
                )
            return self.db.workflow(row["id"])
        return None

    def _insert(
        self,
        c,
        workflow_id,
        request,
        fingerprint,
        order,
        intent,
        status,
        mode,
        decision,
        evidence,
        digest,
        events,
    ):
        stamp = now()
        c.execute(
            "INSERT INTO workflows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                workflow_id,
                order["id"],
                status,
                intent,
                request.message,
                mode,
                json.dumps(decision),
                json.dumps(evidence),
                json.dumps(order),
                digest,
                decision["reason"],
                stamp,
                stamp,
                request.request_key,
                fingerprint,
            ),
        )
        for agent, event, detail in events:
            self.db.event(c, workflow_id, agent, event, detail)

    def _review_transaction(self, workflow_id, request):
        with self.db.connect(write=True) as c:
            row = c.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
            if not row:
                raise DomainError("Workflow not found.", 404)
            workflow = dict(row)
            if workflow["status"] != "pending_approval":
                raise DomainError(
                    "Only a pending workflow can be reviewed; this workflow was already resolved.",
                    409,
                )
            decision = json.loads(workflow["decision_json"])
            if not request.approve:
                c.execute(
                    "INSERT INTO approvals VALUES(?,?,?,?,?)",
                    (workflow_id, 0, request.reviewer, request.note, now()),
                )
                c.execute(
                    "UPDATE workflows SET status='rejected',response=?,updated_at=? WHERE id=?",
                    (
                        "The reviewer rejected the proposed action. The order was not changed.",
                        now(),
                        workflow_id,
                    ),
                )
                self.db.event(
                    c,
                    workflow_id,
                    "Human Reviewer",
                    "approval_rejected",
                    request.model_dump(),
                )
            else:
                order = dict(
                    c.execute(
                        "SELECT * FROM orders WHERE id=?", (workflow["order_id"],)
                    ).fetchone()
                )
                snapshot = json.loads(workflow["snapshot_json"])
                policies, digest = self.index.load()
                rechecked = evaluate_eligibility(order, workflow["intent"], policies)
                stale = (
                    order["version"] != snapshot["version"]
                    or digest != workflow["policy_hash"]
                    or rechecked["action"] != decision["action"]
                    or rechecked["amount_paise"] != decision["amount_paise"]
                    or not rechecked["requires_approval"]
                )
                if stale:
                    c.execute(
                        "UPDATE workflows SET status='escalated',response=?,updated_at=? WHERE id=?",
                        (
                            "Order, policy or eligibility changed. Action blocked; submit a fresh workflow.",
                            now(),
                            workflow_id,
                        ),
                    )
                    self.db.event(
                        c,
                        workflow_id,
                        "Orchestrator",
                        "stale_approval_blocked",
                        {
                            "reason": "State or policy changed",
                            "reviewer": request.reviewer,
                        },
                    )
                else:
                    c.execute(
                        "INSERT INTO approvals VALUES(?,?,?,?,?)",
                        (workflow_id, 1, request.reviewer, request.note, now()),
                    )
                    self.db.event(
                        c,
                        workflow_id,
                        "Human Reviewer",
                        "approval_granted",
                        request.model_dump(),
                    )
                    result = self.action.execute(c, workflow, order, decision)
                    self.db.event(
                        c, workflow_id, self.action.name, "tool_executed", result
                    )
                    message = (
                        "Cancellation completed."
                        if decision["action"] == "cancel_order"
                        else "Refund recorded."
                    )
                    if result["refund_paise"]:
                        message += f" Simulated refund: INR {result['refund_paise']/100:,.2f}. No real money was transferred."
                    c.execute(
                        "UPDATE workflows SET status='completed',response=?,updated_at=? WHERE id=?",
                        (message, now(), workflow_id),
                    )
                    self.db.event(
                        c,
                        workflow_id,
                        "Orchestrator",
                        "workflow_completed",
                        {"response": message},
                    )
        return self.db.workflow(workflow_id)
