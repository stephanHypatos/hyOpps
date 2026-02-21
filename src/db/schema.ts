import db from './database';

export function createSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS organizations (
      id            TEXT PRIMARY KEY,
      name          TEXT NOT NULL UNIQUE,
      account_types TEXT NOT NULL DEFAULT '["partner"]',
      created_at    TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS users (
      id              TEXT PRIMARY KEY,
      firstname       TEXT NOT NULL,
      lastname        TEXT NOT NULL,
      email           TEXT NOT NULL UNIQUE,
      languages       TEXT NOT NULL DEFAULT '[]',
      skills          TEXT NOT NULL DEFAULT '[]',
      roles           TEXT NOT NULL DEFAULT '[]',
      organization_id TEXT REFERENCES organizations(id),
      app_role        TEXT NOT NULL DEFAULT 'user' CHECK (app_role IN ('admin', 'user')),
      password_hash   TEXT NOT NULL,
      created_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS studio_companies (
      id              TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL REFERENCES organizations(id),
      studio_id       TEXT NOT NULL UNIQUE,
      name            TEXT NOT NULL,
      environment     TEXT NOT NULL CHECK (environment IN ('test', 'prod')),
      created_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS user_studio_access (
      id                TEXT PRIMARY KEY,
      user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      studio_company_id TEXT NOT NULL REFERENCES studio_companies(id) ON DELETE CASCADE,
      granted_at        TEXT DEFAULT (datetime('now')),
      revoked_at        TEXT,
      UNIQUE (user_id, studio_company_id)
    );

    CREATE TABLE IF NOT EXISTS system_groups (
      id              TEXT PRIMARY KEY,
      organization_id TEXT NOT NULL REFERENCES organizations(id),
      tool            TEXT NOT NULL,
      external_name   TEXT NOT NULL,
      external_id     TEXT,
      created_at      TEXT DEFAULT (datetime('now')),
      UNIQUE (organization_id, tool)
    );

    CREATE TABLE IF NOT EXISTS organization_integrations (
      id                      TEXT PRIMARY KEY,
      organization_id         TEXT NOT NULL UNIQUE REFERENCES organizations(id),
      keycloak_confirmed      INTEGER DEFAULT 0,
      keycloak_cluster        TEXT,
      metabase_collection_id  TEXT,
      lms_confirmed           INTEGER DEFAULT 0,
      updated_at              TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS resources (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      type        TEXT,
      has_api     INTEGER DEFAULT 1,
      created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS workflow_definitions (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      description TEXT,
      created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS workflow_step_definitions (
      id                     TEXT PRIMARY KEY,
      workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
      step_order             INTEGER NOT NULL,
      name                   TEXT NOT NULL,
      label                  TEXT NOT NULL,
      type                   TEXT NOT NULL CHECK (type IN ('auto', 'manual')),
      description            TEXT,
      UNIQUE (workflow_definition_id, step_order)
    );

    CREATE TABLE IF NOT EXISTS workflow_executions (
      id                     TEXT PRIMARY KEY,
      workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
      organization_id        TEXT REFERENCES organizations(id),
      user_id                TEXT REFERENCES users(id),
      requested_by           TEXT REFERENCES users(id),
      status                 TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'running', 'awaiting_input', 'completed', 'failed')),
      current_step_order     INTEGER DEFAULT 1,
      created_at             TEXT DEFAULT (datetime('now')),
      completed_at           TEXT
    );

    CREATE TABLE IF NOT EXISTS workflow_step_executions (
      id                 TEXT PRIMARY KEY,
      execution_id       TEXT NOT NULL REFERENCES workflow_executions(id),
      step_definition_id TEXT NOT NULL REFERENCES workflow_step_definitions(id),
      step_order         INTEGER NOT NULL,
      status             TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'running', 'awaiting_input', 'completed', 'failed', 'skipped')),
      manual_input       TEXT,
      output             TEXT,
      error              TEXT,
      completed_by       TEXT REFERENCES users(id),
      started_at         TEXT,
      completed_at       TEXT
    );

    CREATE TABLE IF NOT EXISTS access_grants (
      id           TEXT PRIMARY KEY,
      user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      resource_id  TEXT NOT NULL REFERENCES resources(id),
      permission   TEXT NOT NULL DEFAULT 'read'
                   CHECK (permission IN ('read', 'write', 'admin')),
      granted_by   TEXT REFERENCES users(id),
      granted_at   TEXT DEFAULT (datetime('now')),
      revoked_at   TEXT,
      execution_id TEXT REFERENCES workflow_executions(id),
      UNIQUE (user_id, resource_id)
    );
  `);
}
