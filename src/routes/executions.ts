import { Router, Request, Response } from 'express';
import { randomUUID } from 'crypto';
import db from '../db/database';
import { requireAdmin } from '../middleware/auth';
import { startExecution, submitManualInput, retryStep } from '../engine/workflow';

const router = Router();

// List executions
router.get('/', requireAdmin, (req: Request, res: Response) => {
  const { status } = req.query;
  let query = `
    SELECT we.*, wd.name as workflow_name, wd.description as workflow_description,
           o.name as organization_name,
           u.email as user_email,
           rb.email as requested_by_email
    FROM workflow_executions we
    JOIN workflow_definitions wd ON wd.id = we.workflow_definition_id
    LEFT JOIN organizations o ON o.id = we.organization_id
    LEFT JOIN users u ON u.id = we.user_id
    LEFT JOIN users rb ON rb.id = we.requested_by
  `;
  const params: unknown[] = [];
  if (status) {
    query += ' WHERE we.status = ?';
    params.push(status);
  }
  query += ' ORDER BY we.created_at DESC';

  const rows = db.prepare(query).all(...params);
  res.json(rows);
});

// Get single execution with steps
router.get('/:id', requireAdmin, (req: Request, res: Response) => {
  const execution = db.prepare(`
    SELECT we.*, wd.name as workflow_name, wd.description as workflow_description,
           o.name as organization_name,
           u.email as user_email,
           rb.email as requested_by_email
    FROM workflow_executions we
    JOIN workflow_definitions wd ON wd.id = we.workflow_definition_id
    LEFT JOIN organizations o ON o.id = we.organization_id
    LEFT JOIN users u ON u.id = we.user_id
    LEFT JOIN users rb ON rb.id = we.requested_by
    WHERE we.id = ?
  `).get(req.params.id) as any;

  if (!execution) {
    res.status(404).json({ error: 'Execution not found' });
    return;
  }

  const steps = db.prepare(`
    SELECT wse.*, wsd.name as step_name, wsd.label, wsd.type as step_type, wsd.description,
           cb.email as completed_by_email
    FROM workflow_step_executions wse
    JOIN workflow_step_definitions wsd ON wsd.id = wse.step_definition_id
    LEFT JOIN users cb ON cb.id = wse.completed_by
    WHERE wse.execution_id = ?
    ORDER BY wse.step_order ASC
  `).all(req.params.id) as any[];

  const parsedSteps = steps.map(s => ({
    ...s,
    manual_input: s.manual_input ? JSON.parse(s.manual_input) : null,
    output: s.output ? JSON.parse(s.output) : null,
  }));

  res.json({ ...execution, steps: parsedSteps });
});

// Create new execution
router.post('/', requireAdmin, async (req: Request, res: Response) => {
  const { workflow_type } = req.body;
  if (!workflow_type) {
    res.status(400).json({ error: 'workflow_type required (new_partner | new_partner_user)' });
    return;
  }

  const wfDef = db.prepare('SELECT * FROM workflow_definitions WHERE name = ?').get(workflow_type) as any;
  if (!wfDef) {
    res.status(400).json({ error: 'Unknown workflow type' });
    return;
  }

  const id = randomUUID();
  const now = new Date().toISOString();
  db.prepare(
    'INSERT INTO workflow_executions (id, workflow_definition_id, requested_by, status, created_at) VALUES (?, ?, ?, ?, ?)'
  ).run(id, wfDef.id, req.user!.id, 'pending', now);

  try {
    await startExecution(id);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: msg });
    return;
  }

  const created = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(id);
  res.status(201).json(created);
});

// Submit manual input for a step
router.post('/:id/steps/:stepId/input', requireAdmin, async (req: Request, res: Response) => {
  try {
    await submitManualInput(req.params.id, req.params.stepId, req.body, req.user!.id);
    const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(req.params.id);
    res.json(execution);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(400).json({ error: msg });
  }
});

// Retry a failed step
router.post('/:id/steps/:stepId/retry', requireAdmin, async (req: Request, res: Response) => {
  try {
    await retryStep(req.params.id, req.params.stepId);
    const execution = db.prepare('SELECT * FROM workflow_executions WHERE id = ?').get(req.params.id);
    res.json(execution);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(400).json({ error: msg });
  }
});

export default router;
