"""PDMA (21 CFR 203) sample disbursement. WRITE-ONCE — corrections are a reversal
transaction, never an edit. Five hard-fails, each a visible on-camera refusal:

  1. lot expired < interaction date            (203.38 lot/control tracking)
  2. lot not in the rep's reconciled inventory
  3. recipient is not a licensed prescriber
  4. annual per-HCP/product limit exceeded
  5. missing signature -> blocks SUBMIT of the parent call report (not this record)

A REJECT blocks SUBMIT, not DRAFT: the line is saved flagged PENDING_RECONCILIATION so a
rep in a hospital corridor whose lot number is one digit off doesn't lose the work and
find a way around the tool."""
from datetime import date
from typing import Any, Optional

from sqlalchemy import text

from ..db.session import engine

_RESOLVE_PRODUCT = text("""SELECT product_id FROM product
    WHERE product_id=:p OR brand_name ILIKE :p OR brand_name ILIKE '%'||:p||'%' OR molecule ILIKE :p LIMIT 1""")
_LOT = text("SELECT lot_id, expiry_date FROM sample_lot WHERE product_id=:pid AND lot_number=:lot")
_INV = text("""SELECT ri.units_on_hand FROM rep_inventory ri JOIN sample_lot sl ON sl.lot_id=ri.lot_id
               WHERE ri.rep_id=:rep AND sl.product_id=:pid AND sl.lot_number=:lot""")
_HCP = text("SELECT is_licensed_prescriber, sample_eligible FROM hcp WHERE hcp_id=:hcp")
_LIMIT = text("SELECT annual_sample_limit_per_hcp FROM product WHERE product_id=:pid")
_YTD = text("""SELECT COALESCE(SUM(quantity),0) FROM sample_transactions
               WHERE hcp_id=:hcp AND product_id=:pid AND status='RECORDED'
                 AND created_at >= date_trunc('year', now())""")
_INSERT = text("""
    INSERT INTO sample_transactions
      (interaction_id, hcp_id, rep_id, product_id, lot_id, lot_number, expiry_date, quantity,
       unit_of_measure, delivery_method, signature_artifact_ref, signature_datetime, status,
       rejection_reason, compliance_result)
    VALUES
      (:interaction_id, :hcp, :rep, :pid, :lot_id, :lot, :expiry, :qty,
       :uom, :delivery, :sig, :sig_dt, :status,
       :rej, CAST(:compliance AS JSONB))
    RETURNING sample_transaction_id
""")

async def record_sample_distribution(
    *,
    hcp_id: str,
    product_id: str,
    lot_number: str,
    quantity: int,
    rep_id: str,
    interaction_id: Optional[str] = None,
    unit_of_measure: str = "units",
    delivery_method: str = "hand_delivered",
    signature_artifact_ref: Optional[str] = None,
    as_of_date: Optional[date] = None,
) -> dict[str, Any]:
    import json
    from datetime import datetime, timezone
    today = as_of_date or date.today()

    async with engine.begin() as conn:

        product_id = (await conn.execute(_RESOLVE_PRODUCT, {"p": product_id})).scalar() or product_id
        lot = (await conn.execute(_LOT, {"pid": product_id, "lot": lot_number})).mappings().first()
        inv = (await conn.execute(_INV, {"rep": rep_id, "pid": product_id, "lot": lot_number})).scalar()
        hcp = (await conn.execute(_HCP, {"hcp": hcp_id})).mappings().first()
        limit = (await conn.execute(_LIMIT, {"pid": product_id})).scalar() or 12
        ytd = (await conn.execute(_YTD, {"hcp": hcp_id, "pid": product_id})).scalar() or 0

        checks = {
            "lot_valid": lot is not None,
            "not_expired": bool(lot and lot["expiry_date"] >= today),
            "in_reconciled_inventory": inv is not None and inv >= quantity,
            "recipient_licensed": bool(hcp and hcp["is_licensed_prescriber"] and hcp["sample_eligible"]),
            "within_annual_limit": (ytd + quantity) <= limit,
            "signature_captured": signature_artifact_ref is not None,
        }

        rejection = None
        if not checks["lot_valid"]:
            rejection = f"Lot {lot_number} not found for this product."
        elif not checks["not_expired"]:
            rejection = (f"Lot {lot_number} expired {lot['expiry_date']}. A disbursement cannot be "
                         "recorded from an expired lot (21 CFR 203.38).")
        elif not checks["in_reconciled_inventory"]:
            rejection = (f"Lot {lot_number} is not in your reconciled inventory in sufficient quantity "
                         f"(need {quantity}, have {inv or 0}).")
        elif not checks["recipient_licensed"]:
            rejection = "Recipient is not a licensed prescriber — samples may only go to prescribers (PDMA)."
        elif not checks["within_annual_limit"]:
            rejection = (f"Annual limit exceeded: {ytd} of {limit} units already recorded this year for "
                         f"this HCP/product; {quantity} more would breach the cap.")

        status = "REJECTED" if rejection else "RECORDED"

        saved_to_draft_flagged = False
        if status == "REJECTED":
            saved_to_draft_flagged = True

        tx_id = (await conn.execute(_INSERT, {
            "interaction_id": interaction_id, "hcp": hcp_id, "rep": rep_id, "pid": product_id,
            "lot_id": lot["lot_id"] if lot else None, "lot": lot_number,
            "expiry": lot["expiry_date"] if lot else today, "qty": quantity,
            "uom": unit_of_measure, "delivery": delivery_method,
            "sig": signature_artifact_ref,
            "sig_dt": datetime.now(timezone.utc) if signature_artifact_ref else None,
            "status": status, "rej": rejection,
            "compliance": json.dumps(checks),
        })).scalar_one()

        if status == "RECORDED":
            await conn.execute(text("""
                UPDATE rep_inventory SET units_on_hand = units_on_hand - :qty
                WHERE rep_id=:rep AND lot_id=:lot_id
            """), {"qty": quantity, "rep": rep_id, "lot_id": lot["lot_id"]})

    remaining = None if status == "REJECTED" else (inv - quantity)
    return {
        "sample_transaction_id": str(tx_id),
        "status": status,
        "remaining_inventory": remaining,
        "compliance_result": checks,
        "rejection_reason": rejection,
        "saved_to_draft_flagged": saved_to_draft_flagged,
        "signature_required_for_submit": not checks["signature_captured"],
    }
