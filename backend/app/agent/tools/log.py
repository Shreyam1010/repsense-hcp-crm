"""The mandated Log Interaction tool.

Extracts entities from the rep's free text, patches the live form draft (this is what
makes the form fill itself from chat), and — on explicit confirmation (commit=true) —
files an immutable, locked, version-1 call report."""
import json
from typing import Any, Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from ...schemas import _coerce_bool
from ...services import interaction_service as isvc

_SENT_LABELS = {"positive", "neutral", "negative"}

class LogInteractionArgs(BaseModel):
    commit: Optional[str] = Field("false", description="'true' to FILE the report — only after the rep explicitly confirms. Else 'false'.")
    hcp_id: Optional[str] = Field(None, description="Resolved HCP id from resolve_hcp. NEVER a free-text name.")
    interaction_type: Optional[str] = Field(
        None, description="One of: face_to_face, remote_video, phone, conference, group_event")
    interaction_datetime_claimed: Optional[str] = Field(None, description="ISO8601 datetime the rep claims.")
    summary_text: Optional[str] = Field(None, description="Factual summary of what was discussed (the topics).")
    summary_provenance: Optional[str] = Field(None, description="typed | chat_extractive | voice_transcript_extractive")
    attendees: Optional[list[str]] = Field(None, description="Names of others present, as plain strings.")
    materials_shared: Optional[list[str]] = Field(None, description="material_ids from check_product_material only.")
    sentiment: Optional[dict] = Field(
        None, description="Object {label, source, rationale_quote}. label is one of positive/neutral/negative; "
                          "source is rep_stated or model_inferred; rationale_quote is the rep's exact words. "
                          "OMIT this field entirely if the rep gave no sentiment signal — do NOT send nulls.")
    outcomes: Optional[str] = None
    consent_ref: Optional[str] = None

def _normalize_sentiment(sent: Any) -> Optional[dict]:
    """Accept a loose sentiment object; return a clean one or None if it has no usable label."""
    if not isinstance(sent, dict):
        return None
    label = sent.get("label")
    if label not in _SENT_LABELS:
        return None
    out = {"label": label,
           "source": sent.get("source") if sent.get("source") in ("rep_stated", "model_inferred") else "model_inferred",
           "rationale_quote": sent.get("rationale_quote"),
           "confirmed_by_rep": bool(sent.get("confirmed_by_rep"))}
    if sent.get("barrier_code"):
        out["barrier_code"] = sent["barrier_code"]
    return out

def _dump(v):
    """Normalize pydantic models -> plain JSON-able values (exclude None)."""
    if isinstance(v, BaseModel):
        return v.model_dump(exclude_none=True)
    if isinstance(v, list):
        return [_dump(x) for x in v]
    return v

@tool(args_schema=LogInteractionArgs)
async def log_interaction(*, runtime: ToolRuntime, **kw) -> Command:
    """Draft or file an HCP call report. Extract only what the rep actually said. Set
    commit=true ONLY after the rep has explicitly confirmed."""
    try:
        state = runtime.state or {}
        commit = _coerce_bool(kw.pop("commit", False))
        if "sentiment" in kw:
            kw["sentiment"] = _normalize_sentiment(kw["sentiment"])
        patch = {k: _dump(v) for k, v in kw.items() if v is not None}
        patch["commit"] = commit
        result = await isvc.apply_patch(
            patch,
            rep_id=state.get("rep_id", "REP-001"),
            territory_id=state.get("territory_id", "IN-South-02"),
            prior_form=state.get("form", {}),
            thread_id=(runtime.config or {}).get("configurable", {}).get("thread_id"),
            interaction_id=state.get("interaction_id"),
        )
        if runtime.stream_writer:
            runtime.stream_writer({"event": "tool_call",
                                   "data": {"name": "log_interaction", "status": "ok",
                                            "filed": result.tool_feedback.get("filed", False)}})
            if result.status == "SUBMITTED":
                runtime.stream_writer({"event": "filed", "data": {
                    "interaction_id": result.interaction_id, "version": result.version,
                    "status": "SUBMITTED"}})
        update = {
            "form": result.patch,
            "compliance_flags": [f.model_dump() for f in result.flags],
            "messages": [ToolMessage(content=json.dumps(result.tool_feedback),
                                     tool_call_id=runtime.tool_call_id)],
        }
        if result.status == "SUBMITTED":
            update["interaction_id"] = result.interaction_id
        return Command(update=update)
    except Exception as e:
        return Command(update={"messages": [ToolMessage(
            content=f"TOOL_ERROR log_interaction: {e}", tool_call_id=runtime.tool_call_id)]})
