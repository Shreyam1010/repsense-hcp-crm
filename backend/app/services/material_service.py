"""MLR-approved material gating. The model may SELECT from this output; it may never
NAME a material. Returns filtered_out WITH reasons so the UI can render
'2 assets excluded: … (expired) · … (withdrawn)' — a filter you can watch working is
worth ten times a filter that works silently."""
from datetime import date
from typing import Any, Optional

from sqlalchemy import text

from ..db.session import engine

_RESOLVE_PRODUCT = text("""
    SELECT product_id FROM product
    WHERE product_id = :p OR brand_name ILIKE :p OR molecule ILIKE :p
       OR brand_name ILIKE '%' || :p || '%'
    LIMIT 1
""")

_QUERY = text("""
    SELECT material_id, mlr_code, title, version, product_id, approved_indication,
           approval_date, expiration_date, country, status, allowed_channels, allowed_audiences
    FROM material
    WHERE product_id = :product_id
      AND country = :country
    ORDER BY mlr_code
""")

async def check_product_material(
    product_id: str,
    *,
    country: str = "IN",
    channel: str = "in_person",
    indication_context: Optional[str] = None,
    hcp_specialty: Optional[str] = None,
    as_of_date: Optional[date] = None,
) -> dict[str, Any]:
    today = as_of_date or date.today()
    async with engine.connect() as conn:

        resolved = (await conn.execute(_RESOLVE_PRODUCT, {"p": product_id})).scalar()
        pid = resolved or product_id
        rows = (await conn.execute(_QUERY, {"product_id": pid, "country": country})).mappings().all()

    approved: list[dict[str, Any]] = []
    filtered_out: list[dict[str, Any]] = []
    for r in rows:
        m = dict(r)
        m["approval_date"] = r["approval_date"].isoformat() if r["approval_date"] else None
        m["expiration_date"] = r["expiration_date"].isoformat() if r["expiration_date"] else None

        if r["status"] == "WITHDRAWN":
            filtered_out.append({"material_id": r["material_id"], "title": r["title"], "reason": "WITHDRAWN"})
            continue
        if r["status"] == "EXPIRED" or (r["expiration_date"] and r["expiration_date"] < today):
            filtered_out.append({"material_id": r["material_id"], "title": r["title"], "reason": "EXPIRED"})
            continue
        if channel and r["allowed_channels"] and channel not in r["allowed_channels"]:
            filtered_out.append({"material_id": r["material_id"], "title": r["title"], "reason": "WRONG_CHANNEL"})
            continue
        approved.append({
            "material_id": r["material_id"], "mlr_code": r["mlr_code"], "title": r["title"],
            "version": r["version"], "approved_indication": r["approved_indication"],
            "approval_date": m["approval_date"], "expiration_date": m["expiration_date"],
            "status": "APPROVED", "allowed_audiences": r["allowed_audiences"],
        })
    return {"approved_materials": approved, "filtered_out": filtered_out}

async def resolve_material_ids(material_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Look up materials by id and freeze their approval status at share time."""
    if not material_ids:
        return {}
    async with engine.connect() as conn:
        rows = (await conn.execute(
            text("SELECT material_id, mlr_code, title, status FROM material WHERE material_id = ANY(:ids)"),
            {"ids": material_ids},
        )).mappings().all()
    return {r["material_id"]: dict(r) for r in rows}
