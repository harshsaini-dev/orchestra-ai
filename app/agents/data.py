"""Existing AgentFlow role, preserved for Phase 2."""
from ..models import DomainError

class DataAgent:
    name = "Data Agent"
    allowed_tools = {"get_order_status"}

    def invoke(self, tool, db, order_id):
        if tool not in self.allowed_tools:
            raise DomainError("Tool is not permitted for this agent.", 403)
        order = db.order(order_id)
        if not order:
            raise DomainError("Order not found. Select one of the sample orders.", 404)
        return order
