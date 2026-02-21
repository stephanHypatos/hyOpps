"""
Microsoft Teams integration via Microsoft Graph API.

Uses OAuth 2.0 client credentials flow to authenticate as the registered
Azure AD application, then:
  1. Calls the invitation API (handles both new and existing guest users)
  2. Adds the user as a member of the configured Teams team

Required Graph API application permissions (with admin consent):
    User.Invite.All          - to invite / look up guest users
    TeamMember.ReadWrite.All - to add members to the Teams team

Required env vars (set in python/.env):
    AZURE_TENANT_ID      - Directory (tenant) ID
    AZURE_CLIENT_ID      - Application (client) ID
    AZURE_CLIENT_SECRET  - Client secret value
    TEAMS_TEAM_ID        - Microsoft 365 Group / Team ID
"""

import os

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; values must come from OS environment


# ── Auth ────────────────────────────────────────────────────────────────────

def _get_access_token() -> str:
    tenant_id = os.environ.get("AZURE_TENANT_ID", "")
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")

    if not all([tenant_id, client_id, client_secret]):
        raise RuntimeError(
            "Teams integration not configured. "
            "Set AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET in python/.env"
        )

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── User invite / resolve ─────────────────────────────────────────────────────

def _get_or_invite_user(email: str, display_name: str, token: str) -> tuple:
    """
    Call the Graph invitations endpoint.
    - New user  → creates a B2B guest, returns their new object ID.
    - Existing guest → returns their existing object ID without re-sending invite.
    Returns (user_object_id: str, newly_invited: bool).
    Requires: User.Invite.All
    """
    resp = requests.post(
        "https://graph.microsoft.com/v1.0/invitations",
        json={
            "invitedUserEmailAddress": email,
            "invitedUserDisplayName": display_name,
            # Redirect target after the guest accepts the invite
            "inviteRedirectUrl": "https://teams.microsoft.com",
            # Suppress the Azure default email — the workflow handles communication
            "sendInvitationMessage": False,
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    user_id = data["invitedUser"]["id"]
    # status == "PendingAcceptance" → new invite; anything else → user already existed
    newly_invited = data.get("status") == "PendingAcceptance"
    return user_id, newly_invited


# ── Team membership ──────────────────────────────────────────────────────────

def _add_to_team(team_id: str, user_object_id: str, token: str) -> None:
    """
    Add the user to the Teams team as a regular member.
    409 means already a member — treated as success.
    Requires: TeamMember.ReadWrite.All
    """
    resp = requests.post(
        f"https://graph.microsoft.com/v1.0/teams/{team_id}/members",
        json={
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": [],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_object_id}')",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if resp.status_code == 409:
        return  # already a member — idempotent
    resp.raise_for_status()


# ── Public interface ─────────────────────────────────────────────────────────

def add_user_to_teams(email: str, display_name: str) -> dict:
    """
    Invite the partner user to Azure AD (if not already there) and
    add them to the configured TEAMS_TEAM_ID.

    Returns a result dict stored as step output in the workflow.
    Raises on any error so the workflow step is marked failed.
    """
    team_id = os.environ.get("TEAMS_TEAM_ID", "")
    if not team_id:
        raise RuntimeError(
            "TEAMS_TEAM_ID not set in python/.env. "
            "Find it in Teams Admin Center → Teams → select team → Team ID."
        )

    token = _get_access_token()
    user_object_id, newly_invited = _get_or_invite_user(email, display_name, token)
    _add_to_team(team_id, user_object_id, token)

    return {
        "teams_user_object_id": user_object_id,
        "teams_team_id": team_id,
        "teams_guest_invited": str(newly_invited).lower(),
    }
