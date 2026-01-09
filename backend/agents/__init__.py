"""Backend agents package."""

from .clarifying import clarifying_agent
from .search import search_agent

# Wire up handoffs (done here to avoid circular imports)
# ClarifyingAgent hands off to SearchAgent when SearchProfile is complete
clarifying_agent.handoffs = [search_agent]

__all__ = ["clarifying_agent", "search_agent"]
