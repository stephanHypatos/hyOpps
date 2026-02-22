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
- **Email:** stdlib `smtplib` + STARTTLS — no extra dependencies
- **DB file:** `python/data/hyopps_py.db` (created on first run)

## Features

### Workflow Types
- **New Partner Onboarding** (8 steps) — sets up org, Studio companies, Metabase group, Teams channel, Slack group, LMS
- **New Partner User** (9 steps) — adds user to an existing partner org, creates Metabase account + adds to org group, provisions personal Studio company, sends documentation email

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
| `METABASE_URL` | Base URL of your Metabase instance (no trailing slash) |
| `METABASE_API_KEY` | Metabase API key (Admin → Settings → Authentication → API Keys, requires v0.46+) |
| `AZURE_TENANT_ID` | Azure AD Directory (tenant) ID |
| `AZURE_CLIENT_ID` | Azure AD Application (client) ID |
| `AZURE_CLIENT_SECRET` | Azure AD client secret value |
| `TEAMS_TEAM_ID` | Microsoft 365 Group ID for the Teams team partners are added to |
| `SMTP_HOST` | SMTP server hostname (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port — defaults to `587` (STARTTLS) |
| `SMTP_USER` | SMTP login / sender address |
| `SMTP_PASSWORD` | SMTP password or app password |
| `EMAIL_FROM` | Optional From header override (e.g. `HyOpps <noreply@example.com>`) |

## Integrations

### Metabase (LIVE)
Implemented in `python/api/integrations/metabase.py`. Fully wired into the `new_partner_user` onboarding workflow.

**What it does:**
- Creates a Metabase user account for the new partner user (find-or-create by email)
- Adds the user to the org's configured Metabase permission group
- Stores the Metabase user ID in the local DB for fast subsequent lookups
- Admin UI supports adding/removing the user from 1-to-N permission groups manually

**Setup per org:** Set the org's Metabase permission group ID via the org detail page → "Edit / add group IDs" expander, or via `PUT /api/organizations/{id}/groups`.

### Email / Share Documentation (LIVE)
Implemented in `python/api/integrations/email.py`. Wired into the `share_documentation` step (step 9) of `new_partner_user`.

**What it does:**
- Sends an HTML + plain-text email to the newly onboarded user at the end of the workflow
- Email contains the org's three documentation links (internal, general, additional)
- Uses stdlib `smtplib` + STARTTLS — no extra pip packages needed

**Setup per org:** Go to org detail page → "Edit documentation links" and set the three URLs. These are stored in the `organization_documentation` table and sent automatically during onboarding.

**Required `.env` keys:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`. The step will fail with a clear error if these are missing.

### Microsoft Teams (STUBBED)
Implemented in `python/api/integrations/teams.py`. Currently **stubbed** in the workflow pending Azure permission grant.

Required Graph API **Application** permissions (admin consent needed):
- `User.Invite.All`
- `TeamMember.ReadWrite.All`

To enable: update `add_user_to_teams_channel` in `python/api/integrations/steps.py`.

### Future Integrations (planned)
- `slack.py` — Slack API (group management)
- `atlassian.py` — Atlassian / Confluence

## Auto Step Status

| Step | Workflow | Status |
|------|----------|--------|
| `add_user_to_metabase_group` | new_partner_user | **Live** — find-or-create account, add to org group |
| `share_documentation` | new_partner_user | **Live** — sends HTML email with org doc links |
| `create_studio_user_company` | new_partner_user | **Live** (stub output, DB write real) |
| `add_user_to_teams_channel` | new_partner_user | Stubbed — awaiting Azure permissions |
| `add_user_to_slack_group` | new_partner_user | Stubbed |
| `send_studio_invite` | new_partner_user | Stubbed |
| `add_user_to_studio_companies` | new_partner_user | Stubbed |
| `clone_metabase_collection` | new_partner | Stubbed |
| `create_metabase_group` | new_partner | Stubbed |
| `grant_metabase_db_access` | new_partner | Stubbed |
| `create_teams_channel` | new_partner | Stubbed |
| `create_slack_group` | new_partner | Stubbed |
