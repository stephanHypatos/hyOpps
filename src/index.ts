import express from 'express';
import cors from 'cors';
import path from 'path';
import { createSchema } from './db/schema';
import { seedData } from './db/seed';
import authRoutes from './routes/auth';
import executionRoutes from './routes/executions';
import organizationRoutes from './routes/organizations';
import userRoutes from './routes/users';

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Serve static frontend
app.use(express.static(path.join(process.cwd(), 'public')));

// API routes
app.use('/api/auth', authRoutes);
app.use('/api/executions', executionRoutes);
app.use('/api/organizations', organizationRoutes);
app.use('/api/users', userRoutes);

// Workflow definitions (public read)
app.get('/api/workflow-definitions', (_req, res) => {
  const db = require('./db/database').default;
  const defs = db.prepare('SELECT * FROM workflow_definitions').all();
  res.json(defs);
});

// Serve frontend for all non-API routes (SPA fallback)
app.get('*', (_req, res) => {
  res.sendFile(path.join(process.cwd(), 'public', 'index.html'));
});

async function bootstrap() {
  createSchema();
  await seedData();

  app.listen(PORT, () => {
    console.log(`HyOpps Workflow Server running on http://localhost:${PORT}`);
    console.log('Default admin: admin@hyopps.local / admin123');
  });
}

bootstrap().catch(console.error);
