import { randomUUID } from 'crypto';
import bcrypt from 'bcryptjs';
import db from './database';

export async function seedData() {
  const existing = db.prepare('SELECT COUNT(*) as count FROM workflow_definitions').get() as { count: number };
  if (existing.count > 0) return;

  // Resources
  const resources = [
    { id: randomUUID(), name: 'Studio', type: 'studio', has_api: 1 },
    { id: randomUUID(), name: 'Metabase', type: 'insights', has_api: 1 },
    { id: randomUUID(), name: 'Microsoft Teams', type: 'communication', has_api: 1 },
    { id: randomUUID(), name: 'Slack', type: 'communication', has_api: 1 },
    { id: randomUUID(), name: 'LMS', type: 'learning', has_api: 0 },
    { id: randomUUID(), name: 'KeyCloak', type: 'auth', has_api: 0 },
  ];

  const insertResource = db.prepare(
    'INSERT OR IGNORE INTO resources (id, name, type, has_api) VALUES (?, ?, ?, ?)'
  );
  for (const r of resources) {
    insertResource.run(r.id, r.name, r.type, r.has_api);
  }

  // Workflow definitions
  const newPartnerId = randomUUID();
  const newPartnerUserId = randomUUID();

  db.prepare('INSERT OR IGNORE INTO workflow_definitions (id, name, description) VALUES (?, ?, ?)').run(
    newPartnerId, 'new_partner', 'Onboard a new partner organization from scratch'
  );
  db.prepare('INSERT OR IGNORE INTO workflow_definitions (id, name, description) VALUES (?, ?, ?)').run(
    newPartnerUserId, 'new_partner_user', 'Add a new user to an existing partner organization'
  );

  // New Partner steps
  const newPartnerSteps = [
    { order: 1, name: 'input_studio_companies', label: 'Input Studio Companies', type: 'manual', description: 'Admin creates companies in Studio UI, then inputs organization name + Studio TEST ID + Studio PROD ID' },
    { order: 2, name: 'trigger_infrabot', label: 'Trigger Infrabot', type: 'manual', description: 'Admin triggers Infrabot with name, company ID, cluster, scopes. Confirms when KeyCloak creds are stored in GitHub' },
    { order: 3, name: 'clone_metabase_collection', label: 'Clone Metabase Collection', type: 'auto', description: 'Clone template collection for the new partner via Metabase API' },
    { order: 4, name: 'create_metabase_group', label: 'Create Metabase User Group', type: 'auto', description: 'Create a user group in Metabase and store the group ID' },
    { order: 5, name: 'grant_metabase_db_access', label: 'Grant DB Access to Metabase Group', type: 'auto', description: 'Grant database access to the Metabase group' },
    { order: 6, name: 'create_teams_channel', label: 'Create Teams Channel', type: 'auto', description: 'Create a dedicated Teams channel via MS Graph API' },
    { order: 7, name: 'create_slack_group', label: 'Create Slack Group', type: 'auto', description: 'Create a Slack group via Slack API' },
    { order: 8, name: 'lms_setup', label: 'LMS Setup', type: 'manual', description: 'Admin adds partner learning path in LMS. Confirm when done' },
  ];

  const insertStep = db.prepare(
    'INSERT OR IGNORE INTO workflow_step_definitions (id, workflow_definition_id, step_order, name, label, type, description) VALUES (?, ?, ?, ?, ?, ?, ?)'
  );

  for (const s of newPartnerSteps) {
    insertStep.run(randomUUID(), newPartnerId, s.order, s.name, s.label, s.type, s.description);
  }

  // New Partner User steps
  const newPartnerUserSteps = [
    { order: 1, name: 'select_organization', label: 'Select Organization', type: 'manual', description: 'Admin selects existing partner organization from list' },
    { order: 2, name: 'input_user_details', label: 'Input User Details', type: 'manual', description: 'Admin inputs user details and selects which Studio companies to grant access to' },
    { order: 3, name: 'add_user_to_studio_companies', label: 'Add User to Studio Companies', type: 'auto', description: 'Add user to selected Studio companies (TEST + PROD)' },
    { order: 4, name: 'add_user_to_metabase_group', label: 'Add User to Metabase Group', type: 'auto', description: "Add user to the org's Metabase system group" },
    { order: 5, name: 'add_user_to_teams_channel', label: 'Add User to Teams Channel', type: 'auto', description: "Add user to the org's Teams system group" },
    { order: 6, name: 'add_user_to_slack_group', label: 'Add User to Slack Group', type: 'auto', description: "Add user to the org's Slack system group" },
    { order: 7, name: 'create_studio_user_company', label: 'Create User-Specific Studio Company', type: 'auto', description: 'Create a user-specific Studio company entry' },
    { order: 8, name: 'send_studio_invite', label: 'Send Studio Invite', type: 'auto', description: 'Send invite to Studio platform' },
    { order: 9, name: 'share_documentation', label: 'Share Documentation', type: 'auto', description: 'Send documentation links via email/Slack' },
  ];

  for (const s of newPartnerUserSteps) {
    insertStep.run(randomUUID(), newPartnerUserId, s.order, s.name, s.label, s.type, s.description);
  }

  // Create default admin user
  const passwordHash = await bcrypt.hash('admin123', 10);
  const adminId = randomUUID();
  db.prepare(
    'INSERT OR IGNORE INTO users (id, firstname, lastname, email, app_role, password_hash) VALUES (?, ?, ?, ?, ?, ?)'
  ).run(adminId, 'Admin', 'User', 'admin@hyopps.local', 'admin', passwordHash);

  console.log('Database seeded successfully');
  console.log('Default admin: admin@hyopps.local / admin123');
}
