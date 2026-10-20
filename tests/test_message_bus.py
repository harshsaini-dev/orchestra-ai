"""O1/O2/O4: execution evidence and dispatch boundaries, without model calls."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.events import AgentMessage, AgentState, StateMachine, AgentCancelled
from app.core.message_bus import MessageBus
from app.main import create_app
from app.models import DomainError, WorkflowRequest


class NumberPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    number: int


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "bus.db")
    app.state.jobs.pacing = 0
    with TestClient(app) as client:
        yield client


def test_dispatch_is_validated_and_persisted_before_work():
    events = []
    def handler(payload):
        assert events[0][0] == "message_sent"
        assert events[0][2]["payload"] == {"number": 3}
        assert events[-1][0] == "agent_started"
        return {"answer": payload.number * 2}
    bus = MessageBus("test-trace", lambda *event: events.append(event))
    bus.register("Data", "double", NumberPayload, handler)
    assert bus.request("Data", "double", {"number": 3}, purpose="Calculate") == {"answer": 6}
    messages = [AgentMessage.model_validate(e[2]) for e in events if e[0] == "message_sent"]
    assert messages[1].causation_id == messages[0].id
    assert messages[1].step_id == messages[0].step_id
    assert (messages[0].sender, messages[1].recipient) == ("Orchestrator", "Orchestrator")
    assert bus.states["Data"].state == AgentState.DONE


@pytest.mark.parametrize("payload", [{"number":"3"}, {"number":3,"execute":True}, {}, {"number":None}])
def test_bad_payload_never_dispatches(payload):
    events, calls = [], []
    bus = MessageBus("trace", lambda *event: events.append(event))
    bus.register("Data", "calculate", NumberPayload, lambda value: calls.append(value))
    with pytest.raises(ValidationError):
        bus.request("Data", "calculate", payload, purpose="test")
    assert calls == [] and events == []


def test_unknown_recipient_cannot_invoke_a_tool():
    bus = MessageBus("trace", lambda *event: None)
    with pytest.raises(DomainError, match="permitted"):
        bus.request("Shell", "exec", {"command":"anything"}, purpose="test")


def test_failure_is_redacted_and_state_is_error():
    events=[]
    def fail(payload):
        raise RuntimeError("SECRET_PROVIDER_KEY")
    bus=MessageBus("trace",lambda *event:events.append(event))
    bus.register("Data","calculate",NumberPayload,fail)
    with pytest.raises(RuntimeError):
        bus.request("Data","calculate",{"number":1},purpose="test")
    assert bus.states["Data"].state == AgentState.ERROR
    assert "SECRET_PROVIDER_KEY" not in json.dumps(events)
    assert not any(e[0] == "agent_completed" for e in events)


def test_cancelled_start_does_not_execute_handler():
    calls=[]
    def emit(kind,agent,detail):
        if kind == "agent_started":
            raise AgentCancelled()
    bus=MessageBus("trace",emit)
    bus.register("Data","calculate",NumberPayload,lambda value:calls.append(value))
    with pytest.raises(AgentCancelled):
        bus.request("Data","calculate",{"number":1},purpose="test")
    assert not calls
    assert bus.states["Data"].state == AgentState.CANCELLED


def test_state_machine_enforces_recovery_and_terminal_boundaries():
    state=StateMachine()
    with pytest.raises(ValueError):
        state.transition(AgentState.WORKING)
    for target in (AgentState.THINKING,AgentState.RETRIEVING,AgentState.ERROR,AgentState.RECOVERING,
                   AgentState.THINKING,AgentState.WORKING,AgentState.WAITING_APPROVAL,
                   AgentState.THINKING,AgentState.WORKING,AgentState.DONE):
        state.transition(target)
    with pytest.raises(ValueError):
        state.transition(AgentState.THINKING)


def test_sync_workflow_has_real_durable_messages_and_atomic_review(client):
    run=client.post('/api/workflows',json={"order_id":"ORD-1001","intent":"cancel","message":"Cancel this order."}).json()
    trace=client.get(f'/api/workflows/{run["id"]}/traces').json()[0]
    assert trace['status']=='waiting_approval'
    messages=[e['detail'] for e in trace['events'] if e['kind']=='message_sent']
    requests=[m for m in messages if m['from']=='Orchestrator']
    assert [m['to'] for m in requests]==['Planner Agent','Data Agent','Policy Agent','Decision Agent']
    assert len(messages)==8
    assert len({m['trace_id'] for m in messages})==1
    assert all(AgentMessage.model_validate(message) for message in messages)
    assert client.get('/api/orders/ORD-1001').json()['version']==1
    reviewed=client.post(f'/api/workflows/{run["id"]}/review',json={"approve":True,"reviewer":"Test reviewer"})
    assert reviewed.status_code==200
    traces=client.get(f'/api/workflows/{run["id"]}/traces').json()
    assert len(traces)==2 and all(t['status']=='done' for t in traces)
    assert traces[1]['events'][0]['detail']['to']=='Action Agent'
    assert client.get('/api/orders/ORD-1001').json()['version']==2
    assert client.get('/api/traces/not-found').status_code==404


def test_concurrent_workflows_have_independent_state_and_trace_ids(client):
    service=client.app.state.service
    def create(number):
        return service.create(WorkflowRequest(order_id='ORD-1001',intent='status',message='Where is my order?',request_key=f'concurrent-{number}'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(create,range(6)))
    traces=[service.traces.for_workflow(result['id'])[0] for result in results]
    assert len({t['id'] for t in traces})==6
    assert all(t['status']=='done' for t in traces)
    assert all(len([e for e in t['events'] if e['kind']=='agent_completed'])==4 for t in traces)


def test_failed_lookup_preserves_data_agent_error_trace(client):
    assert client.post('/api/workflows',json={"order_id":"ORD-9999","intent":"status","message":"Where is my order?"}).status_code==404
    with client.app.state.db.connect() as c:
        row=c.execute('SELECT id,status FROM execution_traces').fetchone()
    assert row['status']=='failed'
    trace=client.get('/api/traces/'+row['id']).json()
    assert trace['events'][-1]['kind']=='error'
    assert trace['events'][-1]['agent']=='Data Agent'
    assert client.get('/api/metrics').json()['refunds']==0


def test_traces_survive_restart_and_replay_does_not_repeat_actions(tmp_path):
    path=tmp_path/'persist.db'
    with TestClient(create_app(path)) as first:
        run=first.post('/api/workflows',json={"order_id":"ORD-1001","intent":"cancel","message":"Cancel my order."}).json()
        first.post(f'/api/workflows/{run["id"]}/review',json={"approve":True,"reviewer":"Reviewer"})
        before=first.get(f'/api/workflows/{run["id"]}/traces').json()
    with TestClient(create_app(path)) as second:
        for _ in range(3):
            assert second.get(f'/api/workflows/{run["id"]}/traces').json()==before
        assert second.get('/api/metrics').json()['refunds']==1
        assert second.get('/api/orders/ORD-1001').json()['version']==2
