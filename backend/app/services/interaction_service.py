"""Core interaction service: logging and editing call reports.

Draft content lives in graph state (the checkpointer); interaction_versions is written
ONLY at file-time and amend-time, so every row in it is an immutable filed record and the
append-only trigger is always correct. This is the same set of service functions the REST
form path calls — the two writers (chat / form) cannot drift because they share this code."""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..db.session import engine
from ..schemas import ComplianceFlag, EditResult, PatchResult
from . import audit, compliance, material_service

_CONTROL_KEYS = {"commit", "runtime"}

_REQUIRED_FOR_SUBMIT = ["hcp_id"]

def _clean(patch: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in patch.items() if k not in _CONTROL_KEYS and v is not None}

def _apply_dotted(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Apply changed_fields that may use dotted paths ('sentiment.label') or whole values."""
    out = json.loads(json.dumps(base))
    for key, val in changes.items():
        if "." in key:
            parts = key.split(".")
            node = out
            for p in parts[:-1]:
                node = node.setdefault(p, {})
                if not isinstance(node, dict):
                    node = {}
            node[parts[-1]] = val
        else:
            out[key] = val
    return out

def _missing_for_submit(form: dict[str, Any]) -> list[str]:
    return [f for f in _REQUIRED_FOR_SUBMIT if not form.get(f)]

async def apply_patch(
    patch: dict[str, Any],
    *,
    rep_id: str,
    territory_id: str,
    prior_form: Optional[dict[str, Any]] = None,
    thread_id: Optional[str] = None,
    interaction_id: Optional[str] = None,
) -> PatchResult:
    """Merge a chat/tool patch into the draft. On commit=true, file it (v1 immutable) —
    but refuse if a required field is missing, an inferred sentiment is unconfirmed, or a
    safety signal was detected."""
    prior_form = prior_form or {}
    clean_patch = _clean(patch)
    merged = {**prior_form, **clean_patch}
    commit = bool(patch.get("commit"))

    flags: list[ComplianceFlag] = []
    flags += compliance.pii_ae_tripwire(
        merged.get("summary_text"),
        merged.get("outcomes"),
        " ".join(t.get("key_message", "") for t in (merged.get("topics_discussed") or []) if isinstance(t, dict)),
    )
    sent_flags, needs_confirmation = compliance.validate_sentiment(merged.get("sentiment"))
    flags += sent_flags

    missing = _missing_for_submit(merged)
    has_block = any(f.severity == "block" for f in flags)

    if commit:
        if missing:
            return PatchResult(
                interaction_id=interaction_id or "draft", version=0, status="DRAFT",
                patch=clean_patch, flags=flags,
                tool_feedback={"filed": False, "missing_for_submit": missing,
                               "reason": f"Cannot file — missing required field(s): {missing}."},
            )
        if needs_confirmation:
            flags.append(ComplianceFlag(
                severity="block", code="sentiment_unconfirmed_refuse",
                message=("I won't file an AI-inferred read of a physician under your name until you "
                         "confirm it."), field="sentiment"))
            return PatchResult(
                interaction_id=interaction_id or "draft", version=0, status="DRAFT",
                patch=clean_patch, flags=flags,
                tool_feedback={"filed": False, "needs_confirmation": "sentiment",
                               "reason": "Inferred sentiment must be confirmed by the rep before filing."},
            )
        if has_block:
            return PatchResult(
                interaction_id=interaction_id or "draft", version=0, status="DRAFT",
                patch=clean_patch, flags=flags,
                tool_feedback={"filed": False, "blocked": True,
                               "reason": "A blocking compliance flag prevents filing (see flags)."},
            )
        iid, version = await file_snapshot(
            merged, rep_id=rep_id, territory_id=territory_id, hcp_id=merged.get("hcp_id"),
            thread_id=thread_id, actor_id=rep_id, actor_role="field_rep",
            interaction_id=interaction_id if interaction_id and interaction_id != "draft" else None,
        )
        return PatchResult(
            interaction_id=iid, version=version, status="SUBMITTED",
            patch=clean_patch, flags=flags,
            tool_feedback={"filed": True, "interaction_id": iid, "version": version,
                           "status": "SUBMITTED", "locked": True},
            narration="Filed and locked as version 1.",
        )

    return PatchResult(
        interaction_id=interaction_id or "draft", version=0, status="DRAFT",
        patch=clean_patch, flags=flags,
        tool_feedback={"filed": False, "fields_written": list(clean_patch.keys()),
                       "missing_for_submit": missing,
                       "needs_confirmation": "sentiment" if needs_confirmation else None},
    )

async def file_snapshot(
    snapshot: dict[str, Any],
    *,
    rep_id: str,
    territory_id: str,
    hcp_id: Optional[str],
    thread_id: Optional[str] = None,
    actor_id: str,
    actor_role: str = "field_rep",
    interaction_id: Optional[str] = None,
) -> tuple[str, int]:
    """Write the header + immutable version 1. Serves both chat-commit and REST submit."""
    persisted = {k: v for k, v in snapshot.items() if k not in _CONTROL_KEYS}
    async with engine.begin() as conn:
        if interaction_id:
            iid = interaction_id
        else:
            iid = (await conn.execute(text("""
                INSERT INTO interactions (rep_id, hcp_id, territory_id, status, locked,
                                          current_version, thread_id)
                VALUES (:rep, :hcp, :terr, 'SUBMITTED', true, 1, :tid)
                RETURNING interaction_id
            """), {"rep": rep_id, "hcp": hcp_id, "terr": territory_id, "tid": thread_id})).scalar_one()
        iid = str(iid)

        await conn.execute(text("""
            INSERT INTO interaction_versions (interaction_id, version, snapshot, actor_id, actor_role)
            VALUES (:iid, 1, CAST(:snap AS JSONB), :actor, :role)
        """), {"iid": iid, "snap": json.dumps(persisted), "actor": actor_id, "role": actor_role})

        await _freeze_materials(conn, iid, 1, persisted.get("materials_shared") or [])

        await audit.write_audit(conn, actor_id=actor_id, actor_type="rep",
                                action="interaction:file", entity_type="interaction",
                                entity_id=iid, thread_id=thread_id,
                                after=json.dumps(persisted), reason="filed v1")
    return iid, 1

async def _freeze_materials(conn: AsyncConnection, iid: str, version: int, material_ids: list[str]) -> None:
    if not material_ids:
        return
    lookup = await material_service.resolve_material_ids([m for m in material_ids if isinstance(m, str)])
    for mid, meta in lookup.items():
        await conn.execute(text("""
            INSERT INTO interaction_materials (interaction_id, version, material_id,
                                               mlr_code_at_share, approval_status_at_share)
            VALUES (:iid, :v, :mid, :mlr, :st)
        """), {"iid": iid, "v": version, "mid": mid,
               "mlr": meta["mlr_code"], "st": meta["status"]})

async def amend(
    interaction_id: str,
    changed_fields: dict[str, Any],
    *,
    reason_code: str,
    reason_for_change: str,
    actor_id: str,
    actor_role: str = "field_rep",
    expected_version: Optional[int] = None,
) -> EditResult:
    """Append version N+1. Never a destructive UPDATE. Resolves dotted paths so the model
    can say sentiment.label='negative' without restating the whole record."""
    async with engine.begin() as conn:
        cur = (await conn.execute(text("""
            SELECT i.current_version, i.status, i.server_recorded_at, v.snapshot
            FROM interactions i
            JOIN interaction_versions v
              ON v.interaction_id = i.interaction_id AND v.version = i.current_version
            WHERE i.interaction_id = :iid
        """), {"iid": interaction_id})).mappings().first()
        if not cur:
            raise ValueError(f"interaction {interaction_id} not found")
        if expected_version is not None and expected_version != cur["current_version"]:
            raise ConflictError(cur["current_version"])

        prior = cur["snapshot"] or {}
        new_snapshot = _apply_dotted(prior, changed_fields)
        new_version = cur["current_version"] + 1

        diff = []
        for key, to_val in changed_fields.items():
            from_val = prior
            for p in key.split("."):
                from_val = from_val.get(p) if isinstance(from_val, dict) else None
            if from_val != to_val:
                diff.append({"field": key, "from": from_val, "to": to_val})

        import datetime as _dt
        age_days = (_dt.datetime.now(_dt.timezone.utc) - cur["server_recorded_at"]).days
        requires_approval = age_days > 14

        await conn.execute(text("""
            INSERT INTO interaction_versions (interaction_id, version, snapshot, diff,
                                              reason_code, reason_for_change, actor_id, actor_role,
                                              requires_approval)
            VALUES (:iid, :v, CAST(:snap AS JSONB), CAST(:diff AS JSONB),
                    :rc, :reason, :actor, :role, :req)
        """), {"iid": interaction_id, "v": new_version, "snap": json.dumps(new_snapshot),
               "diff": json.dumps(diff), "rc": reason_code, "reason": reason_for_change,
               "actor": actor_id, "role": actor_role, "req": requires_approval})

        if not requires_approval:
            await conn.execute(text("""
                UPDATE interactions SET current_version = :v, status = 'AMENDED'
                WHERE interaction_id = :iid
            """), {"v": new_version, "iid": interaction_id})

        audit_id = await audit.write_audit(
            conn, actor_id=actor_id, actor_type="rep", action="interaction:amend",
            entity_type="interaction", entity_id=interaction_id,
            before=json.dumps(prior), after=json.dumps(new_snapshot), reason=reason_for_change)

    return EditResult(
        interaction_id=interaction_id, new_version=new_version, prior_version=cur["current_version"],
        diff=diff, changed_fields=changed_fields, requires_approval=requires_approval, audit_id=audit_id,
        narration=(f"Amended to v{new_version}. Reason: {reason_for_change}. v{cur['current_version']} is retained."
                   if not requires_approval else
                   f"Change recorded as v{new_version} but routed for compliance approval (record is "
                   f"{age_days} days old)."),
    )

class ConflictError(Exception):
    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__(f"version conflict: current is {current_version}")

async def get_current(interaction_id: str) -> Optional[dict[str, Any]]:
    async with engine.connect() as conn:
        row = (await conn.execute(text("""
            SELECT interaction_id, rep_id, hcp_id, territory_id, status, locked,
                   current_version, snapshot, server_recorded_at
            FROM interaction_current WHERE interaction_id = :iid
        """), {"iid": interaction_id})).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["interaction_id"] = str(d["interaction_id"])
    d["server_recorded_at"] = d["server_recorded_at"].isoformat()
    return d

async def get_versions(interaction_id: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT version, snapshot, diff, reason_code, reason_for_change, actor_id, actor_role,
                   requires_approval, created_at
            FROM interaction_versions WHERE interaction_id = :iid ORDER BY version
        """), {"iid": interaction_id})).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return out
