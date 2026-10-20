"""Existing AgentFlow role, preserved for Phase 2."""
import re

class PlannerAgent:
    name = "Planner Agent"

    def infer_intent(self, message):
        text = message.lower()
        if re.search(r"\b(don't|do not|never|not|stop|avoid)\b", text):
            return "unknown"
        choices = set()
        if re.search(r"\b(cancel|cancellation)\b", text):
            choices.add("cancel")
        if re.search(r"\b(refund|money back|return)\b", text):
            choices.add("refund")
        if len(choices) == 1:
            return choices.pop()
        if not choices and re.search(r"\b(status|where|track|tracking|delayed|late|delivery|arrive)\b", text):
            return "status"
        return "unknown"
