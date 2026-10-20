"""Live queue persistence and approval safety tests; no external AI calls."""

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "jobs.db")
    app.state.jobs.pacing = 0
    with TestClient(app) as c:
        yield c


def submit(c, **kwargs):
    request = {
        "order_id": "ORD-1001",
        "intent": "cancel",
        "message": "Cancel my order.",
        **kwargs,
    }
    response = c.post("/api/jobs", json={"request": request, "guided": False})
    assert response.status_code == 202, response.text
    return response.json()


def finished(c, jid):
    for _ in range(200):
        result = c.get("/api/jobs/" + jid).json()
        if result["status"] in {"done", "failed", "cancelled", "interrupted"}:
            return result
        time.sleep(0.01)
    pytest.fail("Job did not reach a terminal state")


def test_event_sequence_reconnect_and_approval(client):
    job = finished(client, submit(client)["id"])
    assert job["status"] == "done"
    events = job["events"]
    assert [e["agent"] for e in events if e["kind"] == "agent_started"] == [
        "Planner Agent",
        "Data Agent",
        "Policy Agent",
        "Decision Agent",
    ]
    assert [e["kind"] for e in events][-2:] == ["agent_waiting", "done"]
    assert all(
        e["detail"]["duration_ms"] >= 0
        for e in events
        if e["kind"] == "agent_completed"
    )
    assert client.get("/api/orders/ORD-1001").json()["status"] == "processing"
    cursor = events[4]["id"]
    response = client.get(
        "/api/jobs/" + job["id"] + "/events", headers={"Last-Event-ID": str(cursor)}
    )
    streamed = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert streamed == [e for e in events if e["id"] > cursor]
    wid = job["workflow_id"]
    review = client.post(
        "/api/workflows/" + wid + "/review-job",
        json={
            "review": {"approve": True, "reviewer": "Test reviewer"},
            "guided": False,
        },
    )
    assert review.status_code == 202
    result = finished(client, review.json()["id"])
    assert result["status"] == "done"
    assert any(
        e["kind"] == "agent_completed" and e["agent"] == "Action Agent"
        for e in result["events"]
    )
    order = client.get("/api/orders/ORD-1001").json()
    assert (order["status"], order["payment_status"], order["version"]) == (
        "cancelled",
        "refunded",
        2,
    )
    assert len(client.get("/api/workflows/" + wid + "/jobs").json()) == 2
    audit = client.get("/api/workflows/" + wid + "/export").json()
    assert len(audit["execution_jobs"]) == 2
    assert audit["execution_jobs"][0]["events"] == events
    assert (
        client.post(
            "/api/workflows/" + wid + "/review-job",
            json={"review": {"approve": True, "reviewer": "Again"}},
        ).status_code
        == 409
    )
    assert client.get("/api/metrics").json()["refunds"] == 1


def test_job_idempotency_and_conflict(client):
    first = submit(client, request_key="idempotent-job-1")
    second = submit(client, request_key="idempotent-job-1")
    assert first["id"] == second["id"]
    assert finished(client, first["id"])["status"] == "done"
    conflict = client.post(
        "/api/jobs",
        json={
            "request": {
                "order_id": "ORD-1001",
                "intent": "status",
                "message": "Changed request.",
                "request_key": "idempotent-job-1",
            },
            "guided": False,
        },
    )
    assert conflict.status_code == 409
    assert client.get("/api/metrics").json()["workflows"] == 1


def test_real_progress_is_persisted_before_agent_finishes_and_stop(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = client.app.state.service.planner.infer_intent

    def blocked(message):
        entered.set()
        assert release.wait(5)
        return original(message)

    monkeypatch.setattr(client.app.state.service.planner, "infer_intent", blocked)
    try:
        job = submit(client, intent="auto")
        assert entered.wait(3)
        mid = client.get("/api/jobs/" + job["id"]).json()
        assert mid["status"] == "running"
        assert mid["events"][-1]["kind"] == "agent_started"
        assert mid["events"][-1]["agent"] == "Planner Agent"
        assert client.get("/api/metrics").json()["workflows"] == 0
        assert client.post("/api/jobs/" + job["id"] + "/stop").status_code == 200
    finally:
        release.set()
    end = finished(client, job["id"])
    assert end["status"] == "cancelled"
    assert client.get("/api/orders/ORD-1001").json()["version"] == 1
    assert client.get("/api/metrics").json()["workflows"] == 0


def test_failed_job_reports_domain_error(client):
    job = finished(client, submit(client, order_id="ORD-9999")["id"])
    assert job["status"] == "failed"
    assert "not found" in job["error"].lower()
    assert job["workflow_id"] is None
    assert client.get("/api/metrics").json()["workflows"] == 0


def test_live_review_rechecks_stale_order(client):
    one = finished(client, submit(client)["id"])
    two = finished(client, submit(client)["id"])

    def review(wid):
        r = client.post(
            "/api/workflows/" + wid + "/review-job",
            json={"review": {"approve": True, "reviewer": "Reviewer"}, "guided": False},
        )
        return finished(client, r.json()["id"])

    assert review(one["workflow_id"])["status"] == "done"
    result = review(two["workflow_id"])
    assert result["events"][-1]["detail"]["workflow_status"] == "escalated"
    assert any(e["kind"] == "agent_skipped" for e in result["events"])
    assert client.get("/api/metrics").json()["refunds"] == 1


def test_restart_preserves_trace_and_marks_orphaned_jobs(tmp_path):
    path = tmp_path / "persistent.db"
    with TestClient(create_app(path)) as first:
        job = finished(first, submit(first)["id"])
        with first.app.state.db.connect(write=True) as c:
            c.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
    with TestClient(create_app(path)) as second:
        saved = second.get("/api/jobs/" + job["id"]).json()
        assert saved["status"] == "interrupted"
        assert saved["events"][-1]["kind"] == "interrupted"
        assert len(saved["events"]) == len(job["events"]) + 1
        assert second.get("/api/metrics").json()["workflows"] == 1


def test_invalid_stream_cursor_and_unknown_job(client):
    job = finished(client, submit(client)["id"])
    assert (
        client.get(
            "/api/jobs/" + job["id"] + "/events", headers={"Last-Event-ID": "bad"}
        ).status_code
        == 400
    )
    assert client.get("/api/jobs/missing/events").status_code == 404
    assert client.get("/api/jobs/" + job["id"] + "/events?after=-1").status_code == 422
    assert client.post("/api/jobs/" + job["id"] + "/stop").status_code == 409


def test_queue_has_bounded_capacity_and_recovers(client, monkeypatch):
    release = threading.Event()
    original = client.app.state.service.planner.infer_intent

    def blocked(message):
        assert release.wait(5)
        return original(message)

    monkeypatch.setattr(client.app.state.service.planner, "infer_intent", blocked)
    try:
        accepted = [submit(client, intent="auto")["id"] for _ in range(8)]
        full = client.post(
            "/api/jobs",
            json={
                "request": {
                    "order_id": "ORD-1001",
                    "intent": "auto",
                    "message": "Cancel my order.",
                },
                "guided": False,
            },
        )
        assert full.status_code == 429
    finally:
        release.set()
    assert all(finished(client, jid)["status"] == "done" for jid in accepted)
    assert finished(client, submit(client)["id"])["status"] == "done"
