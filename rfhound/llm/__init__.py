"""Optional LLM copilot for RFHound.

Lets a Claude API or a local (OpenAI-compatible) model drive RFHound through a
**restricted, receive-and-analyse-only** action set. The copilot cannot transmit,
replay, capture, or run arbitrary code — those actions are simply not in its
registry. "Building features on the go" is supported only as *drafting a mod for
human review*; nothing the model writes is ever auto-executed.
"""

from .actions import ACTIONS, run_action, tool_schemas  # noqa: F401
from .agent import Copilot, AgentResult  # noqa: F401
