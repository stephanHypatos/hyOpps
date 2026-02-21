import json
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin

router = APIRouter()


@router.get("")
def list_organizations(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM organizations ORDER BY name ASC").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["account_types"] = json.loads(d.get("account_types") or '["partner"]')
        result.append(d)
    return result


@router.get("/{org_id}")
def get_organization(org_id: str, admin=Depends(require_admin)):
    conn = get_db()
    org = conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        raise HTTPException(status_code=404, detail="Organization not found")

    system_groups = conn.execute(
        "SELECT * FROM system_groups WHERE organization_id=?", (org_id,)
    ).fetchall()
    studio_companies = conn.execute(
        "SELECT * FROM studio_companies WHERE organization_id=?", (org_id,)
    ).fetchall()
    integrations = conn.execute(
        "SELECT * FROM organization_integrations WHERE organization_id=?", (org_id,)
    ).fetchone()
    conn.close()

    result = dict(org)
    result["account_types"] = json.loads(result.get("account_types") or '["partner"]')
    result["system_groups"] = [dict(g) for g in system_groups]
    result["studio_companies"] = [dict(sc) for sc in studio_companies]
    result["integrations"] = dict(integrations) if integrations else None
    return result
