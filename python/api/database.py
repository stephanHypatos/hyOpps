import sqlite3
import os
import json
import uuid
import bcrypt
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "hyopps_py.db")


def get_db() -> sqlite3.Connection:
    """Return a new SQLite connection. Each caller (thread) gets its own connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema() -> None:
    conn = get_db()
    conn.executescript("""
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
                                   CHECK (status IN ('pending','running','awaiting_input','completed','failed')),
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
                               CHECK (status IN ('pending','running','awaiting_input','completed','failed','skipped')),
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
                         CHECK (permission IN ('read','write','admin')),
            granted_by   TEXT REFERENCES users(id),
            granted_at   TEXT DEFAULT (datetime('now')),
            revoked_at   TEXT,
            execution_id TEXT REFERENCES workflow_executions(id),
            UNIQUE (user_id, resource_id)
        );

        CREATE TABLE IF NOT EXISTS user_studio_companies (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            studio_id  TEXT NOT NULL UNIQUE,
            name       TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def seed_data() -> None:
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM workflow_definitions").fetchone()[0]
    if count > 0:
        conn.close()
        return

    now = datetime.utcnow().isoformat()

    # Resources
    resources = [
        ("Studio", "studio", 1),
        ("Metabase", "insights", 1),
        ("Microsoft Teams", "communication", 1),
        ("Slack", "communication", 1),
        ("LMS", "learning", 0),
        ("KeyCloak", "auth", 0),
    ]
    for name, rtype, has_api in resources:
        conn.execute(
            "INSERT OR IGNORE INTO resources (id, name, type, has_api) VALUES (?,?,?,?)",
            (str(uuid.uuid4()), name, rtype, has_api)
        )

    # Workflow definitions
    np_id = str(uuid.uuid4())
    npu_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO workflow_definitions (id, name, description) VALUES (?,?,?)",
        (np_id, "new_partner", "Onboard a new partner organization from scratch")
    )
    conn.execute(
        "INSERT OR IGNORE INTO workflow_definitions (id, name, description) VALUES (?,?,?)",
        (npu_id, "new_partner_user", "Add a new user to an existing partner organization")
    )

    # New Partner steps
    np_steps = [
        (1, "input_studio_companies", "Input Studio Companies", "manual",
         "Admin creates companies in Studio UI, then inputs org name + Studio TEST/PROD IDs"),
        (2, "trigger_infrabot", "Trigger Infrabot", "manual",
         "Admin triggers Infrabot with name, company ID, cluster, scopes. Confirms when KeyCloak creds stored"),
        (3, "clone_metabase_collection", "Clone Metabase Collection", "auto",
         "Clone template collection for the new partner via Metabase API"),
        (4, "create_metabase_group", "Create Metabase User Group", "auto",
         "Create a user group in Metabase and store the group ID"),
        (5, "grant_metabase_db_access", "Grant DB Access to Metabase Group", "auto",
         "Grant database access to the Metabase group"),
        (6, "create_teams_channel", "Create Teams Channel", "auto",
         "Create a dedicated Teams channel via MS Graph API"),
        (7, "create_slack_group", "Create Slack Group", "auto",
         "Create a Slack group via Slack API"),
        (8, "lms_setup", "LMS Setup", "manual",
         "Admin adds partner learning path in LMS. Confirm when done"),
    ]
    for order, name, label, stype, desc in np_steps:
        conn.execute(
            "INSERT OR IGNORE INTO workflow_step_definitions (id,workflow_definition_id,step_order,name,label,type,description) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), np_id, order, name, label, stype, desc)
        )

    # New Partner User steps
    npu_steps = [
        (1, "select_organization", "Select Organization", "manual",
         "Admin selects existing partner organization from list"),
        (2, "input_user_details", "Input User Details", "manual",
         "Admin inputs user details. User will automatically receive their own personal Studio company."),
        (3, "add_user_to_studio_companies", "Add User to Org Studio Groups", "auto",
         "Add user to the org's Studio platform groups for shared resources"),
        (4, "add_user_to_metabase_group", "Add User to Metabase Group", "auto",
         "Add user to the org's Metabase system group"),
        (5, "add_user_to_teams_channel", "Add User to Teams Channel", "auto",
         "Add user to the org's Teams system group"),
        (6, "add_user_to_slack_group", "Add User to Slack Group", "auto",
         "Add user to the org's Slack system group"),
        (7, "create_studio_user_company", "Create User-Specific Studio Company", "auto",
         "Create a user-specific Studio company entry"),
        (8, "send_studio_invite", "Send Studio Invite", "auto",
         "Send invite to Studio platform"),
        (9, "share_documentation", "Share Documentation", "auto",
         "Send documentation links via email/Slack"),
    ]
    for order, name, label, stype, desc in npu_steps:
        conn.execute(
            "INSERT OR IGNORE INTO workflow_step_definitions (id,workflow_definition_id,step_order,name,label,type,description) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), npu_id, order, name, label, stype, desc)
        )

    # Default admin user
    password_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
    conn.execute(
        "INSERT OR IGNORE INTO users (id,firstname,lastname,email,app_role,password_hash) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), "Admin", "User", "admin@hyopps.local", "admin", password_hash)
    )

    conn.commit()
    conn.close()
    print("Database seeded. Default admin: admin@hyopps.local / admin123")
