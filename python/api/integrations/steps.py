import random
import string
from typing import Any


def _fake_id(prefix: str) -> str:
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    return f"{prefix}-{suffix}"


def execute_step(step_name: str, context: dict[str, Any]) -> dict[str, Any]:
    """
    Step dispatcher for all auto steps.
    Real integrations are called where available; stubs are used where pending.
    Returns: {"success": bool, "output": dict, "error": str}
    """
    if step_name == "clone_metabase_collection":
        return {"success": True, "output": {"metabase_collection_id": _fake_id("mb-col")}}

    elif step_name == "create_metabase_group":
        org = str(context.get("organization_name", "partner")).lower().replace(" ", "-")
        return {
            "success": True,
            "output": {
                "metabase_group_id": _fake_id("mb-grp"),
                "metabase_group_name": f"ext-{org}",
            }
        }

    elif step_name == "grant_metabase_db_access":
        return {"success": True, "output": {"granted": "true"}}

    elif step_name == "create_teams_channel":
        org = str(context.get("organization_name", "partner")).lower().replace(" ", "-")
        return {
            "success": True,
            "output": {
                "teams_channel_id": _fake_id("teams-ch"),
                "teams_channel_name": f"ext-{org}",
            }
        }

    elif step_name == "create_slack_group":
        org = str(context.get("organization_name", "partner")).lower().replace(" ", "-")
        return {
            "success": True,
            "output": {
                "slack_group_id": _fake_id("slack-grp"),
                "slack_group_handle": f"ext-{org}",
            }
        }

    elif step_name == "add_user_to_studio_companies":
        ids = context.get("selected_studio_company_ids", [])
        return {"success": True, "output": {"added_companies": str(ids)}}

    elif step_name == "add_user_to_metabase_group":
        from ..database import get_db
        from .metabase import provision_user

        email = str(context.get("email", "")).strip().lower()
        firstname = str(context.get("firstname", ""))
        lastname = str(context.get("lastname", ""))
        org_id = str(context.get("organization_id", ""))

        if not email:
            return {"success": False, "error": "Missing email in workflow context"}
        if not org_id:
            return {"success": False, "error": "Missing organization_id in workflow context"}

        # Look up the org's Metabase permission group ID from system_groups
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT external_id FROM system_groups WHERE organization_id=? AND tool='metabase'",
                (org_id,)
            ).fetchone()
        finally:
            conn.close()

        if not row or not row["external_id"]:
            return {"success": False, "error": "No Metabase group configured for this organization. Set it via the org detail page."}

        try:
            group_id = int(row["external_id"])
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid Metabase group ID '{row['external_id']}' — must be an integer"}

        try:
            result = provision_user(email, firstname, lastname, group_id)
            return {"success": True, "output": {
                "metabase_user_id": str(result["metabase_user_id"]),
                "metabase_group_id": str(result["metabase_group_id"]),
                "metabase_user_existed": str(result["user_exists"]).lower(),
                "metabase_user_created": str(result["created"]).lower(),
            }}
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif step_name == "add_user_to_teams_channel":
        # TODO: re-enable once Azure app permissions are granted
        return {"success": True, "output": {"teams_membership_id": _fake_id("teams-mbr")}}

    elif step_name == "add_user_to_slack_group":
        return {"success": True, "output": {"updated": "true"}}

    elif step_name == "create_studio_user_company":
        firstname = str(context.get("firstname", "")).strip()
        lastname = str(context.get("lastname", "")).strip()
        name = f"{firstname} {lastname}".strip() or str(context.get("email", "user"))
        return {"success": True, "output": {
            "studio_user_company_id": _fake_id("studio-usr"),
            "studio_user_company_name": f"{name} - Personal Studio",
        }}

    elif step_name == "send_studio_invite":
        return {"success": True, "output": {
            "invite_sent": "true",
            "email": str(context.get("email", "")),
        }}

    elif step_name == "share_documentation":
        from ..database import get_db
        from .email import send_documentation_email

        email = str(context.get("email", "")).strip()
        firstname = str(context.get("firstname", "")).strip()
        org_id = str(context.get("organization_id", "")).strip()

        if not email:
            return {"success": False, "error": "Missing email in workflow context"}
        if not org_id:
            return {"success": False, "error": "Missing organization_id in workflow context"}

        conn = get_db()
        try:
            org = conn.execute("SELECT name FROM organizations WHERE id=?", (org_id,)).fetchone()
            docs_row = conn.execute(
                "SELECT internal_docu, generique_docu, add_docu FROM organization_documentation WHERE organization_id=?",
                (org_id,)
            ).fetchone()
        finally:
            conn.close()

        org_name = org["name"] if org else ""
        docs = dict(docs_row) if docs_row else {}

        try:
            result = send_documentation_email(email, firstname, org_name, docs)
            return {"success": True, "output": {
                "sent_to": email,
                "channels": "email",
                "links_sent": str(result.get("links_sent", 0)),
            }}
        except Exception as e:
            return {"success": False, "error": f"Email failed: {str(e)}"}

    else:
        return {"success": False, "error": f"Unknown step: {step_name}"}
