"""Pure-Python compliance checks. No LLM call, no middleware routing — these are deterministic regex
tripwires that run inside the service layer.

The PII / adverse-event tripwire is the important one: a rep noting
'Dr. Sharma described a 62-year-old patient who had a bad reaction' creates
special-category personal data in a commercial CRM AND starts a ~24h serious-AE
reporting clock. That must be caught and routed to pharmacovigilance INDEPENDENTLY of
the sentiment field — a 'positive' label sitting next to a safety signal reads, in
discovery, as a company that saw an adverse event and coded it as good news."""
import re

from ..schemas import ComplianceFlag

_AE_PATTERNS = [
    r"\badverse\s+event\b", r"\bside\s*effect\b", r"\breaction\b", r"\bhospitali[sz]",
    r"\bdeath\b|\bdied\b|\bfatal\b", r"\btoxicit", r"\bSAE\b",
    r"\ballergic\b", r"\banaphyla", r"\boverdose\b",
]

_PHI_PATTERNS = [
    r"\bpatient\b", r"\b\d{1,3}\s*[- ]?year[- ]?old\b", r"\bmy\s+patient\b",
    r"\bthe\s+patient\b", r"\bMRN\b", r"\bdiagnos",
]

_AE_RE = re.compile("|".join(_AE_PATTERNS), re.IGNORECASE)
_PHI_RE = re.compile("|".join(_PHI_PATTERNS), re.IGNORECASE)

def pii_ae_tripwire(*texts: str | None) -> list[ComplianceFlag]:
    """Scan free-text fields. Returns flags; a safety hit is severity='block' and must
    route to pharmacovigilance regardless of sentiment."""
    blob = " ".join(t for t in texts if t)
    flags: list[ComplianceFlag] = []
    if not blob.strip():
        return flags

    ae = _AE_RE.search(blob)
    phi = _PHI_RE.search(blob)

    if ae:
        flags.append(ComplianceFlag(
            severity="block", code="adverse_event_suspected",
            message=(f"Possible adverse-event language ({ae.group(0)!r}) detected. This must "
                     "be routed to Pharmacovigilance — it is not a sentiment signal and cannot "
                     "be filed on a commercial call report until triaged."),
            field="summary_text",
        ))
    if phi:
        flags.append(ComplianceFlag(
            severity="warn", code="possible_phi",
            message=(f"Possible patient information ({phi.group(0)!r}) in a commercial CRM field. "
                     "Remove patient identifiers before filing (GDPR/DPDP special-category data)."),
            field="summary_text",
        ))
    return flags

def validate_sentiment(sentiment: dict | None) -> tuple[list[ComplianceFlag], bool]:
    """Returns (flags, needs_confirmation). An AI-inferred sentiment on a named physician
    cannot be filed until the rep confirms it, and requires a verbatim rationale_quote
    (also enforced by the DB CHECK inferred_sentiment_needs_quote)."""
    flags: list[ComplianceFlag] = []
    if not sentiment:
        return flags, False
    source = sentiment.get("source")
    if source == "model_inferred":
        if not sentiment.get("rationale_quote"):
            flags.append(ComplianceFlag(
                severity="block", code="inferred_sentiment_no_quote",
                message="Inferred sentiment needs a verbatim quote from the rep's own words.",
                field="sentiment",
            ))
        if not sentiment.get("confirmed_by_rep"):
            flags.append(ComplianceFlag(
                severity="warn", code="inferred_sentiment_unconfirmed",
                message=("Sentiment is the model's inference. It must be confirmed by the rep "
                         "before this call can be filed."),
                field="sentiment",
            ))
            return flags, True
    return flags, False
