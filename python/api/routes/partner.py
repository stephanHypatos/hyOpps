"""
Partner-admin routes — scoped to the partner_admin's own organization.
Accessible to both 'partner_admin' and 'admin' roles.
"""

import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_partner_admin
from ..models import ManualInputRequest
from ..engine.workflow import start_execution, submit_manual_input, retry_step

router = APIRouter()


def _parse_step(row) -> dict:
    d = dict(row)
    d["manual_input"] = json.loads(d["manual_input"]) if d.get("manual_input") else None
    d["output"] = json.loads(d["output"]) if d.get("output") else None
    return d


def _get_org_id(user: dict) -> str:
    """Return the org_id to scope queries. Admins must not hit this path without an org."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization assigned")
    return org_id


# ── Organization overview ────────────────────────────────────────────────────

@router.get("/me")
def get_partner_overview(user=Depends(require_partner_admin)):
    org_id = _get_org_id(user)
    conn = get_db()
    org = conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        raise HTTPException(status_code=404, detail="Organization not found")

    users = conn.execute(
        "SELECT id, firstname, lastname, email, app_role, created_at FROM users WHERE organization_id=? ORDER BY created_at DESC",
        (org_id,)
    ).fetchall()
    integrations = conn.execute(
        "SELECT * FROM organization_integrations WHERE organization_id=?", (org_id,)
    ).fetchone()
    conn.close()

    result = dict(org)
    result["account_types"] = json.loads(result.get("account_types") or '["partner"]')
    result["users"] = [dict(u) for u in users]
    result["integrations"] = dict(integrations) if integrations else None
    return result


# ── Executions (scoped to org) ───────────────────────────────────────────────

@router.get("/executions")
def list_partner_executions(user=Depends(require_partner_admin)):
    org_id = _get_org_id(user)
    conn = get_db()
    rows = conn.execute("""
        SELECT we.*, wd.name as workflow_name,
               u.email as user_email,
               rb.email as requested_by_email
        FROM workflow_executions we
        JOIN workflow_definitions wd ON wd.id=we.workflow_definition_id
        LEFT JOIN users u ON u.id=we.user_id
        LEFT JOIN users rb ON rb.id=we.requested_by
        WHERE we.organization_id=? AND wd.name='new_partner_user'
        ORDER BY we.created_at DESC
    """, (org_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/executions/{execution_id}")
def get_partner_execution(execution_id: str, user=Depends(require_partner_admin)):
    org_id = _get_org_id(user)
    conn = get_db()
    execution = conn.execute("""
        SELECT we.*, wd.name as workflow_name,
               o.name as organization_name,
               u.email as user_email,
               rb.email as requested_by_email
        FROM workflow_executions we
        JOIN workflow_definitions wd ON wd.id=we.workflow_definition_id
        LEFT JOIN organizations o ON o.id=we.organization_id
        LEFT JOIN users u ON u.id=we.user_id
        LEFT JOIN users rb ON rb.id=we.requested_by
        WHERE we.id=? AND we.organization_id=?
    """, (execution_id, org_id)).fetchone()

    if not execution:
        conn.close()
        raise HTTPException(status_code=404, detail="Execution not found")

    steps = conn.execute("""
        SELECT wse.*, wsd.name as step_name, wsd.label, wsd.type as step_type, wsd.description,
               cb.email as completed_by_email
        FROM workflow_step_executions wse
        JOIN workflow_step_definitions wsd ON wsd.id=wse.step_definition_id
        LEFT JOIN users cb ON cb.id=wse.completed_by
        WHERE wse.execution_id=?
        ORDER BY wse.step_order ASC
    """, (execution_id,)).fetchall()
    conn.close()

    result = dict(execution)
    result["steps"] = [_parse_step(s) for s in steps]
    return result


@router.post("/executions", status_code=201)
def create_partner_execution(user=Depends(require_partner_admin)):
    """
    Start a new_partner_user workflow for the partner_admin's org.
    The select_organization step is auto-submitted so the workflow
    lands at input_user_details immediately.
    """
    org_id = _get_org_id(user)
    conn = get_db()
    wf_def = conn.execute(
        "SELECT * FROM workflow_definitions WHERE name='new_partner_user'"
    ).fetchone()
    if not wf_def:
        conn.close()
        raise HTTPException(status_code=500, detail="new_partner_user workflow not found")

    execution_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO workflow_executions (id,workflow_definition_id,requested_by,status,created_at) VALUES (?,?,?,?,?)",
        (execution_id, wf_def["id"], user["id"], "pending", now)
    )
    conn.commit()
    conn.close()

    # Start the workflow — will pause at select_organization (manual step)
    start_execution(execution_id)

    # Auto-submit select_organization with the partner's org
    conn = get_db()
    select_org_step = conn.execute("""
        SELECT wse.id FROM workflow_step_executions wse
        JOIN workflow_step_definitions wsd ON wsd.id=wse.step_definition_id
        WHERE wse.execution_id=? AND wsd.name='select_organization'
          AND wse.status='awaiting_input'
    """, (execution_id,)).fetchone()
    conn.close()

    if select_org_step:
        submit_manual_input(
            execution_id,
            select_org_step["id"],
            {"organization_id": org_id},
            user["id"]
        )

    conn = get_db()
    result = dict(conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone())
    conn.close()
    return result


@router.post("/executions/{execution_id}/steps/{step_exec_id}/input")
def submit_partner_step_input(
    execution_id: str,
    step_exec_id: str,
    body: ManualInputRequest,
    user=Depends(require_partner_admin)
):
    org_id = _get_org_id(user)
    # Verify execution belongs to this org
    conn = get_db()
    ex = conn.execute(
        "SELECT id FROM workflow_executions WHERE id=? AND organization_id=?", (execution_id, org_id)
    ).fetchone()
    conn.close()
    if not ex:
        raise HTTPException(status_code=404, detail="Execution not found")

    try:
        submit_manual_input(execution_id, step_exec_id, body.to_dict(), user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_db()
    result = dict(conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone())
    conn.close()
    return result


@router.post("/executions/{execution_id}/steps/{step_exec_id}/retry")
def retry_partner_step(
    execution_id: str,
    step_exec_id: str,
    user=Depends(require_partner_admin)
):
    org_id = _get_org_id(user)
    conn = get_db()
    ex = conn.execute(
        "SELECT id FROM workflow_executions WHERE id=? AND organization_id=?", (execution_id, org_id)
    ).fetchone()
    conn.close()
    if not ex:
        raise HTTPException(status_code=404, detail="Execution not found")

    try:
        retry_step(execution_id, step_exec_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_db()
    result = dict(conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone())
    conn.close()
    return result
