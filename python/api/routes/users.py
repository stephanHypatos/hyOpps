import json
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth import require_admin

router = APIRouter()


@router.get("")
def list_users(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("""
        SELECT u.id, u.firstname, u.lastname, u.email, u.languages, u.skills, u.roles,
               u.organization_id, u.app_role, u.created_at, o.name as organization_name
        FROM users u
        LEFT JOIN organizations o ON o.id=u.organization_id
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

    studio_access = conn.execute("""
        SELECT usa.*, sc.studio_id, sc.name, sc.environment, o.name as organization_name
        FROM user_studio_access usa
        JOIN studio_companies sc ON sc.id=usa.studio_company_id
        JOIN organizations o ON o.id=sc.organization_id
        WHERE usa.user_id=? AND usa.revoked_at IS NULL
    """, (user_id,)).fetchall()
    conn.close()

    return {
        "user": dict(user),
        "access_grants": [dict(g) for g in access_grants],
        "studio_access": [dict(s) for s in studio_access],
    }
