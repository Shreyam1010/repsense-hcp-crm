"""Graph state. The `form` reducer is mandatory — and not for the reason usually given.

PRIMARY: a bare `form: dict` is a LastValue channel, so every write CLOBBERS the whole
dict. Turn 2's {"sentiment": ...} would erase turn 1's hcp_id/date/topics. The chat-driven flow
depends on fields ACCUMULATING across turns; without this reducer the form empties itself.

SECONDARY: two tool calls in one AIMessage both writing `form` raise InvalidUpdateError.
gpt-oss-120b does not do parallel tool calls (Groq's support table), so this stays latent
here and would detonate on a swap to llama-3.3-70b-versatile, which does. Defense in depth."""
from typing import Annotated, Any

from langchain.agents import AgentState
from typing_extensions import NotRequired

def merge_form(left: dict | None, right: dict | None) -> dict:
    """Shallow-merge partial form patches so fields accumulate across turns."""
    return {**(left or {}), **(right or {})}

def append_flags(left: list | None, right: list | None) -> list:
    return (left or []) + (right or [])

class FormState(AgentState):
    form:             NotRequired[Annotated[dict[str, Any], merge_form]]
    compliance_flags: NotRequired[Annotated[list[dict], append_flags]]
    interaction_id:   NotRequired[str]
    rep_id:           NotRequired[str]
    territory_id:     NotRequired[str]
