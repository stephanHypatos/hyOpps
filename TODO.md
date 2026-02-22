# HyOpps — TODO

## High Priority

### Metabase — onboarding group assignment not confirmed
- The `add_user_to_metabase_group` step calls `provision_user` which calls `add_to_group`
- Verify the user IS actually added to the org's permission group during onboarding (not just the account created)
- Debug: after a workflow run, expand step 4 "Output data" in execution detail — confirm `metabase_group_id` is present
- Quick check: hit `GET /api/metabase/debug/user/{mb_user_id}` and confirm the group appears in `user_group_memberships`

### Email — SMTP setup required for share_documentation step
- `share_documentation` (step 9 of `new_partner_user`) now sends a real email
- Requires `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` in `python/.env`
- If SMTP is not configured, step 9 will fail — add credentials before testing
- Optional: set `EMAIL_FROM=HyOpps <noreply@example.com>` for a nicer From header

## Medium Priority

### Microsoft Teams — enable live integration
- Implementation exists in `python/api/integrations/teams.py`
- Blocked on Azure permission grant: `User.Invite.All` + `TeamMember.ReadWrite.All`
- Once permissions granted, replace stub in `steps.py` `add_user_to_teams_channel`:
  ```python
  from .teams import add_user_to_teams
  result = add_user_to_teams(email, display_name)
  return {"success": True, "output": result}
  ```

### Slack integration
- Create `python/api/integrations/slack.py`
- Wire into `steps.py` `add_user_to_slack_group`
- Needs `SLACK_BOT_TOKEN` in `.env`

### Metabase — debug endpoint cleanup
- `GET /api/metabase/debug/user/{mb_user_id}` is useful but should be removed or gated before production

## Low Priority / Nice to Have

### Show metabase_user_id in user cards
- Currently only shown in the edit form
- Could add a small badge in the user list view if `metabase_user_id` is set

### Org documentation — show in partner dashboard
- Documentation links currently only shown in admin org detail
- Could expose read-only links in partner admin dashboard under org info

### Workflow retry UX
- Currently the retry button re-runs only the failed step
- Consider adding a "re-run from step N" option

### Partner admin — execution history
- Partner admin can see their executions but has limited detail view
- Consider expanding the partner panel execution detail page

### Atlassian / Confluence integration
- Not started — add `atlassian.py` following `metabase.py` pattern

## Known Issues / Quirks

- **Metabase API field names** differ from documentation:
  - `GET /api/user/:id` → `user_group_memberships` (not `group_memberships`)
  - Each membership entry: `{"id": <group_id>, ...}` — `id` IS the group_id
  - `GET /api/permissions/membership` → keyed by user_id string (not group_id)
- **SQLite concurrency** — engine holds one write connection across all auto steps; never open a second write connection inside `execute_step()`
- **Teams stub** — `add_user_to_teams_channel` always returns fake success; no real Teams action taken
- **Email** — `share_documentation` step will fail if SMTP is not configured in `.env`
