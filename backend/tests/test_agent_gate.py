"""THE GATE. If this passes, the assignment is essentially done.

Two turns on one thread_id, driven by the real LLM:
  1. A free-text note produces a MULTI-HOP tool chain (resolve_hcp BEFORE log_interaction)
     and fills the form — the agent DECIDES, it doesn't route.
  2. A correction on the same thread flips the sentiment while the hcp_id from turn 1
     SURVIVES — proving both the checkpointer (memory) and the merge_form reducer.

Requires a real GROQ_API_KEY; skipped otherwise."""
import pytest
from langchain.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_agent
from app.config import settings

pytestmark = pytest.mark.skipif(
    not settings.groq_key_looks_real, reason="no GROQ_API_KEY set")

def _tool_names(messages):
    names = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            names.append(tc["name"])
    return names

async def test_two_turns_one_thread():
    agent = build_agent(InMemorySaver())
    cfg = {"configurable": {"thread_id": "gate-1"}, "recursion_limit": 20}

    r1 = await agent.ainvoke({
        "messages": [HumanMessage(
            "Met Dr. Priya Sharma at Apollo this morning, went really well, "
            "discussed OncoBoost OASIS efficacy")],
        "rep_id": "REP-001", "territory_id": "IN-South-02",
    }, config=cfg)

    names = _tool_names(r1["messages"])
    assert "resolve_hcp" in names, f"expected resolve_hcp in {names}"
    assert "log_interaction" in names, f"expected log_interaction in {names}"

    assert names.index("resolve_hcp") < names.index("log_interaction")
    assert r1["form"].get("hcp_id") == "HCP-001", r1["form"]

    r2 = await agent.ainvoke({
        "messages": [HumanMessage("Actually I got that wrong, it didn't go well — formulary problem")],
    }, config=cfg)

    sentiment = r2["form"].get("sentiment", {})
    assert sentiment.get("label") == "negative", r2["form"]

    assert r2["form"].get("hcp_id") == "HCP-001", r2["form"]
