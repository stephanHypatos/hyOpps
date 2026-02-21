import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin
from ..models import CreateExecutionRequest, ManualInputRequest
from ..engine.workflow import start_execution, submit_manual_input, retry_step

router = APIRouter()


def _parse_step(row) -> dict:
    d = dict(row)
    d["manual_input"] = json.loads(d["manual_input"]) if d.get("manual_input") else None
    d["output"] = json.loads(d["output"]) if d.get("output") else None
    return d


@router.get("")
def list_executions(status: str = None, admin=Depends(require_admin)):
    conn = get_db()
    query = """
        SELECT we.*, wd.name as workflow_name, wd.description as workflow_description,
               o.name as organization_name,
               u.email as user_email,
               rb.email as requested_by_email
        FROM workflow_executions we
        JOIN workflow_definitions wd ON wd.id=we.workflow_definition_id
        LEFT JOIN organizations o ON o.id=we.organization_id
        LEFT JOIN users u ON u.id=we.user_id
        LEFT JOIN users rb ON rb.id=we.requested_by
    """
    params = []
    if status:
        query += " WHERE we.status=?"
        params.append(status)
    query += " ORDER BY we.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{execution_id}")
def get_execution(execution_id: str, admin=Depends(require_admin)):
    conn = get_db()
    execution = conn.execute("""
        SELECT we.*, wd.name as workflow_name, wd.description as workflow_description,
               o.name as organization_name,
               u.email as user_email,
               rb.email as requested_by_email
        FROM workflow_executions we
        JOIN workflow_definitions wd ON wd.id=we.workflow_definition_id
        LEFT JOIN organizations o ON o.id=we.organization_id
        LEFT JOIN users u ON u.id=we.user_id
        LEFT JOIN users rb ON rb.id=we.requested_by
        WHERE we.id=?
    """, (execution_id,)).fetchone()

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


@router.post("", status_code=201)
def create_execution(body: CreateExecutionRequest, admin=Depends(require_admin)):
    conn = get_db()
    wf_def = conn.execute(
        "SELECT * FROM workflow_definitions WHERE name=?", (body.workflow_type,)
    ).fetchone()
    if not wf_def:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Unknown workflow type: {body.workflow_type}")

    execution_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO workflow_executions (id,workflow_definition_id,requested_by,status,created_at) VALUES (?,?,?,?,?)",
        (execution_id, wf_def["id"], admin["id"], "pending", now)
    )
    conn.commit()
    conn.close()

    start_execution(execution_id)

    conn = get_db()
    result = dict(conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone())
    conn.close()
    return result


@router.post("/{execution_id}/steps/{step_exec_id}/input")
def submit_step_input(
    execution_id: str,
    step_exec_id: str,
    body: ManualInputRequest,
    admin=Depends(require_admin)
):
    try:
        submit_manual_input(execution_id, step_exec_id, body.to_dict(), admin["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_db()
    result = dict(conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone())
    conn.close()
    return result


@router.post("/{execution_id}/steps/{step_exec_id}/retry")
def retry_step_endpoint(
    execution_id: str,
    step_exec_id: str,
    admin=Depends(require_admin)
):
    try:
        retry_step(execution_id, step_exec_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_db()
    result = dict(conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone())
    conn.close()
    return result
