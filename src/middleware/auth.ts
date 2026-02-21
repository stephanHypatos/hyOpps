import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import db from '../db/database';

const JWT_SECRET = process.env.JWT_SECRET || 'hyopps-dev-secret-change-in-prod';

export function generateToken(userId: string): string {
  return jwt.sign({ userId }, JWT_SECRET, { expiresIn: '8h' });
}

export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  const header = req.headers.authorization;
  if (!header || !header.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  const token = header.slice(7);
  try {
    const payload = jwt.verify(token, JWT_SECRET) as { userId: string };
    const row = db.prepare(
      'SELECT id, firstname, lastname, email, languages, skills, roles, organization_id, app_role, created_at FROM users WHERE id = ?'
    ).get(payload.userId) as any;

    if (!row) {
      res.status(401).json({ error: 'User not found' });
      return;
    }

    req.user = {
      ...row,
      languages: JSON.parse(row.languages || '[]'),
      skills: JSON.parse(row.skills || '[]'),
      roles: JSON.parse(row.roles || '[]'),
    };
    next();
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
}

export function requireAdmin(req: Request, res: Response, next: NextFunction): void {
  requireAuth(req, res, () => {
    if (req.user?.app_role !== 'admin') {
      res.status(403).json({ error: 'Admin access required' });
      return;
    }
    next();
  });
}
