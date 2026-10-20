"""O4 shared pure rules; no agent dispatch or side effects."""
from datetime import datetime, timezone

def evaluate_eligibility(order, intent, evidence, at=None):
    at = at or datetime.now(timezone.utc)
    policies = {p["id"]: p for p in evidence}
    decision = {"action": "none", "eligible": False, "requires_approval": False,
                "policy_ids": [], "reason": "", "amount_paise": 0}

    def finish(action, reason, policy, eligible=False, amount=0):
        decision.update(action=action, reason=reason, policy_ids=[policy], eligible=eligible,
                        requires_approval=action in {"cancel_order", "refund_order"}, amount_paise=amount)
        return decision

    if intent == "status":
        late = order["status"] in {"processing", "shipped"} and datetime.fromisoformat(order["due_at"]) < at
        delay = " Its expected delivery date has passed." if late else ""
        return finish("reply", f"Order {order['id']} is {order['status']}; payment is {order['payment_status']}.{delay}", "POL-STATUS", True)
    if intent == "cancel":
        if order["status"] == "cancelled":
            return finish("reply", "This order is already cancelled. No further cancellation is needed.", "POL-CANCEL", True)
        policy = policies.get("POL-CANCEL")
        if not policy:
            return finish("escalate", "Governing cancellation policy was not retrieved.", "POL-CONTROL")
        if order["status"] not in policy["allowed_statuses"]:
            return finish("escalate", "Cancellation is only permitted before shipment. Manual review is required.", "POL-CANCEL")
        amount = order["amount_paise"] if order["payment_status"] == "paid" else 0
        return finish("cancel_order", "Eligible for cancellation before shipment. Human approval is required" + (" for cancellation and a full simulated refund." if amount else "; no refund is due for this unpaid order."), "POL-CANCEL", True, amount)
    if intent == "refund":
        if order["payment_status"] == "refunded":
            return finish("reply", "This order has already been refunded. A second refund is blocked.", "POL-REFUND", True)
        if order["payment_status"] != "paid":
            return finish("escalate", "No captured payment exists for this order. A refund cannot be issued.", "POL-REFUND")
        policy = policies.get("POL-REFUND")
        if not policy:
            return finish("escalate", "Governing refund policy was not retrieved.", "POL-CONTROL")
        eligible = order["status"] == "cancelled"
        if order["status"] == "delivered" and order["delivered_at"]:
            days = (at - datetime.fromisoformat(order["delivered_at"])).total_seconds() / 86400
            eligible = 0 <= days <= policy["return_window_days"]
        if not eligible:
            return finish("escalate", "Refund policy is not satisfied: the order must be cancelled, or delivered within the seven-day window. Manual review is required.", "POL-REFUND")
        return finish("refund_order", "Eligible for a full simulated refund. Human approval is required.", "POL-REFUND", True, order["amount_paise"])
    return finish("escalate", "The request is ambiguous or unsupported. Select an explicit intent or ask a human reviewer.", "POL-CONTROL")
