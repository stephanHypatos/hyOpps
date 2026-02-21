# HyOpps — Workflow Orchestration

Access provisioning workflow orchestration app. Automates and tracks partner onboarding across Studio, Metabase, Teams, Slack, LMS, and KeyCloak.

## Quick Start

```bash
# Install dependencies
pip install -r python/requirements.txt

# Start both servers (FastAPI + Streamlit)
bash python/run.sh
```

Or start individually:

```bash
# FastAPI backend (port 8000, auto-reloads)
cd python && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Streamlit frontend (port 8501, auto-reloads)
streamlit run python/frontend/app.py --server.port 8501 --server.headless true
```

**Admin panel:** http://localhost:8501
**API docs:** http://localhost:8000/docs
**Default admin:** `admin@hyopps.local` / `admin123`

## Stack

- **Backend:** FastAPI (Python 3.9), SQLite (`sqlite3` stdlib)
- **Frontend:** Streamlit
- **Auth:** JWT (HMAC-SHA256, 8h sessions), bcrypt password hashing
- **DB file:** `python/data/hyopps_py.db` (created on first run)

## Features

### Workflow Types
- **New Partner Onboarding** (8 steps) — sets up org, Studio companies, Metabase group, Teams channel, Slack group, LMS
- **New Partner User** (9 steps) — adds user to an existing partner org, provisions per-user personal Studio company, adds to all org groups

### User Roles
| Role | Access |
|------|--------|
| `admin` | Full admin panel — all orgs, users, executions |
| `partner_admin` | Partner panel — their org only; can add new users via onboarding workflow |
| `user` | No panel access |

### Partner Admin Flow
1. Real admin runs *New Partner User* workflow to create the person
2. Real admin edits user → sets role to `partner_admin`, sets a password
3. Partner admin logs in at http://localhost:8501 → sees their org dashboard
4. Partner admin clicks **Add User** → onboarding workflow starts (org pre-selected)

## Environment Variables

Copy `python/.env.example` to `python/.env` and fill in credentials.

| Variable | Description |
|----------|-------------|
| `JWT_SECRET` | JWT signing secret (change in production) |
| `AZURE_TENANT_ID` | Azure AD Directory (tenant) ID |
| `AZURE_CLIENT_ID` | Azure AD Application (client) ID |
| `AZURE_CLIENT_SECRET` | Azure AD client secret value |
| `TEAMS_TEAM_ID` | Microsoft 365 Group ID for the Teams team partners are added to |

## Integrations

### Microsoft Teams (Graph API)
Implemented in `python/api/integrations/teams.py`. Currently **stubbed** in the workflow pending Azure permission grant.

Required Graph API **Application** permissions (admin consent needed):
- `User.Invite.All`
- `TeamMember.ReadWrite.All`

To enable: update `add_user_to_teams_channel` in `python/api/integrations/steps.py` (see the `TODO` comment).

### Future Integrations (planned)
Add a new file per service following the `teams.py` pattern, then wire into `steps.py`:
- `slack.py` — Slack API
- `metabase.py` — Metabase API
- `atlassian.py` — Atlassian / Confluence

## Integration Stubs

All auto steps not yet wired to real APIs return simulated success responses. Step names map to:

| Step | Target API |
|------|-----------|
| `clone_metabase_collection` | POST Metabase `/api/collection` |
| `create_metabase_group` | POST Metabase `/api/permissions/group` |
| `add_user_to_metabase_group` | PUT Metabase `/api/permissions/membership` |
| `create_teams_channel` | POST MS Graph `/teams/{id}/channels` |
| `add_user_to_teams_channel` | MS Graph (implemented, stubbed pending permissions) |
| `create_slack_group` | POST Slack `/usergroups.create` |
| `add_user_to_slack_group` | POST Slack `/usergroups.users.update` |
| `send_studio_invite` | Studio invite API |
| `share_documentation` | Email / Slack |
