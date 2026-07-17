"""The one JSON shape. This `form` object is byte-identical across five homes:

    LLM tool args -> graph state["form"] -> SSE form_patch -> Redux formDraft.values
                  -> Postgres interaction_versions.snapshot (JSONB)

There is no DTO, no serializer, no toApiModel(). That is why "chat fills the form" and
"the record amends itself" are the same mechanism, and why the 'structured form
OR conversational chat' is one state machine with two writers."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

def _coerce_int(v: Any) -> Any:
    if isinstance(v, str) and v.strip():
        try:
            return int(float(v))
        except ValueError:
            return v
    return v

def _coerce_bool(v: Any) -> Any:
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y"}
    return v

CoercedInt = Annotated[int, BeforeValidator(_coerce_int)]
CoercedBool = Annotated[bool, BeforeValidator(_coerce_bool)]

SentimentLabel = Literal["positive", "neutral", "negative"]
SentimentSource = Literal["rep_stated", "model_inferred"]
InteractionType = Literal["face_to_face", "remote_video", "phone", "conference", "group_event"]
BarrierCode = Literal[
    "formulary_not_listed", "prior_auth_required", "cost_concern",
    "efficacy_doubt", "safety_concern", "no_barrier",
]

class Sentiment(BaseModel):
    """Observed/Inferred HCP sentiment. Defaults to UNSET, never Neutral: defaulting to
    Neutral is the model guessing and laundering the guess as a rep observation."""
    label: SentimentLabel
    barrier_code: Optional[BarrierCode] = None
    source: SentimentSource
    rationale_quote: Optional[str] = Field(
        None, description="Verbatim span from the rep's own words. REQUIRED when source='model_inferred'."
    )
    confirmed_by_rep: bool = False

class Attendee(BaseModel):
    name: str
    hcp_id: Optional[str] = None
    role: Optional[str] = None
    is_licensed_prescriber: bool = False

class Topic(BaseModel):
    product_id: Optional[str] = None
    key_message: Optional[str] = None
    hcp_reaction: Optional[str] = None

class FollowUp(BaseModel):
    action_type: Literal[
        "schedule_meeting", "send_approved_material", "route_medical_inquiry_to_MSL",
        "add_to_event_invite_list", "create_task",
    ]
    target_ref: Optional[str] = None
    label: str
    rationale_quote: Optional[str] = None
    confidence: Optional[float] = None

class ComplianceFlag(BaseModel):
    severity: Literal["info", "warn", "block"]
    code: str
    message: str
    field: Optional[str] = None

class PatchResult(BaseModel):
    """What a service returns after applying a chat/tool patch to the draft."""
    interaction_id: str
    version: int
    status: str
    patch: dict[str, Any]
    flags: list[ComplianceFlag] = []
    tool_feedback: dict[str, Any] = {}
    narration: Optional[str] = None

class EditResult(BaseModel):
    interaction_id: str
    new_version: int
    prior_version: int
    diff: list[dict[str, Any]]
    changed_fields: dict[str, Any]
    requires_approval: bool = False
    audit_id: Optional[int] = None
    narration: Optional[str] = None
