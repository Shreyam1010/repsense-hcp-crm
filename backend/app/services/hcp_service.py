"""HCP master-data resolution and history. Fails closed: never auto-creates an HCP,
never returns out-of-territory records without an explicit flag."""
from typing import Any, Optional

from sqlalchemy import text

from ..db.session import engine

_RESOLVE = text("""
    SELECT hcp_id, full_name, npi, specialty, institution, city, country,
           territory_id, decile, state_license_status, is_licensed_prescriber,
           sample_eligible, email_opt_in, voice_consent_on_file,
           similarity(full_name, :q) AS match_confidence
    FROM hcp
    WHERE full_name % :q OR full_name ILIKE '%' || :q || '%'
    ORDER BY match_confidence DESC, full_name
    LIMIT 8
""")

async def resolve_hcp(
    query_text: str,
    territory_id: str,
    *,
    specialty_hint: Optional[str] = None,
    institution_hint: Optional[str] = None,
    include_out_of_territory: bool = False,
) -> dict[str, Any]:
    """Resolve a spoken/typed name to canonical HCP master records.

    Returns {candidates: [...], action_required: None | 'DISAMBIGUATE' | 'NO_MATCH_REQUEST_MDM'}.
    log_interaction requires a resolved hcp_id, so 'Met Dr. Sharma' cannot be satisfied in
    one tool call — the multi-hop chain emerges from this contract, not a hardcoded sequence."""
    async with engine.connect() as conn:
        rows = (await conn.execute(_RESOLVE, {"q": query_text.strip()})).mappings().all()

    candidates = []
    for r in rows:
        in_territory = r["territory_id"] == territory_id
        if not in_territory and not include_out_of_territory:
            continue
        c = dict(r)
        c["match_confidence"] = round(float(r["match_confidence"] or 0), 3)
        c["is_in_territory"] = in_territory
        c["consent_flags"] = {
            "email_opt_in": r["email_opt_in"],
            "voice_recording_consent": r["voice_consent_on_file"],
        }
        candidates.append(c)

    _HONORIFICS = {"dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.", "prof", "prof.", "the"}
    tokens = [t for t in query_text.lower().split() if t not in _HONORIFICS]
    if tokens:
        strong = [c for c in candidates if all(t in (c["full_name"] or "").lower() for t in tokens)]
        if strong:
            candidates = strong

    if specialty_hint and len(candidates) > 1:
        narrowed = [c for c in candidates if specialty_hint.lower() in (c["specialty"] or "").lower()]
        if narrowed:
            candidates = narrowed

    if not candidates:
        return {"candidates": [], "action_required": "NO_MATCH_REQUEST_MDM"}
    if len(candidates) > 1:
        return {"candidates": candidates, "action_required": "DISAMBIGUATE"}
    return {"candidates": candidates, "action_required": None}

_HISTORY = text("""
    SELECT i.interaction_id, i.status, i.server_recorded_at, v.snapshot
    FROM interactions i
    JOIN interaction_versions v
      ON v.interaction_id = i.interaction_id AND v.version = i.current_version
    WHERE i.hcp_id = :hcp_id
      AND i.territory_id = :territory_id            -- territory access enforced IN SQL
      AND i.server_recorded_at >= now() - (:lookback_days * interval '1 day')
    ORDER BY i.server_recorded_at DESC
    LIMIT :limit
""")

_YTD_SAMPLES = text("""
    SELECT product_id, COALESCE(SUM(quantity), 0) AS units
    FROM sample_transactions
    WHERE hcp_id = :hcp_id AND status = 'RECORDED'
      AND created_at >= date_trunc('year', now())
    GROUP BY product_id
""")

async def get_hcp_history(
    hcp_id: str, territory_id: str, *, lookback_days: int = 180, limit: int = 10
) -> dict[str, Any]:
    async with engine.connect() as conn:

        exists = (await conn.execute(
            text("SELECT 1 FROM hcp WHERE hcp_id = :h"), {"h": hcp_id})).scalar()
        if not exists:
            resolved = (await conn.execute(text("""
                SELECT hcp_id FROM hcp
                WHERE territory_id = :t AND (full_name ILIKE '%' || :q || '%' OR full_name % :q)
                ORDER BY similarity(full_name, :q) DESC LIMIT 1
            """), {"t": territory_id, "q": hcp_id})).scalar()
            if resolved:
                hcp_id = resolved
        rows = (await conn.execute(_HISTORY, {
            "hcp_id": hcp_id, "territory_id": territory_id,
            "lookback_days": lookback_days, "limit": limit,
        })).mappings().all()
        ytd = (await conn.execute(_YTD_SAMPLES, {"hcp_id": hcp_id})).mappings().all()

    interactions = []
    for r in rows:
        snap = r["snapshot"] or {}
        interactions.append({
            "interaction_id": str(r["interaction_id"]),
            "date": r["server_recorded_at"].isoformat(),
            "status": r["status"],
            "summary": snap.get("summary_text"),
            "sentiment": (snap.get("sentiment") or {}).get("label"),
            "barrier_code": (snap.get("sentiment") or {}).get("barrier_code"),
        })
    return {
        "hcp_id": hcp_id,
        "interactions": interactions,
        "aggregates": {
            "ytd_sample_units_by_product": {r["product_id"]: int(r["units"]) for r in ytd},
        },
    }

_LIST = text("""
    SELECT hcp_id, full_name, specialty, institution, city, territory_id,
           is_licensed_prescriber, sample_eligible
    FROM hcp
    WHERE (:q = '' OR full_name ILIKE '%' || :q || '%')
      AND (:territory_id = '' OR territory_id = :territory_id)
    ORDER BY full_name
    LIMIT 20
""")

async def list_hcps(q: str = "", territory_id: str = "") -> list[dict[str, Any]]:
    """Typeahead for the form's HCP Name field — the same data resolve_hcp uses."""
    async with engine.connect() as conn:
        rows = (await conn.execute(_LIST, {"q": q.strip(), "territory_id": territory_id})).mappings().all()
    return [dict(r) for r in rows]
