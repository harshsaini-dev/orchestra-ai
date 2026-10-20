"""Existing AgentFlow role, preserved for Phase 2."""
from ..models import DomainError

class ActionAgent:
    name = "Action Agent"
    allowed_tools = {"cancel_order", "refund_order"}

    def execute(self, conn, workflow, order, decision):
        """Called only inside the approval transaction; checks approval itself too."""
        from ..database import now
        approval = conn.execute("SELECT approved FROM approvals WHERE workflow_id=?", (workflow["id"],)).fetchone()
        if not approval or approval["approved"] != 1:
            raise DomainError("A recorded human approval is required.", 403)
        action = decision["action"]
        if action not in self.allowed_tools:
            raise DomainError("Action is not in the execution allowlist.", 403)
        payment = "refunded" if decision["amount_paise"] else order["payment_status"]
        status = "cancelled" if action == "cancel_order" else order["status"]
        result = conn.execute("UPDATE orders SET status=?,payment_status=?,version=version+1 WHERE id=? AND version=?",
                              (status, payment, order["id"], order["version"]))
        if result.rowcount != 1:
            raise DomainError("Order changed. Submit a fresh workflow.", 409)
        if decision["amount_paise"]:
            conn.execute("INSERT INTO refunds(order_id,workflow_id,amount_paise,created_at) VALUES(?,?,?,?)",
                         (order["id"], workflow["id"], decision["amount_paise"], now()))
        return {"tool": action, "order_status": status, "payment_status": payment,
                "refund_paise": decision["amount_paise"], "simulation": True}
