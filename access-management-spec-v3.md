# Access Management App — Feature Spec v3

**Version:** 0.3  
**Status:** Draft  
**Last updated:** 2026-02-21  
**Purpose:** Extend existing app with user/group management, workflow-based access provisioning, and an admin control panel for hybrid automation (automated steps + manual input steps).

**Changes from v2:**
- `groups` renamed and split into `organizations` (business concept) and `system_groups` (provisioned artifacts)
- `organizations.account_type` is now an array to support partner+client overlap edge case
- Added `studio_companies` table and `user_studio_access` join table for per-user Studio company access
- Updated all references and relationships accordingly

---

## 1. Overview

The app automates access provisioning for two primary user types: **Partners** and **Clients**. A third type, **Internals**, exists but is out of scope for automation in v1.

The system has two main interfaces:

- **User-facing form** — authenticated users submit onboarding requests
- **Admin control panel** — admins monitor workflow progress, input manual data, and trigger/retry automation steps

Every onboarding request becomes a **workflow execution** — a chain of steps that run in sequence, where each step is either automated (calls an API) or manual (waits for an admin to input data and confirm).

---

## 2. Concepts & Terminology

Three concepts that were previously blurred under "group" are now distinct:

**Organization** — the real-world company being onboarded (e.g. "Acme Corp"). Has an account type (partner, client, or both). This is the business entity.

**System Group** — a provisioned group artifact inside a specific tool (e.g. `ext-xsa` in Atlassian, a Slack usergroup, a Metabase permissions group). System groups belong to an organization and are created during onboarding. Users get added to system groups, not directly to organizations.

**Studio Company** — a specific company entity inside Studio (TEST or PROD environment). An organization can have multiple Studio companies. A user can have access to a specific subset of them.

---

## 3. User Roles

| Role | Can Do |
|------|--------|
| `admin` | Submit requests, manage workflows, input manual step data, trigger automations |
| `user` | Submit requests only (future — for now all requests come from admins) |

Authentication is required for all access. Role is assigned at account creation.

---

## 4. Workflow Types

### 4.1 New Partner Onboarding

Triggered when a brand new partner organization needs to be set up from scratch. Creates all company-level infrastructure before any users can be added.

**Steps (in order):**

| # | Step | Type | Description |
|---|------|------|-------------|
| 1 | Input Studio Companies | Manual | Admin creates companies in Studio UI, then inputs organization name + Studio TEST ID + Studio PROD ID into the app |
| 2 | Trigger Infrabot | Manual | Admin triggers Infrabot with: name, company ID, cluster (prod-eu / prod-us), scopes. Confirms when KeyCloak creds are stored in GitHub |
| 3 | Clone Metabase Collection | Auto | Clones template collection for the new partner via Metabase API. Stores returned collection ID |
| 4 | Create Metabase User Group | Auto | Creates a user group in Metabase. Stores returned group ID. Creates corresponding `system_group` record |
| 5 | Grant DB Access to Metabase Group | Auto | Grants database access to the Metabase group via Metabase API |
| 6 | Create Teams Channel | Auto | Creates a dedicated Teams channel via MS Graph API. Stores returned channel ID. Creates corresponding `system_group` record |
| 7 | Create Slack Group | Auto | Creates a Slack group via Slack API. Stores returned group ID. Creates corresponding `system_group` record |
| 8 | LMS Setup | Manual | Admin adds partner learning path in LMS (no API). Confirms when done |

**On completion:** Organization is fully provisioned. All system groups and Studio companies are stored. Users can now be added via the "New Partner User" workflow.

---

### 4.2 New Partner User Onboarding

Triggered when a new user needs to be added to an **existing** partner organization. All infrastructure already exists — steps add the user to each system group and grant Studio company access.

**Steps (in order):**

| # | Step | Type | Description |
|---|------|------|-------------|
| 1 | Select Organization | Manual | Admin selects existing partner organization from list |
| 2 | Input User Details | Manual | Admin inputs: firstname, lastname, email, languages, skills, roles. Also selects which Studio companies this user gets access to |
| 3 | Add User to Studio Companies | Auto | Adds user to selected Studio companies (TEST + PROD) via Studio API |
| 4 | Add User to Metabase User Group | Auto | Adds user to the org's Metabase system group via Metabase API |
| 5 | Add User to Teams Channel | Auto | Adds user to the org's Teams system group via MS Graph API |
| 6 | Add User to Slack Group | Auto | Adds user to the org's Slack system group via Slack API |
| 7 | Create User-Specific Studio Company | Auto | Creates a user-specific Studio company entry via Studio API. Stores returned ID |
| 8 | Send Studio Invite | Auto | Sends invite to Studio platform via Studio API |
| 9 | Share Documentation | Auto | Sends documentation links (standard + partner-specific internal links) via email/Slack |

**On completion:** User has full access. `user_studio_access` records are written. `access_grants` records are written.

---

### 4.3 Future Workflow Types (out of scope v1)

- New Client Onboarding (organization-level)
- New Client User Onboarding
- Internal User Onboarding
- Access Revocation

---

## 5. Data Model

### 5.1 `organizations` table

The real-world company being onboarded. Account type is an array to support the edge case where a company is both a partner and a client.

```sql
CREATE TABLE organizations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  account_types TEXT[] NOT NULL DEFAULT '{"partner"}',
                -- values: 'partner', 'client', 'internal'
  created_at    TIMESTAMPTZ DEFAULT now()
);
```

---

### 5.2 `studio_companies` table

Represents a specific company entity inside Studio. Each organization gets at least one TEST and one PROD Studio company during onboarding. Stored separately so users can be granted access to a subset.

```sql
CREATE TABLE studio_companies (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id),
  studio_id       TEXT NOT NULL UNIQUE,   -- the ID from Studio's system
  name            TEXT NOT NULL,
  environment     TEXT NOT NULL CHECK (environment IN ('test', 'prod')),
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

### 5.3 `user_studio_access` table

Join table: which users have access to which Studio companies. Written at the end of the New Partner User workflow.

```sql
CREATE TABLE user_studio_access (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  studio_company_id UUID NOT NULL REFERENCES studio_companies(id) ON DELETE CASCADE,
  granted_at        TIMESTAMPTZ DEFAULT now(),
  revoked_at        TIMESTAMPTZ,
  UNIQUE (user_id, studio_company_id)
);
```

---

### 5.4 `system_groups` table

Provisioned group artifacts inside external tools. Created during organization onboarding. Users get added to these, not directly to the organization.

```sql
CREATE TABLE system_groups (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id),
  tool            TEXT NOT NULL,       -- 'atlassian', 'slack', 'teams', 'metabase'
  external_name   TEXT NOT NULL,       -- e.g. 'ext-xsa' (the name in the external system)
  external_id     TEXT,               -- the ID returned by the external system's API
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE (organization_id, tool)       -- one system group per tool per org
);
```

---

### 5.5 `organization_integrations` table

Stores all remaining external IDs for an organization that don't fit neatly into `system_groups` — specifically Studio companies, KeyCloak, Metabase collection, and LMS.

```sql
CREATE TABLE organization_integrations (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id         UUID NOT NULL UNIQUE REFERENCES organizations(id),

  -- KeyCloak (Infrabot)
  keycloak_confirmed      BOOLEAN DEFAULT false,
  keycloak_cluster        TEXT,           -- 'prod-eu' | 'prod-us'

  -- Metabase
  metabase_collection_id  TEXT,

  -- LMS
  lms_confirmed           BOOLEAN DEFAULT false,

  updated_at              TIMESTAMPTZ DEFAULT now()
);
```

Note: Studio company IDs are stored in `studio_companies`. Slack, Teams, and Metabase group IDs are stored in `system_groups`. This table covers what's left.

---

### 5.6 `users` table

```sql
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firstname       TEXT NOT NULL,
  lastname        TEXT NOT NULL,
  email           TEXT NOT NULL UNIQUE,
  languages       TEXT[] DEFAULT '{}',   -- ISO 639-1, e.g. ['en', 'de']
  skills          TEXT[] DEFAULT '{}',
  roles           TEXT[] DEFAULT '{}',
  organization_id UUID REFERENCES organizations(id),
  app_role        TEXT NOT NULL DEFAULT 'user' CHECK (app_role IN ('admin', 'user')),
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

### 5.7 `resources` table

The systems/tools that access can be granted to. Seeded manually.

```sql
CREATE TABLE resources (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL UNIQUE,   -- e.g. 'Studio', 'Metabase', 'Teams', 'Slack', 'LMS'
  type        TEXT,                   -- e.g. 'atlassian', 'insights', 'communication'
  has_api     BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

### 5.8 `access_grants` table

The final record of what access a user has to what resource. Written at the end of a successful workflow execution.

```sql
CREATE TABLE access_grants (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resource_id     UUID NOT NULL REFERENCES resources(id),
  permission      TEXT NOT NULL DEFAULT 'read'
                  CHECK (permission IN ('read', 'write', 'admin')),
  granted_by      UUID REFERENCES users(id),
  granted_at      TIMESTAMPTZ DEFAULT now(),
  revoked_at      TIMESTAMPTZ,
  execution_id    UUID REFERENCES workflow_executions(id),
  UNIQUE (user_id, resource_id)
);
```

Note: access grants are now always user-level. Group-level access is represented by the fact that a user belongs to an organization and has entries in `user_studio_access` and `system_groups`.

---

### 5.9 `workflow_definitions` and `workflow_step_definitions` tables

Configuration data — seeded once, rarely changed.

```sql
CREATE TABLE workflow_definitions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE workflow_step_definitions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_definition_id UUID NOT NULL REFERENCES workflow_definitions(id),
  step_order             INTEGER NOT NULL,
  name                   TEXT NOT NULL,
  label                  TEXT NOT NULL,
  type                   TEXT NOT NULL CHECK (type IN ('auto', 'manual')),
  description            TEXT,
  UNIQUE (workflow_definition_id, step_order)
);
```

---

### 5.10 `workflow_executions` table

One row per onboarding request.

```sql
CREATE TABLE workflow_executions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_definition_id UUID NOT NULL REFERENCES workflow_definitions(id),
  organization_id        UUID REFERENCES organizations(id),
  user_id                UUID REFERENCES users(id),
  requested_by           UUID REFERENCES users(id),
  status                 TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'running', 'awaiting_input', 'completed', 'failed')),
  current_step_order     INTEGER DEFAULT 1,
  created_at             TIMESTAMPTZ DEFAULT now(),
  completed_at           TIMESTAMPTZ
);
```

---

### 5.11 `workflow_step_executions` table

One row per step per execution. Full audit trail.

```sql
CREATE TABLE workflow_step_executions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execution_id       UUID NOT NULL REFERENCES workflow_executions(id),
  step_definition_id UUID NOT NULL REFERENCES workflow_step_definitions(id),
  step_order         INTEGER NOT NULL,
  status             TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'running', 'awaiting_input', 'completed', 'failed', 'skipped')),
  manual_input       JSONB,   -- what the admin inputted for manual steps
  output             JSONB,   -- what the API returned for auto steps
  error              TEXT,
  completed_by       UUID REFERENCES users(id),
  started_at         TIMESTAMPTZ,
  completed_at       TIMESTAMPTZ
);
```

---

### 5.12 Entity Relationship Summary

```
organizations ──< studio_companies
organizations ──< system_groups
organizations ──< organization_integrations (1:1)
organizations ──< users
organizations ──< workflow_executions

users ──< user_studio_access >── studio_companies
users ──< access_grants
users ──< workflow_executions (as requested_by)

workflow_definitions ──< workflow_step_definitions
workflow_definitions ──< workflow_executions
workflow_executions ──< workflow_step_executions
workflow_step_definitions ──< workflow_step_executions
workflow_executions ──< access_grants

resources ──< access_grants
```

---

## 6. Application Views

### 6.1 User-Facing Form

- Auth required
- Only accessible to users with `app_role = 'admin'` (for v1)
- Two options: "Onboard New Partner" / "Add User to Existing Partner"
- Submitting creates a `workflow_execution` record with status `pending`
- User sees confirmation screen with execution ID and current status

---

### 6.2 Admin Control Panel

**Execution List view:**
- All executions with status, workflow type, organization name, created date
- Filter by status (pending, running, awaiting_input, completed, failed)

**Execution Detail view:**
- All steps in order with status indicators
- Completed auto steps: show output data (e.g. "Metabase Group ID: 123")
- Completed manual steps: show what was inputted and who confirmed
- `awaiting_input` steps: show inline input form
- `failed` steps: show error + retry button

**Manual Input Form examples:**

*Step 1 — Input Studio Companies:*
```
Organization Name: [text]
Studio Company Name (TEST): [text]
Studio Company ID (TEST):   [text]
Studio Company Name (PROD): [text]
Studio Company ID (PROD):   [text]
[ Confirm & Continue ]
```

*Step 2 — Trigger Infrabot:*
```
Infrabot params (copy these):
  Name:       [pre-filled]
  Company ID: [pre-filled from step 1]
  Cluster:    [prod-eu / prod-us dropdown]
  Scopes:     [text]

[ Mark as Completed ]
```

*Step 2b — User Details + Studio Access:*
```
First Name: [text]   Last Name: [text]
Email: [text]
Languages: [multi-select]
Skills: [tags]
Roles: [multi-select]

Studio Company Access:
  ☑ Acme Corp (TEST)
  ☑ Acme Corp (PROD)
  ☐ Acme Corp Special Project (TEST)

[ Confirm & Continue ]
```

---

## 7. Workflow Engine Logic

**On execution created:**
1. Set status `running`, create all step execution records (`pending`), start step 1

**On step started:**
- `auto` → call integration function → on success: store output, mark `completed`, advance; on failure: mark `failed`, set execution `failed`, notify admin
- `manual` → mark `awaiting_input`, set execution `awaiting_input`, notify admin

**On admin submits manual input:**
1. Write to `manual_input`, mark step `completed`, advance

**On all steps completed:**
1. Mark execution `completed`
2. Write `access_grants`, `user_studio_access` records
3. Notify requester

**Step context object** (passed to each auto step):
```json
{
  "organization_name": "...",
  "studio_company_id_test": "...",
  "studio_company_id_prod": "...",
  "metabase_collection_id": "...",
  "metabase_group_id": "...",
  "teams_channel_id": "...",
  "slack_group_id": "...",
  "user_email": "...",
  "selected_studio_company_ids": ["...", "..."]
}
```

On New Partner completion: context is also used to populate `organization_integrations`, `system_groups`, and `studio_companies`.

---

## 8. Integration Functions (Auto Steps)

```typescript
type StepResult = {
  success: boolean;
  output?: Record<string, string>;
  error?: string;
}

async function executeStep(stepName: string, context: Record<string, any>): Promise<StepResult>
```

| Step Name | Integration | Method |
|-----------|------------|--------|
| `clone_metabase_collection` | Metabase API | POST /api/collection |
| `create_metabase_group` | Metabase API | POST /api/permissions/group |
| `grant_metabase_db_access` | Metabase API | PUT /api/permissions/graph |
| `create_teams_channel` | MS Graph API | POST /teams/{id}/channels |
| `create_slack_group` | Slack API | POST /usergroups.create |
| `add_user_to_studio_companies` | Studio API | TBD |
| `add_user_to_metabase_group` | Metabase API | POST /api/permissions/group/{id}/members |
| `add_user_to_teams_channel` | MS Graph API | POST /teams/{id}/channels/{id}/members |
| `add_user_to_slack_group` | Slack API | POST /usergroups.users.update |
| `create_studio_user_company` | Studio API | TBD |
| `send_studio_invite` | Studio API | TBD |
| `share_documentation` | Email / Slack | TBD |

---

## 9. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/executions` | Submit new onboarding request |
| GET | `/executions` | List executions (admin only) |
| GET | `/executions/:id` | Get execution + all step details |
| POST | `/executions/:id/steps/:stepId/input` | Submit manual input for a step |
| POST | `/executions/:id/steps/:stepId/retry` | Retry a failed auto step |
| GET | `/organizations` | List organizations |
| GET | `/organizations/:id` | Get org + system groups + studio companies |
| GET | `/users` | List users |
| GET | `/users/:id/access` | Get user's access grants + studio company access |

---

## 10. Seed Data

```sql
-- Workflow definitions
INSERT INTO workflow_definitions (name, description) VALUES
  ('new_partner', 'Onboard a new partner organization from scratch'),
  ('new_partner_user', 'Add a new user to an existing partner organization');

-- Resources
INSERT INTO resources (name, type, has_api) VALUES
  ('Studio', 'studio', true),
  ('Metabase', 'insights', true),
  ('Microsoft Teams', 'communication', true),
  ('Slack', 'communication', true),
  ('LMS', 'learning', false),
  ('KeyCloak', 'auth', false);
```

---

## 11. Open Questions

| # | Question | Impact |
|---|----------|--------|
| 1 | What auth system does the app itself use? (KeyCloak, Auth0, custom?) | Affects `users` table + login flow |
| 2 | Should failed steps auto-retry, or always require admin to manually retry? | Workflow engine logic |
| 3 | How should admins be notified when a manual step is waiting? (Slack, email, in-app only?) | Notification system |
| 4 | Should the Client onboarding flow mirror Partner, or is it different enough to design separately? | Scope of v2 |
| 5 | Infrabot: can it be triggered via GitHub Actions API, or purely a Slack bot? | Affects whether step 2 can ever be automated |
| 6 | Can one user belong to multiple organizations? (e.g. a contractor working across two partners) | Would require `user_organization` join table instead of `users.organization_id` |

---

## 12. Out of Scope (v1)

- Client onboarding workflow
- Internal user onboarding
- Access revocation workflow
- End-user self-service form (partners submitting their own requests)
- Multi-cluster / multi-region support beyond prod-eu / prod-us
- Approval flows (requests auto-proceed once submitted by an admin)
