"""Decision agent delegates to the shared deterministic eligibility engine."""
from ..core.eligibility import evaluate_eligibility

class DecisionAgent:
    name = "Decision Agent"

    def decide(self, order, intent, evidence, at=None):
        return evaluate_eligibility(order, intent, evidence, at)
