import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents import ActionAgent, DataAgent, DecisionAgent, PlannerAgent
from app.gemini import GeminiClient, GeminiUnavailable
from app.main import ROOT, create_app
from app.models import ApprovalRequest, DomainError, WorkflowRequest


@pytest.fixture
def client(tmp_path):
    policy = tmp_path / "policies.json"
    policy.write_bytes((ROOT / "data/policies.json").read_bytes())
    with TestClient(create_app(tmp_path / "test.db", policy)) as c:
        yield c


def run(c, order="ORD-1001", intent="cancel", **kwargs):
    return c.post("/api/workflows", json={"order_id": order, "message": "Please process this request.", "intent": intent, **kwargs})


def review(c, wid, approve=True):
    return c.post(f"/api/workflows/{wid}/review", json={"approve": approve, "reviewer": "Test Reviewer", "note": "Verified evidence"})


EXPECTED = {
    "status": ["completed"] * 8,
    "cancel": ["pending_approval", "escalated", "escalated", "escalated", "completed", "pending_approval", "completed", "pending_approval"],
    "refund": ["escalated", "escalated", "pending_approval", "escalated", "pending_approval", "escalated", "completed", "escalated"],
    "auto": ["escalated"] * 8,
}


@pytest.mark.parametrize("intent,order,expected", [(intent, f"ORD-{1001+i}", state) for intent, states in EXPECTED.items() for i,state in enumerate(states)])
def test_business_scenarios(client, intent, order, expected):
    before = client.get(f"/api/orders/{order}").json()
    response = run(client, order, intent)
    assert response.status_code == 201
    w = response.json()
    assert w["status"] == expected
    assert client.get(f"/api/orders/{order}").json() == before  # planning never mutates
    assert len(w["events"]) == 5
    assert w["decision"]["policy_ids"][0] in {p["id"] for p in w["evidence"]}


def test_paid_cancel_approval_is_atomic_and_once(client):
    w = run(client).json()
    assert client.get("/api/orders/ORD-1001").json()["status"] == "processing"
    result = review(client, w["id"]).json()
    assert result["status"] == "completed"
    assert result["approval"]["approved"] == 1
    order = client.get("/api/orders/ORD-1001").json()
    assert (order["status"], order["payment_status"], order["version"]) == ("cancelled", "refunded", 2)
    assert client.get("/api/metrics").json()["refunds"] == 1
    assert review(client, w["id"]).status_code == 409
    assert client.get("/api/metrics").json()["refunds"] == 1
    events = [e["event"] for e in result["events"]]
    assert events.index("approval_granted") < events.index("tool_executed")


def test_unpaid_cancellation_has_no_refund(client):
    w = run(client, "ORD-1006").json()
    review(client, w["id"])
    assert client.get("/api/orders/ORD-1006").json()["payment_status"] == "unpaid"
    assert client.get("/api/metrics").json()["refunds"] == 0


def test_refund_preserves_delivered_status(client):
    w = run(client, "ORD-1003", "refund").json()
    assert review(client, w["id"]).status_code == 200
    o = client.get("/api/orders/ORD-1003").json()
    assert (o["status"], o["payment_status"]) == ("delivered", "refunded")
    repeat = run(client, "ORD-1003", "refund").json()
    assert repeat["decision"]["action"] == "reply"


def test_rejection_does_not_mutate(client):
    original = client.get("/api/orders/ORD-1001").json()
    w = run(client).json()
    assert review(client, w["id"], False).json()["status"] == "rejected"
    assert client.get("/api/orders/ORD-1001").json() == original
    assert review(client, w["id"]).status_code == 409


def test_two_pending_requests_cannot_double_refund(client):
    first, second = run(client).json(), run(client).json()
    review(client, first["id"])
    stale = review(client, second["id"]).json()
    assert stale["status"] == "escalated"
    assert stale["events"][-1]["event"] == "stale_approval_blocked"
    assert client.get("/api/metrics").json()["refunds"] == 1


def test_policy_change_invalidates_approval(client):
    w = run(client).json()
    path = client.app.state.service.index.path
    path.write_text(path.read_text() + "\n")
    assert review(client, w["id"]).json()["status"] == "escalated"
    assert client.get("/api/orders/ORD-1001").json()["status"] == "processing"


def test_request_key_deduplicates(client):
    a, b = run(client, request_key="same-key-123"), run(client, request_key="same-key-123")
    assert a.json()["id"] == b.json()["id"]
    assert client.get("/api/metrics").json()["workflows"] == 1
    assert run(client, "ORD-1002", request_key="same-key-123").status_code == 409


def test_unknown_order_and_workflow(client):
    assert run(client, "ORD-9999").status_code == 404
    assert client.get("/api/workflows/WF-missing").status_code == 404
    assert review(client, "WF-missing").status_code == 404


@pytest.mark.parametrize("payload", [
    {"order_id":"'; DROP TABLE orders;--", "message":"cancel"},
    {"order_id":"ORD-1001", "message":""},
    {"order_id":"ORD-1001", "message":"x"*2001},
    {"order_id":"ORD-1001", "message":"cancel", "intent":"delete_database"},
    {"order_id":"ORD-1001", "message":"cancel", "approved":True},
])
def test_input_validation(client, payload):
    assert client.post("/api/workflows",json=payload).status_code == 422


def test_cross_origin_and_bad_host_blocked(client):
    assert client.post("/api/workflows",json={"order_id":"ORD-1001","message":"cancel"},headers={"Origin":"https://attacker.example"}).status_code==403
    assert client.get("/api/health",headers={"Host":"attacker.example"}).status_code==400


def test_tools_require_permissions_and_approval(client):
    db = client.app.state.db
    with pytest.raises(DomainError):
        DataAgent().invoke("delete_orders", db, "ORD-1001")
    w = run(client).json()
    with pytest.raises(DomainError), db.connect(write=True) as conn:
        ActionAgent().execute(conn, w, w["snapshot"], w["decision"])


def test_persistence_after_app_restart(client):
    w = run(client).json()
    db_path = client.app.state.db.path
    with TestClient(create_app(db_path)) as restarted:
        assert restarted.get(f"/api/workflows/{w['id']}").json()["status"] == "pending_approval"
        assert restarted.get("/api/metrics").json()["workflows"] == 1


def test_concurrent_approvals_execute_once(client):
    service = client.app.state.service
    w = run(client).json()
    def approve():
        try:
            return service.review(w["id"],ApprovalRequest(approve=True,reviewer="Concurrent reviewer"))["status"]
        except DomainError as error:
            return error.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:approve(),range(2)))
    assert sorted(map(str,results)) == ["409","completed"]
    assert client.get("/api/metrics").json()["refunds"] == 1


@pytest.mark.parametrize("days,expected",[(0,"refund_order"),(7,"refund_order"),(7.001,"escalate"),(-1,"escalate")])
def test_refund_window_boundaries(client,days,expected):
    order=client.get("/api/orders/ORD-1003").json()
    at=datetime(2026,10,14,12,tzinfo=timezone.utc)
    order["delivered_at"]=(at-timedelta(days=days)).isoformat()
    decision=DecisionAgent().decide(order,"refund",client.app.state.service.index.load()[0],at=at)
    assert decision["action"]==expected


def test_failed_action_rolls_back_approval_and_order(client):
    w=run(client).json()
    service=client.app.state.service
    original=service.action.execute
    def fail_after_write(*args):
        original(*args)
        raise RuntimeError("Injected transaction failure")
    with patch.object(service.action,"execute",side_effect=fail_after_write), pytest.raises(RuntimeError):
        service.review(w["id"],ApprovalRequest(approve=True,reviewer="Reviewer"))
    state=client.get(f"/api/workflows/{w['id']}").json()
    assert state["status"]=="pending_approval" and state["approval"] is None
    assert client.get("/api/orders/ORD-1001").json()["status"]=="processing"
    assert client.get("/api/metrics").json()["refunds"]==0


def test_export_matches_persistent_record(client):
    w=run(client).json()
    r=client.get(f"/api/workflows/{w['id']}/export")
    assert r.status_code == 200
    exported = r.json()
    assert exported.pop("message_traces")[0]["workflow_id"] == w["id"]
    assert exported == w
    assert "attachment" in r.headers["content-disposition"]


def test_policy_search_ranks_relevant_document(client):
    docs=client.get("/api/policies",params={"q":"refund seven day window"}).json()
    assert docs[0]["id"]=="POL-REFUND"


def test_control_policy_is_always_in_workflow_evidence(client):
    result=run(client,intent="auto",message="cancellation refund seven day delivery order status tracking").json()
    assert result["intent"]=="unknown"
    assert "POL-CONTROL" in {p["id"] for p in result["evidence"]}


@pytest.mark.parametrize("message,expected",[("Cancel my order","cancel"),("I want my money back","refund"),("Where is my delivery?","status"),("Do not cancel my order","unknown"),("Cancel and refund it","unknown")])
def test_offline_planner_ambiguity(message,expected):
    assert PlannerAgent().infer_intent(message)==expected


def test_no_key_falls_back_honestly(client):
    client.app.state.service.gemini.key=""
    w=run(client,intent="auto",message="Cancel my order",use_gemini=True).json()
    assert w["mode"]=="offline_fallback"
    assert w["decision"]["warnings"] and w["status"]=="pending_approval"


def test_mocked_gemini_is_advisory(client):
    provider=client.app.state.service.gemini
    with patch.object(provider,"classify",return_value="cancel"),patch.object(provider,"explain",return_value="Approval is required under POL-CANCEL."):
        w=run(client,intent="auto",use_gemini=True).json()
    assert w["mode"]=="gemini_assisted" and w["status"]=="pending_approval"
    assert w["decision"]["ai_explanation"].startswith("Approval")
    assert client.get("/api/orders/ORD-1001").json()["status"]=="processing"


def test_provider_errors_are_redacted():
    provider=GeminiClient();provider.key="SENSITIVE_TEST_KEY"
    with patch("httpx.Client.post",side_effect=httpx.ConnectError("secret SENSITIVE_TEST_KEY")):
        with pytest.raises(GeminiUnavailable) as error: provider.classify("cancel")
    assert "SENSITIVE_TEST_KEY" not in str(error.value)


def test_gemini_invalid_json_and_intent_rejected():
    provider=GeminiClient();provider.key="fake"
    with patch.object(provider,"generate_json",return_value={"intent":"execute_shell"}):
        with pytest.raises(GeminiUnavailable): provider.classify("hello")


def test_static_ui_and_openapi(client):
    assert "OrchestraAI" in client.get("/").text
    assert client.get("/static/app.js").status_code==200
    assert "/api/workflows/{workflow_id}/review" in client.get("/openapi.json").json()["paths"]
