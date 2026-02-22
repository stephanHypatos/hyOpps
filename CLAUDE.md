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
│   │   │   ├── steps.py         # Auto-step dispatcher (Teams stubbed, Metabase + email live)
│   │   │   ├── metabase.py      # Metabase API integration (live)
│   │   │   ├── email.py         # SMTP email integration (live — share_documentation step)
│   │   │   └── teams.py         # Microsoft Graph API integration (stubbed pending perms)
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── executions.py    # Admin-only execution routes
│   │       ├── metabase_routes.py  # GET /api/metabase/groups + debug endpoint
│   │       ├── organizations.py
│   │       ├── partner.py       # Partner-admin scoped routes
│   │       └── users.py         # includes /metabase sub-routes
│   ├── frontend/
│   │   └── app.py               # Streamlit UI (admin + partner_admin panels)
│   ├── .env                     # Credentials — gitignored, never commit
│   ├── .env.example             # Template for .env
│   ├── requirements.txt
│   └── run.sh
├── CLAUDE.md
├── README.md
└── TODO.md
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
  ├── organization_integrations (organization_id → unique)
  └── organization_documentation (organization_id → unique, fields: internal_docu, generique_docu, add_docu)

users
  ├── metabase_user_id INTEGER  (nullable — stored on first Metabase provision)
  ├── user_studio_companies (user_id → cascade delete) ← personal per-user studio
  └── access_grants (user_id → cascade delete)

workflow_executions
  ├── workflow_step_executions (execution_id)
  └── refs: organization_id, user_id, requested_by (all nullable, no cascade)
```

DB file: `python/data/hyopps_py.db`

### Delete Gotcha
SQLite FKs are enabled per-connection (`PRAGMA foreign_keys=ON` in `get_db()`). Several FKs have no cascade rule, so delete endpoints must manually null/delete dependents first. See `routes/users.py` and `routes/organizations.py` for the pattern.

### Schema Migrations
`database.py` contains a `_migrate(conn)` function called at startup (before `CREATE TABLE IF NOT EXISTS`). Detects schema drift and applies fixes.

Current migrations:
1. **app_role CHECK constraint** — table recreation to add `partner_admin`
2. **metabase_user_id column** — `ALTER TABLE users ADD COLUMN metabase_user_id INTEGER`
3. **organization_documentation table** — `CREATE TABLE organization_documentation (...)` checked via `sqlite_master`

Pattern for future: check `PRAGMA table_info` for missing columns → `ALTER TABLE ADD COLUMN`; for constraint changes → recreate table with `PRAGMA foreign_keys=OFF`.

## Key Architectural Decisions

### SQLite Concurrency — Critical Rule
The workflow engine holds **one SQLite connection open across all consecutive auto steps**. Never open a second write connection inside `execute_step()` — it causes "database is locked". All side-effect DB writes must go through `_apply_step_output()` in `workflow.py`, which runs on the engine's own connection.

### Personal Studio Companies
Each user onboarded via `new_partner_user` gets their own `user_studio_companies` record. Created in step 7 (`create_studio_user_company`).

### Workflow Engine
- `engine/workflow.py` drives step execution in background threads
- Auto steps call `execute_step()` in `integrations/steps.py`
- `_apply_step_output()` persists auto step side-effects to DB on the engine's connection
- `_finalize_new_partner()` / `_finalize_new_partner_user()` run on workflow completion
- Manual steps pause at `awaiting_input` until admin submits form data

### Workflows
**new_partner** (8 steps): input_studio_companies → trigger_infrabot → clone_metabase_collection → create_metabase_group → grant_metabase_db_access → create_teams_channel → create_slack_group → lms_setup

**new_partner_user** (9 steps): select_organization → input_user_details → add_user_to_studio_companies → **add_user_to_metabase_group** → add_user_to_teams_channel → add_user_to_slack_group → create_studio_user_company → send_studio_invite → share_documentation

### User Roles (`app_role`)
- `admin` — full access
- `partner_admin` — scoped to their org via `/api/partner/*`
- `user` — no panel access

### Partner Admin Flow
1. Admin runs `new_partner_user` → user created, provisioned in Metabase
2. Admin edits user → sets `partner_admin` role + password
3. Partner admin logs in → partner panel (scoped to their org)
4. Partner admin clicks "Add User" → workflow starts with org pre-selected

### API Auth
- All `/api/executions`, `/api/organizations`, `/api/users`, `/api/metabase`, `/api/workflow-definitions` → require `admin` JWT
- `/api/partner/*` → require `admin` or `partner_admin` JWT
- `/api/auth/login`, `/health` → public

## Integrations

### metabase.py — LIVE
Full implementation. Wired in `steps.py` for `add_user_to_metabase_group`.

Auth: `x-api-key` header (Metabase v0.46+ required).

**Key functions in `api/integrations/metabase.py`:**
- `get_user_by_email(email)` — search Metabase user by email
- `create_user(email, firstname, lastname)` — create Metabase user
- `list_groups()` — all non-system groups (excludes group IDs 1 and 2)
- `add_to_group(user_id, group_id)` — add to permission group; 400 + "already" = idempotent no-op
- `remove_from_group(mb_user_id, group_id)` — looks up membership_id then DELETE
- `get_user_group_memberships(mb_user_id)` — GET /api/user/:id + GET /permissions/group
- `provision_user(email, firstname, lastname, group_id)` — find-or-create + add to group

**Critical Metabase API quirks (this instance):**
- `GET /api/user/:id` → memberships field: `user_group_memberships` (NOT `group_memberships`)
- Each membership entry: `{"id": <group_id>, "is_group_manager": bool}` — `id` IS the group_id
- `GET /api/permissions/membership` → keyed by **user_id** string: `{"558": [{membership_id, group_id, user_id}]}`

**metabase_user_id flow:**
1. Onboarding workflow step `add_user_to_metabase_group` calls `provision_user`
2. `_apply_step_output()` in engine stores the returned ID in `users.metabase_user_id`
3. Manual assignment via `POST /api/users/{id}/metabase` also stores it
4. `GET /api/users/{id}/metabase` reads stored ID — no email lookup needed

**Org Metabase group config:** Each org needs a `system_groups` row with `tool='metabase'` and `external_id` = integer group ID as string. Set via org detail page or `PUT /api/organizations/{id}/groups`.

Credentials in `python/.env`:
```
METABASE_URL=https://your-instance.example.com
METABASE_API_KEY=mb_your_api_key_here
```

### teams.py — STUBBED
Real implementation exists. Stubbed pending Azure permission grant (`User.Invite.All`, `TeamMember.ReadWrite.All`). To enable, update `add_user_to_teams_channel` in `steps.py`.

### email.py — LIVE
Implemented in `python/api/integrations/email.py`. Wired into `share_documentation` step.

**What it does:**
- Sends an HTML + plain-text email to the newly onboarded user with org documentation links
- Uses stdlib `smtplib` + STARTTLS — no extra dependencies
- If no docs are configured for the org, the email still sends (with a placeholder note)
- If SMTP is not configured, the step fails with a clear error

**Org documentation config:** Set per org via org detail page → "Edit documentation links" or `PUT /api/organizations/{id}/documentation`. Fields: `internal_docu`, `generique_docu`, `add_docu`.

Credentials in `python/.env`:
```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=sender@example.com
SMTP_PASSWORD=your_smtp_password
EMAIL_FROM=HyOpps <noreply@example.com>   # optional
```

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
GET    /api/organizations/{id}          # includes documentation{} field
PUT    /api/organizations/{id}
PUT    /api/organizations/{id}/groups          # upsert system group (metabase/teams/slack)
PUT    /api/organizations/{id}/documentation   # upsert {internal_docu, generique_docu, add_docu}
DELETE /api/organizations/{id}

GET    /api/users
PUT    /api/users/{id}
DELETE /api/users/{id}
GET    /api/users/{id}/access
GET    /api/users/{id}/metabase              # stored metabase_user_id + current group memberships
POST   /api/users/{id}/metabase              # body: {group_id: int} — find/create + add to group, persists ID
DELETE /api/users/{id}/metabase/{group_id}   # remove from specific group

GET    /api/metabase/groups                  # all non-system permission groups
GET    /api/metabase/debug/user/{mb_id}      # raw Metabase user API response (debug)

GET    /api/partner/me
GET    /api/partner/executions
POST   /api/partner/executions
GET    /api/partner/executions/{id}
POST   /api/partner/executions/{id}/steps/{step_id}/input
POST   /api/partner/executions/{id}/steps/{step_id}/retry

GET    /api/workflow-definitions
GET    /health
```
