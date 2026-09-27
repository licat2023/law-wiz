class AgentNotFoundError(Exception):
    """Raised when an agent code is not registered."""

    def __init__(self, agent_code: str) -> None:
        self.agent_code = agent_code
        super().__init__(f"Agent not found: {agent_code}")
