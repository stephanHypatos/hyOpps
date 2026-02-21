import random
import string
from typing import Any


def _fake_id(prefix: str) -> str:
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    return f"{prefix}-{suffix}"


def execute_step(step_name: str, context: dict[str, Any]) -> dict[str, Any]:
    """
    Stub implementations for all auto steps.
    Replace each case with real API calls when credentials are available.
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
        return {"success": True, "output": {"metabase_user_id": _fake_id("mb-usr")}}

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
        return {"success": True, "output": {
            "sent_to": str(context.get("email", "")),
            "channels": "email,slack",
        }}

    else:
        return {"success": False, "error": f"Unknown step: {step_name}"}
