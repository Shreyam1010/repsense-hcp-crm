"""suggest_follow_ups — the 'AI Suggested Follow-ups' chip row. Constrained SELECTION,
not free generation: the model classifies into a closed enum and picks target_refs from
the approved-material set. This is the ONLY place the build uses Groq Structured Outputs.

Design: try strict json_schema on the extract model; if that errors (Groq occasionally
400s on strict edge cases, and there may be no key in dev), fall back to a deterministic
rule over the draft form. The rules alone make a coherent demo."""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..config import settings

ActionType = str
_ALLOWED = {"schedule_meeting", "send_approved_material", "route_medical_inquiry_to_MSL",
            "add_to_event_invite_list", "create_task"}

class _SuggestionStrict(BaseModel):

    model_config = ConfigDict(extra="forbid")
    action_type: str
    target_ref: Optional[str]
    label: str
    rationale_quote: Optional[str]

class _SuggestionsStrict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggestions: list[_SuggestionStrict]

async def _llm_suggest(draft_form: dict, approved_material_ids: list[str]) -> Optional[list[dict]]:
    if not settings.groq_key_looks_real:
        return None
    try:
        from ..agent.llm import extract_llm
        prompt = (
            "You propose 1-3 follow-up actions for a pharma rep after an HCP call. "
            "Choose action_type ONLY from: schedule_meeting, send_approved_material, "
            "route_medical_inquiry_to_MSL, add_to_event_invite_list, create_task. "
            "For send_approved_material, target_ref MUST be one of these approved material ids: "
            f"{approved_material_ids or 'none'}. If the HCP asked an off-label question, use "
            "route_medical_inquiry_to_MSL. Base rationale_quote on the call summary. "
            f"Call draft: {draft_form}"
        )
        structured = extract_llm().with_structured_output(
            _SuggestionsStrict, method="json_schema", strict=True)
        result = await structured.ainvoke(prompt)
        return [s.model_dump() for s in result.suggestions]
    except Exception:

        try:
            from ..agent.llm import extract_llm
            structured = extract_llm().with_structured_output(_SuggestionsStrict, method="function_calling")
            result = await structured.ainvoke(prompt)
            return [s.model_dump() for s in result.suggestions]
        except Exception:
            return None

def _rule_suggest(draft_form: dict, approved_material_ids: list[str]) -> list[dict]:
    """Deterministic fallback derived from the draft."""
    out: list[dict] = []
    sentiment = (draft_form.get("sentiment") or {})
    barrier = sentiment.get("barrier_code")
    summary = (draft_form.get("summary_text") or "").lower()

    if any(w in summary for w in ("pediatric", "off-label", "off label", "unapproved")):
        out.append({"action_type": "route_medical_inquiry_to_MSL", "target_ref": None,
                    "label": "Route off-label question to Medical Affairs (MSL)",
                    "rationale_quote": draft_form.get("summary_text")})
    if approved_material_ids:
        out.append({"action_type": "send_approved_material", "target_ref": approved_material_ids[0],
                    "label": "Send approved follow-up material", "rationale_quote": None})
    if barrier == "formulary_not_listed":
        out.append({"action_type": "create_task", "target_ref": None,
                    "label": "Prepare formulary dossier for the P&T committee",
                    "rationale_quote": sentiment.get("rationale_quote")})
    out.append({"action_type": "schedule_meeting", "target_ref": None,
                "label": "Schedule a follow-up in 14 days", "rationale_quote": None})
    return out[:4]

async def suggest_follow_ups(
    draft_form: dict[str, Any], hcp_id: str, approved_material_ids: Optional[list[str]] = None
) -> dict[str, Any]:
    approved_material_ids = approved_material_ids or []
    llm = await _llm_suggest(draft_form, approved_material_ids)
    raw = llm if llm is not None else _rule_suggest(draft_form, approved_material_ids)

    suggestions = []
    for s in raw:
        if s.get("action_type") not in _ALLOWED:
            continue
        if s["action_type"] == "send_approved_material" and s.get("target_ref") not in approved_material_ids:
            continue
        s["confidence"] = s.get("confidence", 0.8)
        s["requires_human_approval"] = True
        suggestions.append(s)
    return {"suggestions": suggestions, "source": "llm" if llm is not None else "rules"}
