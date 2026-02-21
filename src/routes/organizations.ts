import { Router, Request, Response } from 'express';
import db from '../db/database';
import { requireAdmin } from '../middleware/auth';

const router = Router();

// List organizations
router.get('/', requireAdmin, (_req: Request, res: Response) => {
  const orgs = db.prepare('SELECT * FROM organizations ORDER BY name ASC').all() as any[];
  const parsed = orgs.map(o => ({
    ...o,
    account_types: JSON.parse(o.account_types || '["partner"]'),
  }));
  res.json(parsed);
});

// Get organization with system groups and studio companies
router.get('/:id', requireAdmin, (req: Request, res: Response) => {
  const org = db.prepare('SELECT * FROM organizations WHERE id = ?').get(req.params.id) as any;
  if (!org) {
    res.status(404).json({ error: 'Organization not found' });
    return;
  }

  const systemGroups = db.prepare('SELECT * FROM system_groups WHERE organization_id = ?').all(req.params.id);
  const studioCompanies = db.prepare('SELECT * FROM studio_companies WHERE organization_id = ?').all(req.params.id);
  const integrations = db.prepare('SELECT * FROM organization_integrations WHERE organization_id = ?').get(req.params.id);

  res.json({
    ...org,
    account_types: JSON.parse(org.account_types || '["partner"]'),
    system_groups: systemGroups,
    studio_companies: studioCompanies,
    integrations: integrations || null,
  });
});

export default router;
