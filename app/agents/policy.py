"""Existing AgentFlow role, preserved for Phase 2."""

class RetrievalAgent:
    name = "Policy Agent"

    def retrieve(self, index, message, intent):
        return index.search(message, intent)
