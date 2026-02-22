import json
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin, hash_password
from ..models import UpdateUserRequest, MetabaseGroupRequest

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


@router.get("/{user_id}/metabase")
def get_user_metabase_status(user_id: str, admin=Depends(require_admin)):
    """Return the user's stored Metabase ID and current group memberships."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mb_user_id = user["metabase_user_id"]
    if not mb_user_id:
        return {"metabase_user_id": None, "email": user["email"], "group_memberships": []}

    from ..integrations.metabase import get_user_group_memberships
    try:
        memberships = get_user_group_memberships(mb_user_id)
        return {"metabase_user_id": mb_user_id, "email": user["email"], "group_memberships": memberships}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metabase error: {str(e)}")


@router.post("/{user_id}/metabase")
def add_user_to_metabase(user_id: str, body: MetabaseGroupRequest, admin=Depends(require_admin)):
    """
    Add user to a Metabase permission group.
    If the user has no stored Metabase ID, find or create their account first and persist the ID.
    """
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    from ..integrations.metabase import get_user_by_email, create_user, add_to_group
    try:
        mb_user_id = user["metabase_user_id"]
        account_created = False

        if not mb_user_id:
            # Check if user already exists in Metabase by email
            mb_user = get_user_by_email(user["email"])
            if mb_user:
                mb_user_id = mb_user["id"]
            else:
                new_user = create_user(user["email"], user["firstname"], user["lastname"])
                mb_user_id = new_user["id"]
                account_created = True
            # Persist so future calls skip the lookup
            conn.execute("UPDATE users SET metabase_user_id=? WHERE id=?", (mb_user_id, user_id))
            conn.commit()

        conn.close()
        add_to_group(mb_user_id, body.group_id)
        return {"ok": True, "metabase_user_id": mb_user_id, "group_id": body.group_id, "account_created": account_created}
    except HTTPException:
        conn.close()
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"Metabase error: {str(e)}")


@router.delete("/{user_id}/metabase/{group_id}")
def remove_user_from_metabase(user_id: str, group_id: int, admin=Depends(require_admin)):
    """Remove the user from a specific Metabase permission group."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mb_user_id = user["metabase_user_id"]
    if not mb_user_id:
        raise HTTPException(status_code=404, detail="User has no stored Metabase account ID")

    from ..integrations.metabase import remove_from_group
    try:
        removed = remove_from_group(mb_user_id, group_id)
        return {"ok": True, "removed": removed}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metabase error: {str(e)}")


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
