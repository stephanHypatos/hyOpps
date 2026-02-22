"""
Metabase integration — user provisioning and permission group membership management.

Authentication: API key sent as `x-api-key` header (requires Metabase v0.46+).

Credentials (python/.env):
    METABASE_URL=https://your-instance.metabase.com
    METABASE_API_KEY=mb_your_api_key_here
"""

import os
from typing import Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_TIMEOUT = 10

# Built-in Metabase system groups that should not be shown in the admin UI
_SYSTEM_GROUP_IDS = {1, 2}  # All Users, Administrators


def _base() -> str:
    return os.environ.get("METABASE_URL", "").rstrip("/")


def _headers() -> dict:
    return {
        "x-api-key": os.environ.get("METABASE_API_KEY", ""),
        "Content-Type": "application/json",
    }


def _check_config() -> None:
    if not _base():
        raise RuntimeError("METABASE_URL is not configured")
    if not os.environ.get("METABASE_API_KEY"):
        raise RuntimeError("METABASE_API_KEY is not configured")


# ── User lookup ─────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[dict]:
    """Return the Metabase user dict for the given email, or None if not found."""
    resp = requests.get(
        f"{_base()}/api/user",
        params={"query": email},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # Metabase v0.41+ wraps results: {"data": [...], "total": ...}
    users = data["data"] if isinstance(data, dict) and "data" in data else data
    normalized = email.strip().lower()
    for u in users:
        if u.get("email", "").strip().lower() == normalized:
            return u
    return None


def create_user(email: str, firstname: str, lastname: str) -> dict:
    """Create a new Metabase user and return the created user dict."""
    resp = requests.post(
        f"{_base()}/api/user",
        json={"email": email, "first_name": firstname, "last_name": lastname},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ── Group listing ────────────────────────────────────────────────────────────

def list_groups() -> list:
    """Return all Metabase permission groups, excluding built-in system groups."""
    _check_config()
    resp = requests.get(
        f"{_base()}/api/permissions/group",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    groups = resp.json()
    return [
        {"id": g["id"], "name": g["name"]}
        for g in groups
        if g["id"] not in _SYSTEM_GROUP_IDS
    ]


# ── Membership management ────────────────────────────────────────────────────

def add_to_group(user_id: int, group_id: int) -> None:
    """Add a Metabase user to a permission group."""
    resp = requests.post(
        f"{_base()}/api/permissions/membership",
        json={"group_id": group_id, "user_id": user_id},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    if resp.status_code in (200, 201):
        return
    if resp.status_code == 400:
        try:
            detail = resp.json().get("message", resp.text)
        except Exception:
            detail = resp.text
        # Metabase returns 400 when the user is already in the group
        if "already" in str(detail).lower():
            return  # idempotent no-op
        raise RuntimeError(f"Metabase refused membership (400): {detail}")
    resp.raise_for_status()


def _find_membership_id(mb_user_id: int, group_id: int) -> Optional[int]:
    """
    Lookup the membership_id for a user in a specific group.
    GET /api/permissions/membership returns {user_id_str: [{membership_id, group_id, user_id, ...}]}.
    """
    resp = requests.get(
        f"{_base()}/api/permissions/membership",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # Keyed by user_id string; each entry has group_id and membership_id
    members = data.get(str(mb_user_id), [])
    for m in members:
        if m.get("group_id") == group_id:
            return m.get("membership_id")
    return None


def remove_from_group(mb_user_id: int, group_id: int) -> bool:
    """
    Remove a Metabase user from a permission group.
    Returns True if removed, False if the membership didn't exist.
    """
    membership_id = _find_membership_id(mb_user_id, group_id)
    if membership_id is None:
        return False
    resp = requests.delete(
        f"{_base()}/api/permissions/membership/{membership_id}",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return True


def get_user_group_memberships(mb_user_id: int) -> list:
    """
    Return all non-system permission group memberships for a Metabase user.
    Each entry: {group_id, group_name, membership_id}
    Uses GET /api/user/:id which directly includes group_memberships for the user,
    then cross-references GET /permissions/group for group names and existence checks.
    """
    # Fetch the user directly — response includes user_group_memberships: [{id: group_id, is_group_manager: bool}, ...]
    user_resp = requests.get(
        f"{_base()}/api/user/{mb_user_id}",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    user_resp.raise_for_status()
    # Metabase returns "user_group_memberships" where each entry's "id" is the group_id
    raw_memberships = user_resp.json().get("user_group_memberships", [])
    if not raw_memberships:
        return []

    # Build group name + existence lookup
    groups_resp = requests.get(
        f"{_base()}/api/permissions/group",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    groups_resp.raise_for_status()
    group_names = {g["id"]: g["name"] for g in groups_resp.json()}

    seen: set = set()
    result = []
    for m in raw_memberships:
        group_id = m.get("id")  # "id" in this response is the group_id
        if group_id is None or group_id in _SYSTEM_GROUP_IDS:
            continue
        if group_id not in group_names:
            continue  # group was deleted in Metabase
        if group_id in seen:
            continue  # deduplicate
        seen.add(group_id)
        result.append({
            "group_id": group_id,
            "group_name": group_names[group_id],
        })
    return result


# ── High-level provisioning ──────────────────────────────────────────────────

def provision_user(email: str, firstname: str, lastname: str, group_id: int) -> dict:
    """
    Ensure the user exists in Metabase and is a member of the given permission group.

    - User exists  → add to group (idempotent — 400 from Metabase treated as no-op).
    - User missing → create user, then add to group.

    Returns:
        {email, metabase_user_id, metabase_group_id, user_exists, created}
    """
    _check_config()
    normalized = email.strip().lower()

    existing = get_user_by_email(normalized)
    if existing:
        add_to_group(existing["id"], group_id)
        return {
            "email": normalized,
            "metabase_user_id": existing["id"],
            "metabase_group_id": group_id,
            "user_exists": True,
            "created": False,
        }

    new_user = create_user(normalized, firstname, lastname)
    add_to_group(new_user["id"], group_id)
    return {
        "email": normalized,
        "metabase_user_id": new_user["id"],
        "metabase_group_id": group_id,
        "user_exists": False,
        "created": True,
    }
