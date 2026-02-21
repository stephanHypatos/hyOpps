import json
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin, hash_password
from ..models import UpdateUserRequest

router = APIRouter()


@router.get("")
def list_users(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("""
        SELECT u.id, u.firstname, u.lastname, u.email, u.languages, u.skills, u.roles,
               u.organization_id, u.app_role, u.created_at, o.name as organization_name,
               usc.name as personal_studio_name, usc.studio_id as personal_studio_id
        FROM users u
        LEFT JOIN organizations o ON o.id=u.organization_id
        LEFT JOIN user_studio_companies usc ON usc.user_id=u.id
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["languages"] = json.loads(d.get("languages") or "[]")
        d["skills"] = json.loads(d.get("skills") or "[]")
        d["roles"] = json.loads(d.get("roles") or "[]")
        result.append(d)
    return result


@router.put("/{user_id}")
def update_user(user_id: str, body: UpdateUserRequest, admin=Depends(require_admin)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    fields = {}
    if body.firstname is not None:
        fields["firstname"] = body.firstname
    if body.lastname is not None:
        fields["lastname"] = body.lastname
    if body.email is not None:
        existing = conn.execute("SELECT id FROM users WHERE email=? AND id!=?", (body.email, user_id)).fetchone()
        if existing:
            conn.close()
            raise HTTPException(status_code=409, detail="Email already in use")
        fields["email"] = body.email
    if body.languages is not None:
        fields["languages"] = json.dumps(body.languages)
    if body.skills is not None:
        fields["skills"] = json.dumps(body.skills)
    if body.roles is not None:
        fields["roles"] = json.dumps(body.roles)
    if body.organization_id is not None:
        fields["organization_id"] = body.organization_id or None
    if body.password is not None:
        if len(body.password) < 8:
            conn.close()
            raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
        fields["password_hash"] = hash_password(body.password)
    if body.app_role is not None:
        if body.app_role not in ("admin", "user", "partner_admin"):
            conn.close()
            raise HTTPException(status_code=422, detail="app_role must be 'admin', 'user', or 'partner_admin'")
        fields["app_role"] = body.app_role

    if fields:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id=?", (*fields.values(), user_id))
        conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/{user_id}")
def delete_user(user_id: str, admin=Depends(require_admin)):
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    # Null out non-cascade FK references before deleting
    conn.execute("UPDATE workflow_executions SET user_id=NULL WHERE user_id=?", (user_id,))
    conn.execute("UPDATE workflow_executions SET requested_by=NULL WHERE requested_by=?", (user_id,))
    conn.execute("UPDATE workflow_step_executions SET completed_by=NULL WHERE completed_by=?", (user_id,))
    conn.execute("UPDATE access_grants SET granted_by=NULL WHERE granted_by=?", (user_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/{user_id}/access")
def get_user_access(user_id: str, admin=Depends(require_admin)):
    conn = get_db()
    user = conn.execute(
        "SELECT id, firstname, lastname, email FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    access_grants = conn.execute("""
        SELECT ag.*, r.name as resource_name, r.type as resource_type
        FROM access_grants ag
        JOIN resources r ON r.id=ag.resource_id
        WHERE ag.user_id=? AND ag.revoked_at IS NULL
    """, (user_id,)).fetchall()

    personal_studio = conn.execute(
        "SELECT * FROM user_studio_companies WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()

    return {
        "user": dict(user),
        "access_grants": [dict(g) for g in access_grants],
        "personal_studio_company": dict(personal_studio) if personal_studio else None,
    }
