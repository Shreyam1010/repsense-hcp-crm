"""extract_fallback — resilience for Groq's `tool_use_failed` 400.

That 400 is a live cross-model Groq issue (agno#4090), documented for gpt-oss-120b
specifically (langchain#34155). When the model emits a malformed tool call, we don't die:
we re-extract under CONSTRAINED DECODING on the extract model and apply the patch through
the SAME service the tool would have called. Downstream cannot tell the difference — and
this is, honestly, the path a real gemma2-9b-it would always have needed.

Built as a stream-handler wrapper, not a graph node: zero unverified
API, no new node, no unanswered-tool_call 400 (we synthesize both sides of the exchange)."""
import json
from typing import Optional

from langchain.messages import AIMessage
from pydantic import BaseModel, ConfigDict

from ..agent.llm import extract_llm
from ..agent.prompt import EXTRACT_PROMPT
from ..services import interaction_service as isvc

class InteractionPatchStrict(BaseModel):
    """Strict json_schema path: Optional WITHOUT defaults so every property is required/
    nullable, plus extra='forbid' for additionalProperties:false. Groq 400s on strict
    without BOTH."""
    model_config = ConfigDict(extra="forbid")
    hcp_query: Optional[str]
    interaction_type: Optional[str]
    summary_text: Optional[str]
    sentiment_label: Optional[str]
    sentiment_source: Optional[str]
    sentiment_quote: Optional[str]
    outcomes: Optional[str]

def _to_form(obj: InteractionPatchStrict) -> dict:
    form: dict = {}
    if obj.interaction_type:
        form["interaction_type"] = obj.interaction_type
    if obj.summary_text:
        form["summary_text"] = obj.summary_text
    if obj.outcomes:
        form["outcomes"] = obj.outcomes
    if obj.sentiment_label:
        form["sentiment"] = {
            "label": obj.sentiment_label,
            "source": obj.sentiment_source or "model_inferred",
            "rationale_quote": obj.sentiment_quote,
        }
    return form

async def extract_fallback(agent, message: str, cfg: dict, rep):
    """Async generator of SSE events. Called by the chat route when the agent raises
    a Groq tool_use_failed BadRequestError."""
    yield {"event": "tool_call", "data": json.dumps(
        {"name": "extract_fallback", "status": "running", "note": "constrained re-extraction"})}

    try:
        extractor = extract_llm().with_structured_output(
            InteractionPatchStrict, method="json_schema", strict=True)
        obj = await extractor.ainvoke(EXTRACT_PROMPT.format(text=message))
    except Exception:

        extractor = extract_llm().with_structured_output(
            InteractionPatchStrict, method="function_calling")
        obj = await extractor.ainvoke(EXTRACT_PROMPT.format(text=message))

    form = _to_form(obj)

    iid = None
    st = await agent.aget_state(cfg)
    prior_form = (st.values or {}).get("form", {}) if st else {}
    result = await isvc.apply_patch(form, rep_id=rep["id"], territory_id=rep["territory_id"],
                                    prior_form=prior_form)

    await agent.aupdate_state(cfg, {"form": result.patch,
                                    "messages": [AIMessage(content="Re-extracted your note into the draft.")]})
    yield {"event": "form_patch", "data": json.dumps(result.patch)}
    yield {"event": "token", "data": json.dumps("Re-extracted your note into the draft.")}
