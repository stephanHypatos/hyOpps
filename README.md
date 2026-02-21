# HyOpps — Workflow Orchestration MVP

Access provisioning workflow orchestration app. Automates and tracks partner onboarding across Studio, Metabase, Teams, Slack, LMS, and KeyCloak.

## Quick Start

```bash
npm install
npm run dev
```

Open http://localhost:3000

**Default admin:** `admin@hyopps.local` / `admin123`

## What's in the MVP

- **Two workflow types** from the spec:
  - New Partner Onboarding (8 steps: 3 manual + 5 auto)
  - New Partner User Onboarding (9 steps: 2 manual + 7 auto)

- **Workflow engine** — steps run in sequence, auto steps execute immediately (stubbed), manual steps pause and wait for admin input

- **Admin control panel** — list executions, filter by status, view step-by-step progress, submit manual input inline, retry failed steps

- **Full data model** from spec — organizations, studio_companies, system_groups, organization_integrations, users, user_studio_access, access_grants, workflow_executions, workflow_step_executions

- **SQLite** — no external database required, stored in `data/hyopps.db`

## Database Reset

```bash
npm run db:reset && npm run dev
```

## Stack

- Express + TypeScript backend
- SQLite via better-sqlite3
- JWT auth (8h sessions)
- Vanilla JS single-page frontend

## Integration Stubs

All auto steps are stubbed in `src/integrations/steps.ts`. Each returns a simulated success response with fake external IDs. Replace with real API calls per step name:

- `clone_metabase_collection` → POST Metabase /api/collection
- `create_metabase_group` → POST Metabase /api/permissions/group
- `create_teams_channel` → POST MS Graph /teams/{id}/channels
- `create_slack_group` → POST Slack /usergroups.create
- `add_user_to_*` → respective platform APIs
- `send_studio_invite`, `share_documentation` → Studio/email/Slack APIs

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 3000 | Server port |
| `JWT_SECRET` | dev secret | Change in production |
