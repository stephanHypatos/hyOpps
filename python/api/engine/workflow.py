"""
Workflow engine — drives step-by-step execution.

Each call to advance() is synchronous and runs in a background thread
so the HTTP response returns immediately.
"""

import json
import uuid
import threading
from datetime import datetime
from typing import Any

from ..database import get_db
from ..integrations.steps import execute_step

_lock = threading.Lock()


# ── helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def _build_context(execution_id: str, conn) -> dict[str, Any]:
    """Merge outputs + manual_inputs from all completed steps into one context dict."""
    rows = conn.execute(
        "SELECT output, manual_input FROM workflow_step_executions WHERE execution_id=? AND status='completed'",
        (execution_id,)
    ).fetchall()
    ctx: dict[str, Any] = {}
    for row in rows:
        if row["output"]:
            ctx.update(json.loads(row["output"]))
        if row["manual_input"]:
            ctx.update(json.loads(row["manual_input"]))
    return ctx


# ── side-effect writers ────────────────────────────────────────────────────

def _apply_step_output(execution_id: str, step_name: str, output: dict, conn) -> None:
    """Immediately persist relevant fields from an auto step's output."""
    execution = conn.execute(
        "SELECT organization_id, user_id FROM workflow_executions WHERE id=?", (execution_id,)
    ).fetchone()
    if not execution:
        return
    org_id = execution["organization_id"]
    user_id = execution["user_id"]
    now = _now()

    if step_name == "create_studio_user_company" and user_id and output.get("studio_user_company_id"):
        conn.execute(
            "INSERT OR IGNORE INTO user_studio_companies (id, user_id, studio_id, name, created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), user_id,
             output["studio_user_company_id"],
             output.get("studio_user_company_name", "Personal Studio"),
             now)
        )
        return

    if not org_id:
        return

    if step_name == "clone_metabase_collection" and output.get("metabase_collection_id"):
        conn.execute(
            "UPDATE organization_integrations SET metabase_collection_id=?, updated_at=? WHERE organization_id=?",
            (output["metabase_collection_id"], now, org_id)
        )

    if step_name == "create_metabase_group" and output.get("metabase_group_id"):
        conn.execute(
            "INSERT OR IGNORE INTO system_groups (id,organization_id,tool,external_name,external_id,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), org_id, "metabase", output.get("metabase_group_name", "metabase"), output["metabase_group_id"], now)
        )

    if step_name == "create_teams_channel" and output.get("teams_channel_id"):
        conn.execute(
            "INSERT OR IGNORE INTO system_groups (id,organization_id,tool,external_name,external_id,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), org_id, "teams", output.get("teams_channel_name", "teams"), output["teams_channel_id"], now)
        )

    if step_name == "create_slack_group" and output.get("slack_group_id"):
        conn.execute(
            "INSERT OR IGNORE INTO system_groups (id,organization_id,tool,external_name,external_id,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), org_id, "slack", output.get("slack_group_handle", "slack"), output["slack_group_id"], now)
        )


def _finalize_new_partner(execution_id: str, conn) -> None:
    execution = conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone()
    if not execution or not execution["organization_id"]:
        return
    org_id = execution["organization_id"]
    ctx = _build_context(execution_id, conn)
    now = _now()

    existing = conn.execute(
        "SELECT id FROM organization_integrations WHERE organization_id=?", (org_id,)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO organization_integrations (id,organization_id,keycloak_confirmed,keycloak_cluster,metabase_collection_id,lms_confirmed,updated_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), org_id,
             1 if ctx.get("keycloak_confirmed") else 0,
             ctx.get("keycloak_cluster"),
             ctx.get("metabase_collection_id"),
             1 if ctx.get("lms_confirmed") else 0,
             now)
        )
    else:
        conn.execute(
            "UPDATE organization_integrations SET keycloak_confirmed=?,keycloak_cluster=?,metabase_collection_id=?,lms_confirmed=?,updated_at=? WHERE organization_id=?",
            (1 if ctx.get("keycloak_confirmed") else 0,
             ctx.get("keycloak_cluster"),
             ctx.get("metabase_collection_id"),
             1 if ctx.get("lms_confirmed") else 0,
             now, org_id)
        )

    for tool, id_key, name_key in [
        ("metabase", "metabase_group_id", "metabase_group_name"),
        ("teams",    "teams_channel_id",  "teams_channel_name"),
        ("slack",    "slack_group_id",    "slack_group_handle"),
    ]:
        if ctx.get(id_key):
            conn.execute(
                "INSERT OR IGNORE INTO system_groups (id,organization_id,tool,external_name,external_id,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), org_id, tool, ctx.get(name_key, tool), ctx[id_key], now)
            )


def _finalize_new_partner_user(execution_id: str, conn) -> None:
    execution = conn.execute("SELECT * FROM workflow_executions WHERE id=?", (execution_id,)).fetchone()
    if not execution or not execution["user_id"] or not execution["requested_by"]:
        return
    user_id = execution["user_id"]
    requested_by = execution["requested_by"]
    ctx = _build_context(execution_id, conn)
    now = _now()

    resources = conn.execute("SELECT id FROM resources").fetchall()
    for r in resources:
        conn.execute(
            "INSERT OR IGNORE INTO access_grants (id,user_id,resource_id,permission,granted_by,granted_at,execution_id) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), user_id, r["id"], "read", requested_by, now, execution_id)
        )


# ── manual input handlers ──────────────────────────────────────────────────

def _handle_input_studio_companies(execution_id: str, data: dict, conn) -> None:
    org_name = data.get("organization_name", "")
    if not org_name:
        return
    now = _now()

    org = conn.execute("SELECT id FROM organizations WHERE name=?", (org_name,)).fetchone()
    if not org:
        org_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO organizations (id,name,account_types,created_at) VALUES (?,?,?,?)",
            (org_id, org_name, '["partner"]', now)
        )
    else:
        org_id = org["id"]

    conn.execute("UPDATE workflow_executions SET organization_id=? WHERE id=?", (org_id, execution_id))

    if not conn.execute("SELECT id FROM organization_integrations WHERE organization_id=?", (org_id,)).fetchone():
        conn.execute(
            "INSERT INTO organization_integrations (id,organization_id,updated_at) VALUES (?,?,?)",
            (str(uuid.uuid4()), org_id, now)
        )

    for env, id_key, name_key in [
        ("test", "studio_company_id_test", "studio_company_name_test"),
        ("prod", "studio_company_id_prod", "studio_company_name_prod"),
    ]:
        studio_id = data.get(id_key, "")
        if studio_id:
            name = data.get(name_key) or f"{org_name} {env.upper()}"
            conn.execute(
                "INSERT OR IGNORE INTO studio_companies (id,organization_id,studio_id,name,environment,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), org_id, studio_id, name, env, now)
            )


def _handle_select_organization(execution_id: str, data: dict, conn) -> None:
    org_id = data.get("organization_id", "")
    if org_id:
        conn.execute("UPDATE workflow_executions SET organization_id=? WHERE id=?", (org_id, execution_id))


def _handle_input_user_details(execution_id: str, data: dict, conn) -> None:
    email = data.get("email", "")
    if not email:
        return
    now = _now()
    execution = conn.execute("SELECT organization_id FROM workflow_executions WHERE id=?", (execution_id,)).fetchone()
    org_id = execution["organization_id"] if execution else None

    user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        import bcrypt, secrets
        user_id = str(uuid.uuid4())
        rand_pw = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (id,firstname,lastname,email,languages,skills,roles,organization_id,app_role,password_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id,
             data.get("firstname", ""),
             data.get("lastname", ""),
             email,
             json.dumps(data.get("languages", [])),
             json.dumps(data.get("skills", [])),
             json.dumps(data.get("roles", [])),
             org_id,
             "user",
             rand_pw,
             now)
        )
    else:
        user_id = user["id"]

    conn.execute("UPDATE workflow_executions SET user_id=? WHERE id=?", (user_id, execution_id))


def _handle_trigger_infrabot(execution_id: str, data: dict, conn) -> None:
    execution = conn.execute("SELECT organization_id FROM workflow_executions WHERE id=?", (execution_id,)).fetchone()
    if not execution or not execution["organization_id"]:
        return
    conn.execute(
        "UPDATE organization_integrations SET keycloak_confirmed=1, keycloak_cluster=?, updated_at=? WHERE organization_id=?",
        (data.get("keycloak_cluster"), _now(), execution["organization_id"])
    )


# ── core advance logic ─────────────────────────────────────────────────────

def _advance(execution_id: str) -> None:
    """Run the next pending step. Called in a background thread."""
    with _lock:
        conn = get_db()
        try:
            execution = conn.execute(
                "SELECT status FROM workflow_executions WHERE id=?", (execution_id,)
            ).fetchone()
            if not execution or execution["status"] in ("completed", "failed"):
                return

            next_step = conn.execute("""
                SELECT wse.id, wse.step_order, wsd.name as step_name, wsd.type as step_type, wsd.label
                FROM workflow_step_executions wse
                JOIN workflow_step_definitions wsd ON wsd.id = wse.step_definition_id
                WHERE wse.execution_id=? AND wse.status='pending'
                ORDER BY wse.step_order ASC LIMIT 1
            """, (execution_id,)).fetchone()

            if not next_step:
                # All done
                now = _now()
                conn.execute(
                    "UPDATE workflow_executions SET status='completed', completed_at=? WHERE id=?",
                    (now, execution_id)
                )
                wf = conn.execute(
                    "SELECT wd.name FROM workflow_definitions wd JOIN workflow_executions we ON we.workflow_definition_id=wd.id WHERE we.id=?",
                    (execution_id,)
                ).fetchone()
                if wf:
                    if wf["name"] == "new_partner":
                        _finalize_new_partner(execution_id, conn)
                    elif wf["name"] == "new_partner_user":
                        _finalize_new_partner_user(execution_id, conn)
                conn.commit()
                return

            now = _now()
            conn.execute(
                "UPDATE workflow_step_executions SET status='running', started_at=? WHERE id=?",
                (now, next_step["id"])
            )
            conn.execute(
                "UPDATE workflow_executions SET current_step_order=?, status='running' WHERE id=?",
                (next_step["step_order"], execution_id)
            )
            conn.commit()

            if next_step["step_type"] == "manual":
                conn.execute(
                    "UPDATE workflow_step_executions SET status='awaiting_input' WHERE id=?",
                    (next_step["id"],)
                )
                conn.execute(
                    "UPDATE workflow_executions SET status='awaiting_input' WHERE id=?",
                    (execution_id,)
                )
                conn.commit()
                return

            # Auto step
            ctx = _build_context(execution_id, conn)
            result = execute_step(next_step["step_name"], ctx)
            finished_at = _now()

            if result["success"]:
                output = result.get("output", {})
                conn.execute(
                    "UPDATE workflow_step_executions SET status='completed', output=?, completed_at=? WHERE id=?",
                    (json.dumps(output), finished_at, next_step["id"])
                )
                _apply_step_output(execution_id, next_step["step_name"], output, conn)
                conn.commit()
                # Recurse for next step (still inside the lock — ok since we use one thread)
                _advance_unlocked(execution_id, conn)
            else:
                conn.execute(
                    "UPDATE workflow_step_executions SET status='failed', error=?, completed_at=? WHERE id=?",
                    (result.get("error", "Unknown error"), finished_at, next_step["id"])
                )
                conn.execute("UPDATE workflow_executions SET status='failed' WHERE id=?", (execution_id,))
                conn.commit()

        finally:
            conn.close()


def _advance_unlocked(execution_id: str, conn) -> None:
    """Advance without acquiring the lock again (called from within _advance)."""
    execution = conn.execute(
        "SELECT status FROM workflow_executions WHERE id=?", (execution_id,)
    ).fetchone()
    if not execution or execution["status"] in ("completed", "failed"):
        return

    next_step = conn.execute("""
        SELECT wse.id, wse.step_order, wsd.name as step_name, wsd.type as step_type
        FROM workflow_step_executions wse
        JOIN workflow_step_definitions wsd ON wsd.id = wse.step_definition_id
        WHERE wse.execution_id=? AND wse.status='pending'
        ORDER BY wse.step_order ASC LIMIT 1
    """, (execution_id,)).fetchone()

    if not next_step:
        now = _now()
        conn.execute(
            "UPDATE workflow_executions SET status='completed', completed_at=? WHERE id=?",
            (now, execution_id)
        )
        wf = conn.execute(
            "SELECT wd.name FROM workflow_definitions wd JOIN workflow_executions we ON we.workflow_definition_id=wd.id WHERE we.id=?",
            (execution_id,)
        ).fetchone()
        if wf:
            if wf["name"] == "new_partner":
                _finalize_new_partner(execution_id, conn)
            elif wf["name"] == "new_partner_user":
                _finalize_new_partner_user(execution_id, conn)
        conn.commit()
        return

    now = _now()
    conn.execute(
        "UPDATE workflow_step_executions SET status='running', started_at=? WHERE id=?",
        (now, next_step["id"])
    )
    conn.execute(
        "UPDATE workflow_executions SET current_step_order=?, status='running' WHERE id=?",
        (next_step["step_order"], execution_id)
    )

    if next_step["step_type"] == "manual":
        conn.execute("UPDATE workflow_step_executions SET status='awaiting_input' WHERE id=?", (next_step["id"],))
        conn.execute("UPDATE workflow_executions SET status='awaiting_input' WHERE id=?", (execution_id,))
        conn.commit()
        return

    ctx = _build_context(execution_id, conn)
    result = execute_step(next_step["step_name"], ctx)
    finished_at = _now()

    if result["success"]:
        output = result.get("output", {})
        conn.execute(
            "UPDATE workflow_step_executions SET status='completed', output=?, completed_at=? WHERE id=?",
            (json.dumps(output), finished_at, next_step["id"])
        )
        _apply_step_output(execution_id, next_step["step_name"], output, conn)
        conn.commit()
        _advance_unlocked(execution_id, conn)  # next step
    else:
        conn.execute(
            "UPDATE workflow_step_executions SET status='failed', error=?, completed_at=? WHERE id=?",
            (result.get("error", "Unknown error"), finished_at, next_step["id"])
        )
        conn.execute("UPDATE workflow_executions SET status='failed' WHERE id=?", (execution_id,))
        conn.commit()


# ── public API ─────────────────────────────────────────────────────────────

def start_execution(execution_id: str) -> None:
    """Create step records and kick off the workflow in a background thread."""
    conn = get_db()
    try:
        execution = conn.execute(
            "SELECT workflow_definition_id FROM workflow_executions WHERE id=?", (execution_id,)
        ).fetchone()
        steps = conn.execute(
            "SELECT * FROM workflow_step_definitions WHERE workflow_definition_id=? ORDER BY step_order ASC",
            (execution["workflow_definition_id"],)
        ).fetchall()
        for step in steps:
            conn.execute(
                "INSERT INTO workflow_step_executions (id,execution_id,step_definition_id,step_order,status) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), execution_id, step["id"], step["step_order"], "pending")
            )
        conn.execute("UPDATE workflow_executions SET status='running' WHERE id=?", (execution_id,))
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(target=_advance, args=(execution_id,), daemon=True)
    thread.start()
    thread.join(timeout=2)  # wait briefly so first step resolves before returning


def submit_manual_input(execution_id: str, step_exec_id: str, data: dict, completed_by: str) -> None:
    conn = get_db()
    try:
        step_exec = conn.execute(
            "SELECT wse.*, wsd.name as step_name FROM workflow_step_executions wse "
            "JOIN workflow_step_definitions wsd ON wsd.id=wse.step_definition_id "
            "WHERE wse.id=? AND wse.execution_id=? AND wse.status='awaiting_input'",
            (step_exec_id, execution_id)
        ).fetchone()
        if not step_exec:
            raise ValueError("Step not found or not awaiting input")

        step_name = step_exec["step_name"]

        if step_name == "input_studio_companies":
            _handle_input_studio_companies(execution_id, data, conn)
        elif step_name == "select_organization":
            _handle_select_organization(execution_id, data, conn)
        elif step_name == "input_user_details":
            _handle_input_user_details(execution_id, data, conn)
        elif step_name == "trigger_infrabot":
            _handle_trigger_infrabot(execution_id, data, conn)

        conn.execute(
            "UPDATE workflow_step_executions SET status='completed', manual_input=?, completed_by=?, completed_at=? WHERE id=?",
            (json.dumps(data), completed_by, _now(), step_exec_id)
        )
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(target=_advance, args=(execution_id,), daemon=True)
    thread.start()
    thread.join(timeout=2)


def retry_step(execution_id: str, step_exec_id: str) -> None:
    conn = get_db()
    try:
        step_exec = conn.execute(
            "SELECT id FROM workflow_step_executions WHERE id=? AND execution_id=? AND status='failed'",
            (step_exec_id, execution_id)
        ).fetchone()
        if not step_exec:
            raise ValueError("Step not found or not in failed state")
        conn.execute(
            "UPDATE workflow_step_executions SET status='pending', error=NULL, started_at=NULL, completed_at=NULL WHERE id=?",
            (step_exec_id,)
        )
        conn.execute("UPDATE workflow_executions SET status='running' WHERE id=?", (execution_id,))
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(target=_advance, args=(execution_id,), daemon=True)
    thread.start()
    thread.join(timeout=2)
