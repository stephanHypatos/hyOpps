from fastapi import APIRouter, HTTPException, Depends
from ..auth import require_admin

router = APIRouter()


@router.get("/groups")
def list_metabase_groups(admin=Depends(require_admin)):
    """Return all non-system Metabase permission groups for use in admin dropdowns."""
    from ..integrations.metabase import list_groups
    try:
        return list_groups()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Metabase error: {str(e)}")


@router.get("/debug/user/{mb_user_id}")
def debug_metabase_user(mb_user_id: int, admin=Depends(require_admin)):
    """Return the raw Metabase API response for a user — for debugging group_memberships structure."""
    import requests as req
    from ..integrations.metabase import _base, _headers, _TIMEOUT
    try:
        resp = req.get(f"{_base()}/api/user/{mb_user_id}", headers=_headers(), timeout=_TIMEOUT)
        return {"status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
