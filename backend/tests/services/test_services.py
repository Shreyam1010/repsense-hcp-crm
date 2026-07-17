"""Service-layer tests. These exercise the business logic directly (no LLM, no HTTP),
which is where the compliance guarantees actually live."""
import pytest
from sqlalchemy import text

from app.db.session import engine
from app.services import (
    compliance,
    hcp_service,
    interaction_service as isvc,
    material_service,
    sample_service,
)

async def test_resolve_disambiguates_two_sharmas():
    r = await hcp_service.resolve_hcp("Dr. Sharma", "IN-South-02")
    assert r["action_required"] == "DISAMBIGUATE"
    assert {c["hcp_id"] for c in r["candidates"]} == {"HCP-001", "HCP-002"}

async def test_resolve_full_name_is_single():
    r = await hcp_service.resolve_hcp("Priya Sharma", "IN-South-02")
    assert r["action_required"] is None
    assert r["candidates"][0]["hcp_id"] == "HCP-001"

async def test_resolve_out_of_territory_withheld_by_default():
    r = await hcp_service.resolve_hcp("Vikram Rao", "IN-South-02")
    assert r["action_required"] == "NO_MATCH_REQUEST_MDM"
    r2 = await hcp_service.resolve_hcp("Vikram Rao", "IN-South-02", include_out_of_territory=True)
    assert r2["candidates"][0]["hcp_id"] == "HCP-004"

async def test_materials_gate_filters_expired_and_withdrawn():
    m = await material_service.check_product_material("PRD-ONC", country="IN")
    approved = {x["mlr_code"] for x in m["approved_materials"]}
    reasons = {x["reason"] for x in m["filtered_out"]}
    assert approved == {"MLR-2026-ONC-0142", "MLR-2026-ONC-0155"}
    assert reasons == {"EXPIRED", "WITHDRAWN"}

@pytest.mark.parametrize("kw,expect_status,needle", [
    (dict(hcp_id="HCP-001", lot_number="OB-2308-B", quantity=2, signature_artifact_ref="s"), "REJECTED", "expired"),
    (dict(hcp_id="HCP-005", lot_number="OB-2410-A", quantity=2, signature_artifact_ref="s"), "REJECTED", "prescriber"),
    (dict(hcp_id="HCP-001", lot_number="NOPE", quantity=1, signature_artifact_ref="s"), "REJECTED", "not found"),
    (dict(hcp_id="HCP-001", lot_number="OB-2410-A", quantity=13, signature_artifact_ref="s"), "REJECTED", "limit"),
    (dict(hcp_id="HCP-001", lot_number="OB-2410-A", quantity=2, signature_artifact_ref="s"), "RECORDED", None),
])
async def test_sample_hard_fails(kw, expect_status, needle):
    s = await sample_service.record_sample_distribution(product_id="PRD-ONC", rep_id="REP-001", **kw)
    assert s["status"] == expect_status
    if needle:
        assert needle.lower() in (s["rejection_reason"] or "").lower()

async def test_sample_missing_signature_blocks_submit_but_records():
    s = await sample_service.record_sample_distribution(
        hcp_id="HCP-001", product_id="PRD-ONC", lot_number="OB-2410-A", quantity=1, rep_id="REP-001")
    assert s["status"] == "RECORDED"
    assert s["signature_required_for_submit"] is True

async def test_adverse_event_tripwire_blocks():
    flags = compliance.pii_ae_tripwire("62-year-old patient had a serious adverse reaction")
    assert any(f.code == "adverse_event_suspected" and f.severity == "block" for f in flags)

async def test_log_draft_then_commit_refuses_unconfirmed_inferred_sentiment():

    draft = await isvc.apply_patch(
        {"hcp_id": "HCP-001", "interaction_type": "face_to_face",
         "summary_text": "Discussed OASIS efficacy data",
         "sentiment": {"label": "positive", "source": "model_inferred",
                       "rationale_quote": "went really well"}},
        rep_id="REP-001", territory_id="IN-South-02", prior_form={})
    assert draft.status == "DRAFT"

    refused = await isvc.apply_patch(
        {"commit": True}, rep_id="REP-001", territory_id="IN-South-02",
        prior_form={"hcp_id": "HCP-001",
                    "sentiment": {"label": "positive", "source": "model_inferred",
                                  "rationale_quote": "went really well", "confirmed_by_rep": False}})
    assert refused.tool_feedback["filed"] is False
    assert refused.tool_feedback.get("needs_confirmation") == "sentiment"

async def test_commit_files_immutable_v1_then_amend_appends_v2():
    form = {"hcp_id": "HCP-001", "interaction_type": "face_to_face",
            "summary_text": "OASIS efficacy discussed",
            "sentiment": {"label": "positive", "source": "rep_stated",
                          "rationale_quote": "went really well", "confirmed_by_rep": True}}
    filed = await isvc.apply_patch({"commit": True}, rep_id="REP-001",
                                   territory_id="IN-South-02", prior_form=form)
    assert filed.status == "SUBMITTED" and filed.version == 1
    iid = filed.interaction_id

    res = await isvc.amend(
        iid, {"sentiment.label": "negative", "sentiment.barrier_code": "formulary_not_listed"},
        reason_code="rep_correction",
        reason_for_change="rep correction — HCP reaction mischaracterized in original entry",
        actor_id="REP-001")
    assert res.new_version == 2
    assert any(d["field"] == "sentiment.label" and d["to"] == "negative" for d in res.diff)

    versions = await isvc.get_versions(iid)
    assert len(versions) == 2
    assert versions[0]["snapshot"]["sentiment"]["label"] == "positive"
    current = await isvc.get_current(iid)
    assert current["snapshot"]["sentiment"]["label"] == "negative"
    assert current["snapshot"]["sentiment"]["barrier_code"] == "formulary_not_listed"

async def test_append_only_trigger_blocks_destructive_update():
    """The kill shot, as a test: no UPDATE can destroy a filed version."""
    form = {"hcp_id": "HCP-001",
            "sentiment": {"label": "positive", "source": "rep_stated",
                          "rationale_quote": "ok", "confirmed_by_rep": True}}
    filed = await isvc.apply_patch({"commit": True}, rep_id="REP-001",
                                   territory_id="IN-South-02", prior_form=form)
    with pytest.raises(Exception) as exc:
        async with engine.begin() as conn:
            await conn.execute(text(
                "UPDATE interaction_versions SET snapshot='{}' WHERE interaction_id=:i AND version=1"),
                {"i": filed.interaction_id})
    assert "append-only" in str(exc.value) or "permission denied" in str(exc.value)
