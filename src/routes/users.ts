import { Router, Request, Response } from 'express';
import db from '../db/database';
import { requireAdmin } from '../middleware/auth';

const router = Router();

// List users
router.get('/', requireAdmin, (_req: Request, res: Response) => {
  const users = db.prepare(`
    SELECT u.id, u.firstname, u.lastname, u.email, u.languages, u.skills, u.roles,
           u.organization_id, u.app_role, u.created_at, o.name as organization_name
    FROM users u
    LEFT JOIN organizations o ON o.id = u.organization_id
    ORDER BY u.created_at DESC
  `).all() as any[];

  const parsed = users.map(u => ({
    ...u,
    languages: JSON.parse(u.languages || '[]'),
    skills: JSON.parse(u.skills || '[]'),
    roles: JSON.parse(u.roles || '[]'),
  }));
  res.json(parsed);
});

// Get user access
router.get('/:id/access', requireAdmin, (req: Request, res: Response) => {
  const user = db.prepare('SELECT id, firstname, lastname, email FROM users WHERE id = ?').get(req.params.id) as any;
  if (!user) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  const accessGrants = db.prepare(`
    SELECT ag.*, r.name as resource_name, r.type as resource_type
    FROM access_grants ag
    JOIN resources r ON r.id = ag.resource_id
    WHERE ag.user_id = ? AND ag.revoked_at IS NULL
  `).all(req.params.id);

  const studioAccess = db.prepare(`
    SELECT usa.*, sc.studio_id, sc.name, sc.environment, o.name as organization_name
    FROM user_studio_access usa
    JOIN studio_companies sc ON sc.id = usa.studio_company_id
    JOIN organizations o ON o.id = sc.organization_id
    WHERE usa.user_id = ? AND usa.revoked_at IS NULL
  `).all(req.params.id);

  res.json({
    user,
    access_grants: accessGrants,
    studio_access: studioAccess,
  });
});

export default router;
