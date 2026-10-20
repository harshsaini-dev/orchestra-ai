"""Self-contained offline demo; uses a temporary database, not dashboard data."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from app.database import Database
from app.main import ROOT
from app.models import ApprovalRequest, WorkflowRequest
from app.retrieval import PolicyIndex
from app.service import WorkflowService


def main():
    with TemporaryDirectory() as directory:
        db=Database(Path(directory)/"demo.db");db.initialize()
        service=WorkflowService(db,PolicyIndex(ROOT/"data/policies.json"))
        w=service.create(WorkflowRequest(order_id="ORD-1001",message="My order is delayed. Please cancel it.",intent="cancel"))
        print("1. Workflow created:",w["id"],w["status"])
        print("2. Decision:",w["response"])
        print("3. Before approval:",db.order("ORD-1001")["status"])
        w=service.review(w["id"],ApprovalRequest(approve=True,reviewer="Demo Reviewer"))
        print("4. After approval:",w["response"])
        print("5. Audit events:")
        for e in w["events"]:print("  ",e["agent"],"->",e["event"])
        print("6. Final order:",json.dumps(db.order("ORD-1001"),indent=2))
        print("Demo completed. Temporary data has been discarded.")


if __name__=="__main__":main()
