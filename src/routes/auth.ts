import { Router, Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import db from '../db/database';
import { generateToken } from '../middleware/auth';

const router = Router();

router.post('/login', async (req: Request, res: Response) => {
  const { email, password } = req.body;
  if (!email || !password) {
    res.status(400).json({ error: 'Email and password required' });
    return;
  }

  const user = db.prepare(
    'SELECT * FROM users WHERE email = ?'
  ).get(email) as any;

  if (!user) {
    res.status(401).json({ error: 'Invalid credentials' });
    return;
  }

  const valid = await bcrypt.compare(password, user.password_hash);
  if (!valid) {
    res.status(401).json({ error: 'Invalid credentials' });
    return;
  }

  const token = generateToken(user.id);
  res.json({
    token,
    user: {
      id: user.id,
      firstname: user.firstname,
      lastname: user.lastname,
      email: user.email,
      app_role: user.app_role,
    },
  });
});

router.get('/me', (req: Request, res: Response) => {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  const jwt = require('jsonwebtoken');
  const JWT_SECRET = process.env.JWT_SECRET || 'hyopps-dev-secret-change-in-prod';
  try {
    const payload = jwt.verify(header.slice(7), JWT_SECRET) as { userId: string };
    const user = db.prepare(
      'SELECT id, firstname, lastname, email, app_role, organization_id, created_at FROM users WHERE id = ?'
    ).get(payload.userId) as any;
    if (!user) { res.status(404).json({ error: 'Not found' }); return; }
    res.json(user);
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
});

export default router;
