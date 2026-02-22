import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin
from ..models import UpdateOrganizationRequest, UpsertSystemGroupRequest, UpsertDocumentationRequest

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
    documentation = conn.execute(
        "SELECT * FROM organization_documentation WHERE organization_id=?", (org_id,)
    ).fetchone()
    conn.close()

    result = dict(org)
    result["account_types"] = json.loads(result.get("account_types") or '["partner"]')
    result["system_groups"] = [dict(g) for g in system_groups]
    result["studio_companies"] = [dict(sc) for sc in studio_companies]
    result["integrations"] = dict(integrations) if integrations else None
    result["documentation"] = dict(documentation) if documentation else None
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


@router.put("/{org_id}/groups")
def upsert_org_system_group(org_id: str, body: UpsertSystemGroupRequest, admin=Depends(require_admin)):
    """Create or update a system group record (metabase/teams/slack) for an org."""
    allowed_tools = ("metabase", "teams", "slack")
    if body.tool not in allowed_tools:
        raise HTTPException(status_code=422, detail=f"tool must be one of {allowed_tools}")

    conn = get_db()
    org = conn.execute("SELECT id FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = conn.execute(
        "SELECT id FROM system_groups WHERE organization_id=? AND tool=?",
        (org_id, body.tool)
    ).fetchone()

    now = datetime.utcnow().isoformat()
    if existing:
        fields = {}
        if body.external_id is not None:
            fields["external_id"] = body.external_id
        if body.external_name is not None:
            fields["external_name"] = body.external_name
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE system_groups SET {set_clause} WHERE id=?", (*fields.values(), existing["id"]))
    else:
        conn.execute(
            "INSERT INTO system_groups (id,organization_id,tool,external_name,external_id,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), org_id, body.tool, body.external_name or body.tool, body.external_id, now)
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.put("/{org_id}/documentation")
def upsert_org_documentation(org_id: str, body: UpsertDocumentationRequest, admin=Depends(require_admin)):
    """Create or update the documentation links for an organization."""
    conn = get_db()
    org = conn.execute("SELECT id FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        raise HTTPException(status_code=404, detail="Organization not found")

    existing = conn.execute(
        "SELECT id FROM organization_documentation WHERE organization_id=?", (org_id,)
    ).fetchone()
    now = datetime.utcnow().isoformat()

    if existing:
        conn.execute(
            "UPDATE organization_documentation SET internal_docu=?, generique_docu=?, add_docu=?, updated_at=? WHERE organization_id=?",
            (body.internal_docu, body.generique_docu, body.add_docu, now, org_id)
        )
    else:
        conn.execute(
            "INSERT INTO organization_documentation (id,organization_id,internal_docu,generique_docu,add_docu,updated_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), org_id, body.internal_docu, body.generique_docu, body.add_docu, now)
        )
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
    conn.execute("DELETE FROM organization_documentation WHERE organization_id=?", (org_id,))
    conn.execute("DELETE FROM organizations WHERE id=?", (org_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
