/* HyOpps Frontend — Vanilla JS SPA */
(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────
  let state = {
    token: localStorage.getItem('token') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    view: 'executions',       // executions | execution-detail | organizations | org-detail | users | new-execution
    executions: [],
    executionFilter: 'all',
    currentExecution: null,
    organizations: [],
    currentOrg: null,
    users: [],
    error: null,
    loading: false,
  };

  // ── API ────────────────────────────────────────────────
  const API = '/api';

  async function api(method, path, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (state.token) opts.headers['Authorization'] = 'Bearer ' + state.token;
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  // ── Render ─────────────────────────────────────────────
  function render() {
    const app = document.getElementById('app');
    if (!state.token) {
      app.innerHTML = renderLogin();
      bindLogin();
      return;
    }
    app.innerHTML = renderApp();
    bindApp();
  }

  // ── Login ──────────────────────────────────────────────
  function renderLogin() {
    return `
      <div class="login-wrap">
        <div class="login-card">
          <h1>HyOpps</h1>
          <p>Workflow Orchestration — Access Provisioning</p>
          ${state.error ? `<div class="alert alert-error">${state.error}</div>` : ''}
          <form id="login-form">
            <div class="form-group">
              <label>Email</label>
              <input type="email" id="email" value="admin@hyopps.local" required />
            </div>
            <div class="form-group">
              <label>Password</label>
              <input type="password" id="password" value="admin123" required />
            </div>
            <button class="btn btn-primary" style="width:100%" type="submit" id="login-btn">
              ${state.loading ? '<span class="spinner"></span>' : 'Sign In'}
            </button>
          </form>
        </div>
      </div>`;
  }

  function bindLogin() {
    document.getElementById('login-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      state.loading = true; state.error = null; render();
      const email = document.getElementById('email').value;
      const password = document.getElementById('password').value;
      try {
        const data = await api('POST', '/auth/login', { email, password });
        state.token = data.token;
        state.user = data.user;
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        state.loading = false;
        await loadExecutions();
        render();
      } catch (err) {
        state.error = err.message;
        state.loading = false;
        render();
      }
    });
  }

  // ── App Shell ──────────────────────────────────────────
  function renderApp() {
    return `
      <div id="app">
        <header class="topbar">
          <span class="topbar-brand">HyOpps</span>
          <div class="topbar-user">
            <span>${state.user?.firstname} ${state.user?.lastname}</span>
            <span class="badge badge-running" style="font-size:11px">${state.user?.app_role}</span>
            <button class="btn-logout" id="logout-btn">Sign out</button>
          </div>
        </header>
        <main>
          ${renderTabs()}
          ${state.error ? `<div class="alert alert-error">${state.error}</div>` : ''}
          ${renderView()}
        </main>
      </div>`;
  }

  function renderTabs() {
    if (['execution-detail', 'org-detail'].includes(state.view)) return '';
    return `
      <div class="tabs">
        <button class="tab ${state.view === 'executions' ? 'active' : ''}" data-tab="executions">Executions</button>
        <button class="tab ${state.view === 'organizations' ? 'active' : ''}" data-tab="organizations">Organizations</button>
        <button class="tab ${state.view === 'users' ? 'active' : ''}" data-tab="users">Users</button>
      </div>`;
  }

  function renderView() {
    switch (state.view) {
      case 'executions': return renderExecutions();
      case 'new-execution': return renderNewExecution();
      case 'execution-detail': return renderExecutionDetail();
      case 'organizations': return renderOrganizations();
      case 'org-detail': return renderOrgDetail();
      case 'users': return renderUsers();
      default: return '';
    }
  }

  // ── Executions List ────────────────────────────────────
  function renderExecutions() {
    const statuses = ['all', 'pending', 'running', 'awaiting_input', 'completed', 'failed'];
    const filtered = state.executionFilter === 'all'
      ? state.executions
      : state.executions.filter(e => e.status === state.executionFilter);

    return `
      <div class="section-header">
        <h2>Workflow Executions</h2>
        <button class="btn btn-primary btn-sm" id="new-execution-btn">+ New Request</button>
      </div>
      <div class="filter-bar">
        ${statuses.map(s => `<button class="filter-btn ${state.executionFilter === s ? 'active' : ''}" data-filter="${s}">${s === 'awaiting_input' ? 'Awaiting Input' : cap(s)}</button>`).join('')}
      </div>
      ${filtered.length === 0 ? `<div class="empty"><div class="empty-icon">📋</div><p>No executions found</p></div>` : `
      <div class="card" style="padding:0;overflow:hidden">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Organization</th>
              <th>Status</th>
              <th>Step</th>
              <th>Requested By</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.map(e => `
              <tr class="clickable" data-execution-id="${e.id}">
                <td><strong>${formatWorkflowName(e.workflow_name)}</strong></td>
                <td>${e.organization_name || '<span style="color:var(--text-muted)">—</span>'}</td>
                <td>${badge(e.status)}</td>
                <td style="color:var(--text-muted);font-size:13px">Step ${e.current_step_order}</td>
                <td style="color:var(--text-muted);font-size:13px">${e.requested_by_email || '—'}</td>
                <td style="color:var(--text-muted);font-size:13px">${formatDate(e.created_at)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`}`;
  }

  // ── New Execution ──────────────────────────────────────
  function renderNewExecution() {
    return `
      <span class="back-link" id="back-btn">← Back</span>
      <div class="section-header"><h2>New Onboarding Request</h2></div>
      <div class="card" style="max-width:500px">
        ${state.error ? `<div class="alert alert-error">${state.error}</div>` : ''}
        <form id="new-exec-form">
          <div class="form-group">
            <label>Workflow Type</label>
            <select name="workflow_type" required>
              <option value="">Select workflow…</option>
              <option value="new_partner">New Partner Onboarding — set up a partner org from scratch</option>
              <option value="new_partner_user">New Partner User — add user to existing partner org</option>
            </select>
          </div>
          <div style="display:flex;gap:10px;margin-top:8px">
            <button class="btn btn-primary" type="submit" ${state.loading ? 'disabled' : ''}>
              ${state.loading ? '<span class="spinner"></span> Starting…' : 'Start Workflow'}
            </button>
            <button class="btn btn-ghost" type="button" id="cancel-btn">Cancel</button>
          </div>
        </form>
      </div>`;
  }

  // ── Execution Detail ───────────────────────────────────
  function renderExecutionDetail() {
    const ex = state.currentExecution;
    if (!ex) return '<div class="empty">Loading…</div>';

    return `
      <span class="back-link" id="back-btn">← All Executions</span>
      <div class="section-header">
        <div>
          <h2>${formatWorkflowName(ex.workflow_name)}</h2>
        </div>
        ${badge(ex.status)}
      </div>
      <div class="meta-row">
        <span>ID: <strong style="font-family:monospace;font-size:12px">${ex.id}</strong></span>
        ${ex.organization_name ? `<span>Organization: <strong>${ex.organization_name}</strong></span>` : ''}
        ${ex.user_email ? `<span>User: <strong>${ex.user_email}</strong></span>` : ''}
        <span>Started: <strong>${formatDate(ex.created_at)}</strong></span>
        ${ex.completed_at ? `<span>Completed: <strong>${formatDate(ex.completed_at)}</strong></span>` : ''}
        <span>Requested by: <strong>${ex.requested_by_email || '—'}</strong></span>
      </div>
      <div class="step-list">
        ${(ex.steps || []).map(s => renderStep(s, ex)).join('')}
      </div>`;
  }

  function renderStep(s, ex) {
    const isActive = s.status === 'awaiting_input' || (s.status === 'running');
    return `
      <div class="step-item ${isActive ? 'active-step' : ''}">
        <div class="step-header">
          <div class="step-num ${stepNumClass(s.status)}">${stepIcon(s)}</div>
          <span class="step-label">${s.label}</span>
          <span class="badge badge-${s.step_type}">${s.step_type}</span>
          ${badge(s.status)}
        </div>
        <div class="step-desc">${s.description || ''}</div>
        ${renderStepData(s, ex)}
      </div>`;
  }

  function renderStepData(s, ex) {
    let html = '';

    if (s.status === 'completed' && s.output && Object.keys(s.output).length > 0) {
      html += `<div class="step-data"><div class="data-block"><dl>
        ${Object.entries(s.output).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}
      </dl></div></div>`;
    }

    if (s.status === 'completed' && s.manual_input && Object.keys(s.manual_input).length > 0) {
      const mi = s.manual_input;
      html += `<div class="step-data"><div class="data-block"><dl>
        ${Object.entries(mi).filter(([k]) => k !== 'selected_studio_company_ids').map(([k, v]) => `<dt>${k}</dt><dd>${Array.isArray(v) ? v.join(', ') : v}</dd>`).join('')}
      </dl></div>
      ${s.completed_by_email ? `<p style="font-size:12px;color:var(--text-muted);margin-top:8px">Confirmed by ${s.completed_by_email}</p>` : ''}
      </div>`;
    }

    if (s.status === 'failed') {
      html += `<div class="step-data">
        <div class="alert alert-error" style="margin:0">${s.error || 'Unknown error'}</div>
        <button class="btn btn-sm btn-danger" style="margin-top:8px" data-retry="${s.id}">Retry</button>
      </div>`;
    }

    if (s.status === 'awaiting_input') {
      html += renderManualForm(s, ex);
    }

    return html;
  }

  function renderManualForm(s, ex) {
    switch (s.step_name) {
      case 'input_studio_companies':
        return `<div class="manual-form">
          <form class="manual-input-form" data-step-id="${s.id}">
            <div class="inline-form-grid">
              <div class="form-group" style="grid-column:1/-1">
                <label>Organization Name</label>
                <input name="organization_name" placeholder="e.g. Acme Corp" required />
              </div>
              <div class="form-group">
                <label>Studio Company Name (TEST)</label>
                <input name="studio_company_name_test" placeholder="Acme Corp TEST" />
              </div>
              <div class="form-group">
                <label>Studio Company ID (TEST)</label>
                <input name="studio_company_id_test" placeholder="studio-id-test" required />
              </div>
              <div class="form-group">
                <label>Studio Company Name (PROD)</label>
                <input name="studio_company_name_prod" placeholder="Acme Corp PROD" />
              </div>
              <div class="form-group">
                <label>Studio Company ID (PROD)</label>
                <input name="studio_company_id_prod" placeholder="studio-id-prod" required />
              </div>
            </div>
            <button class="btn btn-primary btn-sm" type="submit">Confirm &amp; Continue</button>
          </form>
        </div>`;

      case 'trigger_infrabot': {
        const ctx = buildCtxFromSteps(ex.steps);
        return `<div class="manual-form">
          <div class="alert alert-info" style="margin-bottom:12px">
            Copy these params to Infrabot, then confirm below.
          </div>
          <div class="data-block" style="margin-bottom:12px"><dl>
            <dt>Name</dt><dd>${ctx.organization_name || '—'}</dd>
            <dt>Company ID (TEST)</dt><dd>${ctx.studio_company_id_test || '—'}</dd>
            <dt>Company ID (PROD)</dt><dd>${ctx.studio_company_id_prod || '—'}</dd>
          </dl></div>
          <form class="manual-input-form" data-step-id="${s.id}">
            <div class="form-group">
              <label>Cluster</label>
              <select name="keycloak_cluster" required>
                <option value="">Select cluster…</option>
                <option value="prod-eu">prod-eu</option>
                <option value="prod-us">prod-us</option>
              </select>
            </div>
            <div class="form-group">
              <label>Scopes (comma-separated)</label>
              <input name="scopes" placeholder="read, write, admin" />
            </div>
            <input type="hidden" name="keycloak_confirmed" value="true" />
            <button class="btn btn-primary btn-sm" type="submit">Mark as Completed</button>
          </form>
        </div>`;
      }

      case 'lms_setup':
        return `<div class="manual-form">
          <div class="alert alert-info" style="margin-bottom:12px">
            Add partner learning path in LMS, then confirm here.
          </div>
          <form class="manual-input-form" data-step-id="${s.id}">
            <input type="hidden" name="lms_confirmed" value="true" />
            <button class="btn btn-success btn-sm" type="submit">Mark as Completed</button>
          </form>
        </div>`;

      case 'select_organization':
        return `<div class="manual-form">
          <form class="manual-input-form" data-step-id="${s.id}">
            <div class="form-group">
              <label>Partner Organization</label>
              <select name="organization_id" required id="org-select-${s.id}">
                <option value="">Loading organizations…</option>
              </select>
            </div>
            <button class="btn btn-primary btn-sm" type="submit">Select &amp; Continue</button>
          </form>
        </div>`;

      case 'input_user_details': {
        const orgId = ex.organization_id;
        const studioCompanies = state.organizations.find(o => o.id === orgId);
        return `<div class="manual-form">
          <form class="manual-input-form" data-step-id="${s.id}">
            <div class="inline-form-grid">
              <div class="form-group">
                <label>First Name</label>
                <input name="firstname" required />
              </div>
              <div class="form-group">
                <label>Last Name</label>
                <input name="lastname" required />
              </div>
              <div class="form-group" style="grid-column:1/-1">
                <label>Email</label>
                <input type="email" name="email" required />
              </div>
            </div>
            <div class="form-group">
              <label>Languages (comma-separated, ISO codes e.g. en, de)</label>
              <input name="languages" placeholder="en, de, fr" />
            </div>
            <div class="form-group">
              <label>Skills (comma-separated)</label>
              <input name="skills" placeholder="analytics, reporting" />
            </div>
            <div class="form-group">
              <label>Roles (comma-separated)</label>
              <input name="roles" placeholder="analyst, viewer" />
            </div>
            <div class="form-group" id="studio-companies-group-${s.id}">
              <label>Studio Company Access</label>
              <p style="font-size:13px;color:var(--text-muted);margin-bottom:8px">Loading Studio companies…</p>
            </div>
            <button class="btn btn-primary btn-sm" type="submit">Confirm &amp; Continue</button>
          </form>
        </div>`;
      }

      default:
        return `<div class="manual-form">
          <form class="manual-input-form" data-step-id="${s.id}">
            <div class="form-group">
              <label>Notes (optional)</label>
              <textarea name="notes" rows="2"></textarea>
            </div>
            <button class="btn btn-primary btn-sm" type="submit">Confirm &amp; Continue</button>
          </form>
        </div>`;
    }
  }

  // Build a flat context object from step outputs and manual inputs
  function buildCtxFromSteps(steps) {
    const ctx = {};
    for (const s of steps || []) {
      if (s.output) Object.assign(ctx, s.output);
      if (s.manual_input) Object.assign(ctx, s.manual_input);
    }
    return ctx;
  }

  // ── Organizations ──────────────────────────────────────
  function renderOrganizations() {
    return `
      <div class="section-header"><h2>Organizations</h2></div>
      ${state.organizations.length === 0 ? `<div class="empty"><div class="empty-icon">🏢</div><p>No organizations yet</p></div>` : `
      <div class="card" style="padding:0;overflow:hidden">
        <table>
          <thead><tr><th>Name</th><th>Account Types</th><th>Created</th></tr></thead>
          <tbody>
            ${state.organizations.map(o => `
              <tr class="clickable" data-org-id="${o.id}">
                <td><strong>${o.name}</strong></td>
                <td>${(o.account_types || []).map(t => `<span class="badge badge-running" style="margin-right:4px">${t}</span>`).join('')}</td>
                <td style="color:var(--text-muted);font-size:13px">${formatDate(o.created_at)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`}`;
  }

  function renderOrgDetail() {
    const org = state.currentOrg;
    if (!org) return '<div class="empty">Loading…</div>';

    return `
      <span class="back-link" id="back-btn">← All Organizations</span>
      <div class="section-header">
        <h2>${org.name}</h2>
        <div>${(org.account_types || []).map(t => `<span class="badge badge-running" style="margin-right:4px">${t}</span>`).join('')}</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div>
          <h3 style="margin-bottom:12px;font-size:15px;color:var(--text-muted)">System Groups</h3>
          ${(org.system_groups || []).length === 0 ? '<p style="color:var(--text-muted);font-size:14px">None provisioned yet</p>' : `
          <div class="card" style="padding:0;overflow:hidden">
            <table>
              <thead><tr><th>Tool</th><th>Name</th><th>External ID</th></tr></thead>
              <tbody>
                ${org.system_groups.map(g => `
                  <tr>
                    <td><strong>${g.tool}</strong></td>
                    <td>${g.external_name}</td>
                    <td style="font-family:monospace;font-size:12px;color:var(--text-muted)">${g.external_id || '—'}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>`}
        </div>
        <div>
          <h3 style="margin-bottom:12px;font-size:15px;color:var(--text-muted)">Studio Companies</h3>
          ${(org.studio_companies || []).length === 0 ? '<p style="color:var(--text-muted);font-size:14px">None created yet</p>' : `
          <div class="card" style="padding:0;overflow:hidden">
            <table>
              <thead><tr><th>Name</th><th>Env</th><th>Studio ID</th></tr></thead>
              <tbody>
                ${org.studio_companies.map(sc => `
                  <tr>
                    <td><strong>${sc.name}</strong></td>
                    <td><span class="badge badge-${sc.environment === 'prod' ? 'completed' : 'running'}">${sc.environment}</span></td>
                    <td style="font-family:monospace;font-size:12px;color:var(--text-muted)">${sc.studio_id}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>`}
        </div>
      </div>
      ${org.integrations ? `
      <h3 style="margin:24px 0 12px;font-size:15px;color:var(--text-muted)">Integrations</h3>
      <div class="card"><dl class="data-block" style="border:none;padding:0">
        <dt>KeyCloak</dt><dd>${org.integrations.keycloak_confirmed ? '✓ Confirmed' : 'Pending'} ${org.integrations.keycloak_cluster ? `(${org.integrations.keycloak_cluster})` : ''}</dd>
        <dt>Metabase Collection</dt><dd>${org.integrations.metabase_collection_id || '—'}</dd>
        <dt>LMS</dt><dd>${org.integrations.lms_confirmed ? '✓ Confirmed' : 'Pending'}</dd>
      </dl></div>` : ''}`;
  }

  // ── Users ──────────────────────────────────────────────
  function renderUsers() {
    return `
      <div class="section-header"><h2>Users</h2></div>
      ${state.users.length === 0 ? `<div class="empty"><div class="empty-icon">👤</div><p>No users yet</p></div>` : `
      <div class="card" style="padding:0;overflow:hidden">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Organization</th><th>Created</th></tr></thead>
          <tbody>
            ${state.users.map(u => `
              <tr>
                <td><strong>${u.firstname} ${u.lastname}</strong></td>
                <td style="font-size:13px">${u.email}</td>
                <td>${u.app_role === 'admin' ? badge('completed') : badge('pending')} <span style="font-size:12px">${u.app_role}</span></td>
                <td style="color:var(--text-muted);font-size:13px">${u.organization_name || '—'}</td>
                <td style="color:var(--text-muted);font-size:13px">${formatDate(u.created_at)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`}`;
  }

  // ── Data loaders ───────────────────────────────────────
  async function loadExecutions() {
    try {
      state.executions = await api('GET', '/executions');
    } catch (e) { state.error = e.message; }
  }

  async function loadOrganizations() {
    try {
      state.organizations = await api('GET', '/organizations');
    } catch (e) { state.error = e.message; }
  }

  async function loadUsers() {
    try {
      state.users = await api('GET', '/users');
    } catch (e) { state.error = e.message; }
  }

  async function loadExecutionDetail(id) {
    try {
      state.currentExecution = await api('GET', '/executions/' + id);
    } catch (e) { state.error = e.message; }
  }

  async function loadOrgDetail(id) {
    try {
      state.currentOrg = await api('GET', '/organizations/' + id);
    } catch (e) { state.error = e.message; }
  }

  // ── Bind App Events ────────────────────────────────────
  function bindApp() {
    // Logout
    document.getElementById('logout-btn')?.addEventListener('click', () => {
      state.token = null; state.user = null;
      localStorage.removeItem('token'); localStorage.removeItem('user');
      render();
    });

    // Tab navigation
    document.querySelectorAll('[data-tab]').forEach(btn => {
      btn.addEventListener('click', async () => {
        state.view = btn.dataset.tab;
        state.error = null;
        if (state.view === 'executions') await loadExecutions();
        if (state.view === 'organizations') await loadOrganizations();
        if (state.view === 'users') await loadUsers();
        render();
      });
    });

    // Filter buttons
    document.querySelectorAll('[data-filter]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.executionFilter = btn.dataset.filter;
        render();
      });
    });

    // Execution row click
    document.querySelectorAll('[data-execution-id]').forEach(row => {
      row.addEventListener('click', async () => {
        await loadExecutionDetail(row.dataset.executionId);
        state.view = 'execution-detail';
        render();
        bindDetail();
      });
    });

    // Org row click
    document.querySelectorAll('[data-org-id]').forEach(row => {
      row.addEventListener('click', async () => {
        await loadOrgDetail(row.dataset.orgId);
        state.view = 'org-detail';
        render();
        bindApp();
      });
    });

    // New execution button
    document.getElementById('new-execution-btn')?.addEventListener('click', () => {
      state.view = 'new-execution';
      state.error = null;
      render();
      bindNewExecution();
    });

    // Back button
    document.getElementById('back-btn')?.addEventListener('click', async () => {
      state.error = null;
      if (state.view === 'execution-detail') { state.view = 'executions'; await loadExecutions(); }
      else if (state.view === 'org-detail') { state.view = 'organizations'; await loadOrganizations(); }
      else if (state.view === 'new-execution') { state.view = 'executions'; }
      render();
      bindApp();
    });

    // Bind detail if needed
    if (state.view === 'execution-detail') bindDetail();
  }

  function bindNewExecution() {
    document.getElementById('cancel-btn')?.addEventListener('click', () => {
      state.view = 'executions';
      render();
      bindApp();
    });

    document.getElementById('new-exec-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const wfType = e.target.querySelector('[name=workflow_type]').value;
      state.loading = true; state.error = null; render(); bindNewExecution();
      try {
        const exec = await api('POST', '/executions', { workflow_type: wfType });
        state.loading = false;
        // Brief pause then show detail
        await new Promise(r => setTimeout(r, 400));
        await loadExecutionDetail(exec.id);
        state.view = 'execution-detail';
        render();
        bindDetail();
      } catch (err) {
        state.error = err.message;
        state.loading = false;
        render();
        bindNewExecution();
      }
    });
  }

  function bindDetail() {
    // Manual input forms
    document.querySelectorAll('.manual-input-form').forEach(form => {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const stepId = form.dataset.stepId;
        const fd = new FormData(form);
        const input = {};
        for (const [k, v] of fd.entries()) {
          if (k === 'languages' || k === 'skills' || k === 'roles') {
            input[k] = v ? v.split(',').map(s => s.trim()).filter(Boolean) : [];
          } else {
            input[k] = v;
          }
        }

        // Collect studio company checkboxes
        const checkboxes = form.querySelectorAll('[name="selected_studio_company_ids"]');
        if (checkboxes.length > 0) {
          input.selected_studio_company_ids = Array.from(checkboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
        }

        const submitBtn = form.querySelector('[type=submit]');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> Processing…';
        state.error = null;

        try {
          await api('POST', `/executions/${state.currentExecution.id}/steps/${stepId}/input`, input);
          // Poll until not running
          await pollUntilStable(state.currentExecution.id);
          await loadExecutionDetail(state.currentExecution.id);
          render();
          bindDetail();
        } catch (err) {
          state.error = err.message;
          render();
          bindDetail();
        }
      });
    });

    // Retry buttons
    document.querySelectorAll('[data-retry]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const stepId = btn.dataset.retry;
        btn.disabled = true; btn.textContent = 'Retrying…';
        try {
          await api('POST', `/executions/${state.currentExecution.id}/steps/${stepId}/retry`);
          await pollUntilStable(state.currentExecution.id);
          await loadExecutionDetail(state.currentExecution.id);
          render();
          bindDetail();
        } catch (err) {
          state.error = err.message;
          render();
          bindDetail();
        }
      });
    });

    // Populate org select for 'select_organization' step
    const orgSelect = document.querySelector('[id^="org-select-"]');
    if (orgSelect) {
      api('GET', '/organizations').then(orgs => {
        orgSelect.innerHTML = '<option value="">Select organization…</option>' +
          orgs.map(o => `<option value="${o.id}">${o.name}</option>`).join('');
      });
    }

    // Populate studio companies checkboxes for 'input_user_details' step
    const ex = state.currentExecution;
    if (ex?.organization_id) {
      const groupEl = document.querySelector('[id^="studio-companies-group-"]');
      if (groupEl) {
        api('GET', '/organizations/' + ex.organization_id).then(org => {
          const companies = org.studio_companies || [];
          if (companies.length === 0) {
            groupEl.querySelector('p').textContent = 'No Studio companies for this organization.';
          } else {
            groupEl.innerHTML = `<label>Studio Company Access</label>
              <div class="checkbox-list">
                ${companies.map(sc => `
                  <label class="checkbox-item">
                    <input type="checkbox" name="selected_studio_company_ids" value="${sc.id}" checked />
                    ${sc.name} <span class="badge badge-${sc.environment === 'prod' ? 'completed' : 'running'}">${sc.environment}</span>
                  </label>`).join('')}
              </div>`;
          }
        });
      }
    }

    // Auto-refresh if running
    if (ex && (ex.status === 'running')) {
      setTimeout(async () => {
        await loadExecutionDetail(ex.id);
        if (state.view === 'execution-detail') { render(); bindDetail(); }
      }, 1500);
    }
  }

  // Poll until execution is no longer 'running'
  async function pollUntilStable(execId) {
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 400));
      const exec = await api('GET', '/executions/' + execId);
      if (exec.status !== 'running') return;
    }
  }

  // ── Helpers ────────────────────────────────────────────
  function badge(status) {
    return `<span class="badge badge-${status}">${status === 'awaiting_input' ? 'Awaiting Input' : cap(status)}</span>`;
  }

  function stepNumClass(status) {
    const map = { completed: 'done', failed: 'fail', awaiting_input: 'waiting', running: 'running' };
    return map[status] || '';
  }

  function stepIcon(s) {
    if (s.status === 'completed') return '✓';
    if (s.status === 'failed') return '✕';
    if (s.status === 'awaiting_input') return '!';
    if (s.status === 'running') return '…';
    return s.step_order;
  }

  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  function formatWorkflowName(name) {
    const map = { new_partner: 'New Partner Onboarding', new_partner_user: 'New Partner User' };
    return map[name] || name;
  }

  function formatDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  }

  // ── Init ───────────────────────────────────────────────
  async function init() {
    if (state.token) {
      await Promise.all([loadExecutions(), loadOrganizations()]);
    }
    render();
  }

  init();
})();
