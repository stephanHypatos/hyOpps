import { randomUUID } from 'crypto';
import db from '../db/database';
import { executeStep } from '../integrations/steps';

// Build context from stored step outputs + manual inputs
function buildContext(executionId: string): Record<string, unknown> {
  const stepExecs = db.prepare(
    'SELECT output, manual_input FROM workflow_step_executions WHERE execution_id = ? AND status = ?'
  ).all(executionId, 'completed') as Array<{ output: string | null; manual_input: string | null }>;

  const context: Record<string, unknown> = {};
  for (const s of stepExecs) {
    if (s.output) Object.assign(context, JSON.parse(s.output));
    if (s.manual_input) Object.assign(context, JSON.parse(s.manual_input));
  }
  return context;
}

// Persist side-effects from a completed New Partner execution
function finalizeNewPartner(executionId: string) {
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;
  if (!execution) return;

  const context = buildContext(executionId);
  const orgId = execution.organization_id;
  if (!orgId) return;

  const now = new Date().toISOString();

  // Upsert organization_integrations
  const existingInteg = db.prepare('SELECT id FROM organization_integrations WHERE organization_id = ?').get(orgId) as any;
  if (!existingInteg) {
    db.prepare(
      `INSERT INTO organization_integrations (id, organization_id, keycloak_confirmed, keycloak_cluster, metabase_collection_id, lms_confirmed, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).run(
      randomUUID(), orgId,
      context.keycloak_confirmed ? 1 : 0,
      context.keycloak_cluster || null,
      context.metabase_collection_id || null,
      context.lms_confirmed ? 1 : 0,
      now
    );
  } else {
    db.prepare(
      `UPDATE organization_integrations SET keycloak_confirmed=?, keycloak_cluster=?, metabase_collection_id=?, lms_confirmed=?, updated_at=? WHERE organization_id=?`
    ).run(
      context.keycloak_confirmed ? 1 : 0,
      context.keycloak_cluster || null,
      context.metabase_collection_id || null,
      context.lms_confirmed ? 1 : 0,
      now, orgId
    );
  }

  // System groups
  const groupsToCreate = [
    { tool: 'metabase', external_id: context.metabase_group_id, external_name: context.metabase_group_name },
    { tool: 'teams', external_id: context.teams_channel_id, external_name: context.teams_channel_name },
    { tool: 'slack', external_id: context.slack_group_id, external_name: context.slack_group_handle },
  ];

  const insertGroup = db.prepare(
    'INSERT OR IGNORE INTO system_groups (id, organization_id, tool, external_name, external_id, created_at) VALUES (?, ?, ?, ?, ?, ?)'
  );
  for (const g of groupsToCreate) {
    if (g.external_id) {
      insertGroup.run(randomUUID(), orgId, g.tool, String(g.external_name || g.tool), String(g.external_id), now);
    }
  }
}

// Persist side-effects from a completed New Partner User execution
function finalizeNewPartnerUser(executionId: string) {
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;
  if (!execution || !execution.user_id || !execution.requested_by) return;

  const context = buildContext(executionId);
  const now = new Date().toISOString();
  const userId = execution.user_id;
  const requestedBy = execution.requested_by;

  // user_studio_access records
  const selectedIds = context.selected_studio_company_ids as string[] | undefined;
  if (Array.isArray(selectedIds)) {
    const insertAccess = db.prepare(
      'INSERT OR IGNORE INTO user_studio_access (id, user_id, studio_company_id, granted_at) VALUES (?, ?, ?, ?)'
    );
    for (const scId of selectedIds) {
      insertAccess.run(randomUUID(), userId, scId, now);
    }
  }

  // access_grants for all resources
  const resources = db.prepare('SELECT id, name FROM resources').all() as Array<{ id: string; name: string }>;
  const insertGrant = db.prepare(
    'INSERT OR IGNORE INTO access_grants (id, user_id, resource_id, permission, granted_by, granted_at, execution_id) VALUES (?, ?, ?, ?, ?, ?, ?)'
  );
  for (const r of resources) {
    insertGrant.run(randomUUID(), userId, r.id, 'read', requestedBy, now, executionId);
  }
}

// Advance to next step or finalize execution
async function advance(executionId: string) {
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;
  if (!execution || execution.status === 'completed' || execution.status === 'failed') return;

  const nextStep = db.prepare(`
    SELECT wse.*, wsd.name as step_name, wsd.type as step_type, wsd.label
    FROM workflow_step_executions wse
    JOIN workflow_step_definitions wsd ON wsd.id = wse.step_definition_id
    WHERE wse.execution_id = ? AND wse.status = 'pending'
    ORDER BY wse.step_order ASC
    LIMIT 1
  `).get(executionId) as any;

  if (!nextStep) {
    // All steps done
    const now = new Date().toISOString();
    db.prepare("UPDATE workflow_executions SET status='completed', completed_at=? WHERE id=?").run(now, executionId);

    // Write side-effects
    const wfDef = db.prepare(
      'SELECT wd.name FROM workflow_definitions wd JOIN workflow_executions we ON we.workflow_definition_id = wd.id WHERE we.id = ?'
    ).get(executionId) as any;

    if (wfDef?.name === 'new_partner') finalizeNewPartner(executionId);
    if (wfDef?.name === 'new_partner_user') finalizeNewPartnerUser(executionId);
    return;
  }

  const now = new Date().toISOString();

  // Mark step as running
  db.prepare(
    "UPDATE workflow_step_executions SET status='running', started_at=? WHERE id=?"
  ).run(now, nextStep.id);
  db.prepare(
    "UPDATE workflow_executions SET current_step_order=?, status='running' WHERE id=?"
  ).run(nextStep.step_order, executionId);

  if (nextStep.step_type === 'manual') {
    db.prepare(
      "UPDATE workflow_step_executions SET status='awaiting_input' WHERE id=?"
    ).run(nextStep.id);
    db.prepare(
      "UPDATE workflow_executions SET status='awaiting_input' WHERE id=?"
    ).run(executionId);
    return;
  }

  // Auto step — run integration
  const context = buildContext(executionId);
  try {
    const result = await executeStep(nextStep.step_name, context);
    const finishedAt = new Date().toISOString();

    if (result.success) {
      db.prepare(
        "UPDATE workflow_step_executions SET status='completed', output=?, completed_at=? WHERE id=?"
      ).run(JSON.stringify(result.output || {}), finishedAt, nextStep.id);

      // Apply any context fields that need to be persisted to org/users
      applyStepOutput(executionId, nextStep.step_name, result.output || {});

      // Recurse to pick up next step
      await advance(executionId);
    } else {
      db.prepare(
        "UPDATE workflow_step_executions SET status='failed', error=?, completed_at=? WHERE id=?"
      ).run(result.error || 'Unknown error', finishedAt, nextStep.id);
      db.prepare(
        "UPDATE workflow_executions SET status='failed' WHERE id=?"
      ).run(executionId);
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    db.prepare(
      "UPDATE workflow_step_executions SET status='failed', error=?, completed_at=? WHERE id=?"
    ).run(msg, new Date().toISOString(), nextStep.id);
    db.prepare("UPDATE workflow_executions SET status='failed' WHERE id=?").run(executionId);
  }
}

// Apply auto-step output to organization/integration records as needed
function applyStepOutput(executionId: string, stepName: string, output: Record<string, string>) {
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;
  if (!execution) return;

  const orgId = execution.organization_id;
  if (!orgId) return;

  const now = new Date().toISOString();

  if (stepName === 'clone_metabase_collection' && output.metabase_collection_id) {
    db.prepare(
      'UPDATE organization_integrations SET metabase_collection_id=?, updated_at=? WHERE organization_id=?'
    ).run(output.metabase_collection_id, now, orgId);
  }

  if (stepName === 'create_metabase_group' && output.metabase_group_id) {
    db.prepare(
      'INSERT OR IGNORE INTO system_groups (id, organization_id, tool, external_name, external_id, created_at) VALUES (?,?,?,?,?,?)'
    ).run(randomUUID(), orgId, 'metabase', output.metabase_group_name || 'metabase', output.metabase_group_id, now);
  }

  if (stepName === 'create_teams_channel' && output.teams_channel_id) {
    db.prepare(
      'INSERT OR IGNORE INTO system_groups (id, organization_id, tool, external_name, external_id, created_at) VALUES (?,?,?,?,?,?)'
    ).run(randomUUID(), orgId, 'teams', output.teams_channel_name || 'teams', output.teams_channel_id, now);
  }

  if (stepName === 'create_slack_group' && output.slack_group_id) {
    db.prepare(
      'INSERT OR IGNORE INTO system_groups (id, organization_id, tool, external_name, external_id, created_at) VALUES (?,?,?,?,?,?)'
    ).run(randomUUID(), orgId, 'slack', output.slack_group_handle || 'slack', output.slack_group_id, now);
  }
}

// Start a new execution
export async function startExecution(executionId: string) {
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;
  if (!execution) throw new Error('Execution not found');

  // Create all step execution records
  const steps = db.prepare(
    'SELECT * FROM workflow_step_definitions WHERE workflow_definition_id = ? ORDER BY step_order ASC'
  ).all(execution.workflow_definition_id) as any[];

  const insertStepExec = db.prepare(
    'INSERT INTO workflow_step_executions (id, execution_id, step_definition_id, step_order, status) VALUES (?, ?, ?, ?, ?)'
  );

  for (const step of steps) {
    insertStepExec.run(randomUUID(), executionId, step.id, step.step_order, 'pending');
  }

  db.prepare("UPDATE workflow_executions SET status='running' WHERE id=?").run(executionId);

  // Advance asynchronously so the HTTP response returns quickly
  setImmediate(() => advance(executionId));
}

// Submit manual input for a step
export async function submitManualInput(
  executionId: string,
  stepExecId: string,
  input: Record<string, unknown>,
  completedBy: string
) {
  const stepExec = db.prepare(
    "SELECT * FROM workflow_step_executions WHERE id = ? AND execution_id = ? AND status = 'awaiting_input'"
  ).get(stepExecId, executionId) as any;

  if (!stepExec) throw new Error('Step not found or not awaiting input');

  const now = new Date().toISOString();

  // For the 'input_studio_companies' step, create the org + studio companies
  const stepDef = db.prepare(
    'SELECT * FROM workflow_step_definitions WHERE id = ?'
  ).get(stepExec.step_definition_id) as any;

  if (stepDef?.name === 'input_studio_companies') {
    await handleStudioCompaniesInput(executionId, input);
  }

  if (stepDef?.name === 'select_organization') {
    await handleSelectOrganization(executionId, input);
  }

  if (stepDef?.name === 'input_user_details') {
    await handleInputUserDetails(executionId, input);
  }

  if (stepDef?.name === 'trigger_infrabot') {
    await handleTriggerInfrabot(executionId, input);
  }

  db.prepare(
    "UPDATE workflow_step_executions SET status='completed', manual_input=?, completed_by=?, completed_at=? WHERE id=?"
  ).run(JSON.stringify(input), completedBy, now, stepExecId);

  await advance(executionId);
}

async function handleStudioCompaniesInput(executionId: string, input: Record<string, unknown>) {
  const orgName = String(input.organization_name || '');
  if (!orgName) return;

  const now = new Date().toISOString();

  // Create or get organization
  let org = db.prepare('SELECT * FROM organizations WHERE name = ?').get(orgName) as any;
  if (!org) {
    const orgId = randomUUID();
    db.prepare(
      'INSERT INTO organizations (id, name, account_types, created_at) VALUES (?, ?, ?, ?)'
    ).run(orgId, orgName, '["partner"]', now);
    org = { id: orgId };
  }

  // Update execution to link organization
  db.prepare('UPDATE workflow_executions SET organization_id=? WHERE id=?').run(org.id, executionId);

  // Create organization_integrations row
  const existingInteg = db.prepare('SELECT id FROM organization_integrations WHERE organization_id=?').get(org.id);
  if (!existingInteg) {
    db.prepare(
      'INSERT INTO organization_integrations (id, organization_id, updated_at) VALUES (?, ?, ?)'
    ).run(randomUUID(), org.id, now);
  }

  // Create studio companies
  const testId = String(input.studio_company_id_test || '');
  const testName = String(input.studio_company_name_test || '');
  const prodId = String(input.studio_company_id_prod || '');
  const prodName = String(input.studio_company_name_prod || '');

  if (testId) {
    db.prepare(
      'INSERT OR IGNORE INTO studio_companies (id, organization_id, studio_id, name, environment, created_at) VALUES (?,?,?,?,?,?)'
    ).run(randomUUID(), org.id, testId, testName || orgName + ' TEST', 'test', now);
  }
  if (prodId) {
    db.prepare(
      'INSERT OR IGNORE INTO studio_companies (id, organization_id, studio_id, name, environment, created_at) VALUES (?,?,?,?,?,?)'
    ).run(randomUUID(), org.id, prodId, prodName || orgName + ' PROD', 'prod', now);
  }
}

async function handleSelectOrganization(executionId: string, input: Record<string, unknown>) {
  const orgId = String(input.organization_id || '');
  if (orgId) {
    db.prepare('UPDATE workflow_executions SET organization_id=? WHERE id=?').run(orgId, executionId);
  }
}

async function handleInputUserDetails(executionId: string, input: Record<string, unknown>) {
  const now = new Date().toISOString();
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;

  const firstname = String(input.firstname || '');
  const lastname = String(input.lastname || '');
  const email = String(input.email || '');
  if (!email) return;

  // Create user if not exists
  let user = db.prepare('SELECT * FROM users WHERE email = ?').get(email) as any;
  if (!user) {
    const userId = randomUUID();
    const bcrypt = await import('bcryptjs');
    const passwordHash = await bcrypt.hash(randomUUID(), 10);
    db.prepare(
      'INSERT INTO users (id, firstname, lastname, email, languages, skills, roles, organization_id, app_role, password_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)'
    ).run(
      userId, firstname, lastname, email,
      JSON.stringify(input.languages || []),
      JSON.stringify(input.skills || []),
      JSON.stringify(input.roles || []),
      execution?.organization_id || null,
      'user',
      passwordHash,
      now
    );
    user = { id: userId };
  }

  db.prepare('UPDATE workflow_executions SET user_id=? WHERE id=?').run(user.id, executionId);
}

async function handleTriggerInfrabot(executionId: string, input: Record<string, unknown>) {
  const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(executionId) as any;
  if (!execution?.organization_id) return;

  const now = new Date().toISOString();
  const cluster = String(input.keycloak_cluster || '');

  db.prepare(
    'UPDATE organization_integrations SET keycloak_confirmed=1, keycloak_cluster=?, updated_at=? WHERE organization_id=?'
  ).run(cluster, now, execution.organization_id);
}

// Retry a failed auto step
export async function retryStep(executionId: string, stepExecId: string) {
  const stepExec = db.prepare(
    "SELECT * FROM workflow_step_executions WHERE id = ? AND execution_id = ? AND status = 'failed'"
  ).get(stepExecId, executionId) as any;

  if (!stepExec) throw new Error('Step not found or not in failed state');

  db.prepare(
    "UPDATE workflow_step_executions SET status='pending', error=NULL, started_at=NULL, completed_at=NULL WHERE id=?"
  ).run(stepExecId);
  db.prepare("UPDATE workflow_executions SET status='running' WHERE id=?").run(executionId);

  await advance(executionId);
}
