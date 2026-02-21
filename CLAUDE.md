# HyOpps — Claude Code Context

## Project Overview
Workflow orchestration app for access provisioning of partner organisations. Admins run structured workflows to onboard new partners and their users across multiple systems (Studio, Metabase, Teams, Slack, KeyCloak, LMS).

## Stack
- **Backend**: FastAPI (Python 3.9), SQLite via `sqlite3` stdlib
- **Frontend**: Streamlit
- **No Node.js/TypeScript** — was removed, app is Python-only

## Running Servers
Both started via background processes. To restart:
```bash
# FastAPI (port 8000, auto-reloads on file change)
cd python && /Users/stephankuche/Library/Python/3.9/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Streamlit (port 8501, auto-reloads on file change)
/Users/stephankuche/Library/Python/3.9/bin/streamlit run python/frontend/app.py --server.port 8501 --server.headless true
```

Convenience script: `python/run.sh` (starts both).

Default admin login: `admin@hyopps.local` / `admin123`

## Project Structure
```
hyOpps/
├── python/
│   ├── api/
│   │   ├── main.py              # FastAPI app, lifespan: create_schema + seed_data
│   │   ├── database.py          # SQLite schema + seed data
│   │   ├── models.py            # Pydantic request models
│   │   ├── auth.py              # JWT auth, require_admin + require_partner_admin deps
│   │   ├── engine/
│   │   │   └── workflow.py      # Workflow execution engine
│   │   ├── integrations/
│   │   │   ├── steps.py         # Auto-step dispatcher (Teams stubbed, others real)
│   │   │   └── teams.py         # Microsoft Graph API integration (stubbed pending perms)
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── executions.py    # Admin-only execution routes
│   │       ├── organizations.py
│   │       ├── partner.py       # Partner-admin scoped routes
│   │       └── users.py
│   ├── frontend/
│   │   └── app.py               # Streamlit UI (admin + partner_admin panels)
│   ├── .env                     # Credentials — gitignored, never commit
│   ├── .env.example             # Template for .env
│   ├── requirements.txt
│   └── run.sh
├── CLAUDE.md
├── README.md
└── access-management-spec.md
```

## Python 3.9 Compatibility Notes
The system Python is 3.9. Avoid:
- `match` statements (use `if/elif` instead)
- `X | Y` union type hints (use `Union[X, Y]` from `typing`)
- `list[str]` / `dict[str, Any]` as runtime generics in function signatures are fine in 3.9+

## Database Schema (SQLite)
Key tables and relationships:

```
organizations
  ├── users (organization_id → nullable FK)
  ├── studio_companies (organization_id → NOT NULL FK, env: test/prod)
  ├── system_groups (organization_id → NOT NULL FK, tool: metabase/teams/slack)
  └── organization_integrations (organization_id → unique)

users
  ├── user_studio_companies (user_id → cascade delete) ← personal per-user studio
  └── access_grants (user_id → cascade delete)

workflow_executions
  ├── workflow_step_executions (execution_id)
  └── refs: organization_id, user_id, requested_by (all nullable, no cascade)
```

DB file: `python/data/hyopps_py.db`

### Delete Gotcha
SQLite FKs are enabled per-connection (`PRAGMA foreign_keys=ON` in `get_db()`). Several FKs have no cascade rule, so delete endpoints must manually null/delete dependents first. See `routes/users.py` and `routes/organizations.py` for the pattern.

## Key Architectural Decisions

### Personal Studio Companies
Each user onboarded via `new_partner_user` workflow gets their **own individual** `user_studio_companies` record — not shared with other users in the org. Created automatically in step 7 (`create_studio_user_company`). The `studio_companies` table remains for org-level shared companies (TEST/PROD environments).

### Workflow Engine
- `engine/workflow.py` drives step execution synchronously in background threads
- Auto steps call `execute_step()` in `integrations/steps.py`
- `_apply_step_output()` persists auto step results to DB immediately
- `_finalize_new_partner()` / `_finalize_new_partner_user()` run on workflow completion
- Manual steps pause at `awaiting_input` status until admin submits form data

### Workflows
**new_partner** (8 steps): input_studio_companies → trigger_infrabot → clone_metabase_collection → create_metabase_group → grant_metabase_db_access → create_teams_channel → create_slack_group → lms_setup

**new_partner_user** (9 steps): select_organization → input_user_details → add_user_to_studio_companies → add_user_to_metabase_group → add_user_to_teams_channel → add_user_to_slack_group → create_studio_user_company → send_studio_invite → share_documentation

### User Roles (`app_role`)
Three roles stored on the `users` table:
- `admin` — full access to all admin routes and UI
- `partner_admin` — scoped access via `/api/partner/*`; must have an `organization_id`; can add new users to their own org
- `user` — no panel access (portal users only)

### Auth Dependencies (`api/auth.py`)
- `require_admin` — rejects non-admins with 403
- `require_partner_admin` — allows `admin` and `partner_admin`; enforces org assignment for `partner_admin`
- `get_current_user` — validates JWT, looks up user from DB, returns full user dict

### Partner Admin Flow
1. Real admin runs `new_partner_user` to create the user
2. Real admin edits user → sets role to `partner_admin`, sets a password
3. Partner admin logs in → lands on partner panel (separate sidebar, scoped pages)
4. Partner admin clicks "Add User" → `POST /api/partner/executions` auto-submits `select_organization` step with their org, lands at `input_user_details`
5. Partner admin fills in user details; workflow completes normally

### API Auth
- All `/api/executions`, `/api/organizations`, `/api/users`, `/api/workflow-definitions` routes require `admin` JWT
- All `/api/partner/*` routes require `admin` or `partner_admin` JWT
- `/api/auth/login` and `/health` are public

## Integrations (`api/integrations/`)

### teams.py — Microsoft Teams (Graph API)
Real implementation present. Stubbed in `steps.py` pending Azure permission grant.

Required Graph API **Application** permissions (need admin consent):
- `User.Invite.All`
- `TeamMember.ReadWrite.All`

Flow when enabled: calls `/v1.0/invitations` (handles new + existing guest users), then adds to team via `/v1.0/teams/{team_id}/members`.

Credentials in `python/.env`:
```
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
TEAMS_TEAM_ID=
```

To re-enable Teams in the workflow, update `add_user_to_teams_channel` in `steps.py`:
```python
# Replace the stub with:
from .teams import add_user_to_teams
result = add_user_to_teams(email, display_name)
return {"success": True, "output": result}
```

### Future integrations (planned)
Add a new file per service (e.g. `slack.py`, `metabase.py`, `atlassian.py`) following the same pattern as `teams.py`, then wire into `steps.py`.

## API Endpoints
```
POST   /api/auth/login
GET    /api/auth/me

GET    /api/executions
POST   /api/executions
GET    /api/executions/{id}
POST   /api/executions/{id}/steps/{step_id}/input
POST   /api/executions/{id}/steps/{step_id}/retry

GET    /api/organizations
GET    /api/organizations/{id}
PUT    /api/organizations/{id}
DELETE /api/organizations/{id}

GET    /api/users
PUT    /api/users/{id}          # supports password field (min 8 chars, hashed)
DELETE /api/users/{id}
GET    /api/users/{id}/access

GET    /api/partner/me          # org overview + user list
GET    /api/partner/executions
POST   /api/partner/executions  # auto-submits select_organization step
GET    /api/partner/executions/{id}
POST   /api/partner/executions/{id}/steps/{step_id}/input
POST   /api/partner/executions/{id}/steps/{step_id}/retry

GET    /api/workflow-definitions
GET    /health
```
