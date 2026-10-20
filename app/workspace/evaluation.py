"""Small transparent golden benchmark; scores describe this fixture only."""

import statistics
import time
from .retrieval import retrieve, answer
from .policies import Rules, decide
from ..core.message_bus import MessageBus
from ..core.events import AgentState
from .engine import StepInput

GOLDEN = [
    ("refund manager approval 5000", "Refund approvals"),
    ("discount Gold percent", "Discount control"),
    ("inventory stock forecast demand", "Inventory planning"),
    ("invoice overdue escalation", "Invoice escalation"),
    ("leave notice days", "Leave and notice"),
]


def evaluate_workspace(store, company):
    docs = store.items(company, "document")
    rows = []
    latencies = []
    valid = 0
    citation_count = 0
    for question, section in GOLDEN:
        started = time.perf_counter()
        hits = retrieve(docs, question, 5)
        result = answer(docs, question)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        found = any(h["section"] == section for h in hits)
        for cite in result["citations"]:
            citation_count += 1
            valid += any(
                d["id"] == cite["document_id"]
                and any(
                    c["key"] == cite["key"] and c["text"] == cite["text"]
                    for c in d["chunks"]
                )
                for d in docs
            )
        rows.append(
            {
                "question": question,
                "expected_section": section,
                "hit_at_5": found,
                "latency_ms": round(elapsed, 3),
                "abstained": result["abstained"],
            }
        )
    cases = [
        ("refund", {"amount": 5000}, False),
        ("refund", {"amount": 5001}, True),
        ("discount", {"discount": 20, "tier": "Gold"}, False),
        ("discount", {"discount": 16, "tier": "Standard"}, True),
        ("inventory", {"stock": 20, "demand30": 100}, False),
        ("inventory", {"stock": 19, "demand30": 100}, True),
        ("overdue", {"overdue_days": 30}, False),
        ("overdue", {"overdue_days": 31}, True),
        ("leave", {"days": 4, "notice_days": 6}, True),
        ("leave", {"days": 3, "notice_days": 0}, False),
    ]
    correct = sum(
        decide(kind, row, Rules().model_dump())["flagged"] == expected
        for kind, row, expected in cases
    )
    events = []
    attempts = 0

    def read(_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Injected")
        return {"ok": True}

    bus = MessageBus(
        "evaluation-recovery", lambda kind, agent, detail: events.append(kind)
    )
    bus.register("Data", "read", StepInput, read)
    try:
        bus.request(
            "Data", "read", {"run_id": "benchmark"}, purpose="Recovery benchmark"
        )
    except RuntimeError:
        bus.transition("Data", AgentState.RECOVERING)
    recovered = bus.request("Data", "read", {"run_id": "benchmark"}, purpose="Retry")[
        "ok"
    ]
    unknown = answer(docs, "quantum penguin teleportation quaternion")
    return {
        "benchmark": "SME handbook golden fixture v1",
        "questions": rows,
        "hit_at_5": sum(r["hit_at_5"] for r in rows) / len(rows),
        "citation_validity": valid / citation_count if citation_count else None,
        "citations_checked": citation_count,
        "policy_accuracy": correct / len(cases),
        "policy_cases": len(cases),
        "latency_median_ms": round(statistics.median(latencies), 3),
        "latency_max_ms": round(max(latencies), 3),
        "retry_success": int(recovered),
        "retry_trials": 1,
        "retry_attempts": attempts,
        "unsupported_question_abstained": unknown["abstained"],
        "scope": "Five known demo sections and ten fixed default-rule boundary cases. Citation validity checks source existence and exact passage, not semantic entailment. Retry is one injected read fault; not production reliability.",
    }
