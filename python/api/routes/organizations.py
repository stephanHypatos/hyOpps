import json
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin
from ..models import UpdateOrganizationRequest

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


@router.put("/{org_id}")
def update_organization(org_id: str, body: UpdateOrganizationRequest, admin=Depends(require_admin)):
    conn = get_db()
    org = conn.execute("SELECT id FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        raise HTTPException(status_code=404, detail="Organization not found")

    fields = {}
    if body.name is not None:
        existing = conn.execute("SELECT id FROM organizations WHERE name=? AND id!=?", (body.name, org_id)).fetchone()
        if existing:
            conn.close()
            raise HTTPException(status_code=409, detail="Organization name already in use")
        fields["name"] = body.name
    if body.account_types is not None:
        fields["account_types"] = json.dumps(body.account_types)

    if fields:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE organizations SET {set_clause} WHERE id=?", (*fields.values(), org_id))
        conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/{org_id}")
def delete_organization(org_id: str, admin=Depends(require_admin)):
    conn = get_db()
    org = conn.execute("SELECT id FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        raise HTTPException(status_code=404, detail="Organization not found")
    # Null out nullable FK references
    conn.execute("UPDATE users SET organization_id=NULL WHERE organization_id=?", (org_id,))
    conn.execute("UPDATE workflow_executions SET organization_id=NULL WHERE organization_id=?", (org_id,))
    # Delete child rows with NOT NULL FK (cascade won't help without schema-level CASCADE)
    conn.execute("DELETE FROM organization_integrations WHERE organization_id=?", (org_id,))
    conn.execute("DELETE FROM system_groups WHERE organization_id=?", (org_id,))
    conn.execute("DELETE FROM studio_companies WHERE organization_id=?", (org_id,))
    conn.execute("DELETE FROM organizations WHERE id=?", (org_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
