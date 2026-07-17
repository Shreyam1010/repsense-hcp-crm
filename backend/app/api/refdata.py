"""Reference-data endpoints. These call the SAME service functions the agent tools call,
so the structured-form path and the chat path share one implementation and cannot drift."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..db.session import engine
from ..services import hcp_service, material_service
from .deps import current_rep

router = APIRouter()

@router.get("/api/hcps")
async def list_hcps(q: str = "", territory_id: str = "", rep=Depends(current_rep)):
    """Typeahead for the form's HCP Name field — same data resolve_hcp uses."""
    return await hcp_service.list_hcps(q, territory_id or rep["territory_id"])

@router.get("/api/products")
async def list_products():
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT product_id, brand_name, molecule, approved_indication FROM product ORDER BY brand_name"
        ))).mappings().all()
    return [dict(r) for r in rows]

@router.get("/api/materials")
async def list_materials(product_id: str, country: str = "IN", channel: str = "in_person"):
    """Returns {approved_materials, filtered_out[{reason}]} — the MLR gate, over HTTP."""
    return await material_service.check_product_material(product_id, country=country, channel=channel)

@router.get("/api/sample-lots")
async def sample_lots(rep=Depends(current_rep)):
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT sl.lot_id, sl.product_id, sl.lot_number, sl.expiry_date, sl.strength,
                   ri.units_on_hand, (sl.expiry_date < current_date) AS expired
            FROM rep_inventory ri JOIN sample_lot sl ON sl.lot_id = ri.lot_id
            WHERE ri.rep_id = :rep ORDER BY sl.product_id, sl.lot_number
        """), {"rep": rep["id"]})).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["expiry_date"] = d["expiry_date"].isoformat()
        out.append(d)
    return out

@router.post("/api/consents")
async def capture_consent(body: dict, rep=Depends(current_rep)):
    """The screenshot's '(Requires Consent)' made functional. A real gate: the mic stays
    disabled until a consent_ref exists, and the DB CHECK rejects voice provenance without one."""
    async with engine.begin() as conn:
        ref = (await conn.execute(text("""
            INSERT INTO consent (hcp_id, consent_type, consent_method, jurisdiction, valid_until)
            VALUES (:hcp, :ctype, :method, :jur, now() + interval '180 days')
            RETURNING consent_ref
        """), {"hcp": body.get("hcp_id"), "ctype": body.get("consent_type", "voice_recording"),
               "method": body.get("consent_method", "verbal_on_record"),
               "jur": body.get("jurisdiction", "IN")})).scalar_one()
    return {"consent_ref": str(ref), "valid_until_days": 180}
