"""
HyOpps — Streamlit Admin Panel
Calls the FastAPI backend at API_URL (default: http://localhost:8000)
"""

import os
import time
from typing import Union
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="HyOpps",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #1a1d27; }
    .block-container { padding-top: 1.5rem; }
    .step-card { border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; border: 1px solid #2e3347; }
    .step-card-active { border-color: #6366f1 !important; }
    .badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }
    .b-pending    { background:#1e293b; color:#94a3b8; }
    .b-running    { background:#1e3a5f; color:#60a5fa; }
    .b-awaiting   { background:#422006; color:#fbbf24; }
    .b-completed  { background:#052e16; color:#4ade80; }
    .b-failed     { background:#450a0a; color:#f87171; }
    .b-auto       { background:#1e1b4b; color:#a5b4fc; }
    .b-manual     { background:#431407; color:#fdba74; }
</style>
""", unsafe_allow_html=True)


# ── API helpers ────────────────────────────────────────────────────────────

def _headers():
    token = st.session_state.get("token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def api_get(path: str) -> Union[list, dict]:
    resp = requests.get(f"{API_URL}{path}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str, body: dict = None) -> dict:
    resp = requests.post(f"{API_URL}{path}", json=body or {}, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def api_put(path: str, body: dict) -> dict:
    resp = requests.put(f"{API_URL}{path}", json=body, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def api_delete(path: str) -> dict:
    resp = requests.delete(f"{API_URL}{path}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def poll_until_stable(execution_id: str, base: str = "/api/executions", max_wait: float = 5.0) -> dict:
    """Poll execution until status is not 'running'."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        ex = api_get(f"{base}/{execution_id}")
        if ex["status"] != "running":
            return ex
        time.sleep(0.4)
    return api_get(f"{base}/{execution_id}")


# ── Status helpers ─────────────────────────────────────────────────────────

STATUS_COLORS = {
    "pending":       ("⬜", "#94a3b8", "b-pending"),
    "running":       ("🔵", "#60a5fa", "b-running"),
    "awaiting_input":("🟡", "#fbbf24", "b-awaiting"),
    "completed":     ("✅", "#4ade80", "b-completed"),
    "failed":        ("❌", "#f87171", "b-failed"),
    "skipped":       ("⬜", "#94a3b8", "b-pending"),
}


def status_badge(status: str) -> str:
    icon, _, css = STATUS_COLORS.get(status, ("?", "#fff", ""))
    label = "Awaiting Input" if status == "awaiting_input" else status.capitalize()
    return f'<span class="badge {css}">{icon} {label}</span>'


def type_badge(t: str) -> str:
    css = "b-auto" if t == "auto" else "b-manual"
    return f'<span class="badge {css}">{t}</span>'


def step_num_color(status: str) -> str:
    colors = {"completed": "🟢", "failed": "🔴", "awaiting_input": "🟡", "running": "🔵"}
    return colors.get(status, "⚪")


def _role_icon(role: str) -> str:
    return {"admin": "🔑", "partner_admin": "🏢", "user": "👤"}.get(role, "👤")


# ── Login ──────────────────────────────────────────────────────────────────

def show_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("## ⚙️ HyOpps")
        st.caption("Workflow Orchestration — Access Provisioning")
        st.divider()

        with st.form("login_form"):
            email = st.text_input("Email", value="admin@hyopps.local")
            password = st.text_input("Password", type="password", value="admin123")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            try:
                data = api_post("/api/auth/login", {"email": email, "password": password})
                st.session_state["token"] = data["token"]
                st.session_state["user"] = data["user"]
                role = data["user"].get("app_role", "user")
                if role == "partner_admin":
                    st.session_state["page"] = "partner_dashboard"
                else:
                    st.session_state["page"] = "executions"
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")


# ── Admin Sidebar ──────────────────────────────────────────────────────────

def show_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ HyOpps")
        user = st.session_state.get("user", {})
        st.caption(f"👤 {user.get('firstname','')} {user.get('lastname','')}  ·  `{user.get('app_role','')}`")
        st.divider()

        pages = {
            "📋 Executions": "executions",
            "🏢 Organizations": "organizations",
            "👤 Users": "users",
        }
        current = st.session_state.get("page", "executions")
        for label, key in pages.items():
            if st.button(label, use_container_width=True,
                         type="primary" if current == key else "secondary"):
                st.session_state["page"] = key
                st.session_state.pop("viewing_execution_id", None)
                st.session_state.pop("viewing_org_id", None)
                st.rerun()

        st.divider()
        if st.button("Sign Out", use_container_width=True):
            for k in list(st.session_state.keys()):
                st.session_state.pop(k, None)
            st.rerun()


# ── Executions List ────────────────────────────────────────────────────────

def show_executions():
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.markdown("## Workflow Executions")
    with col_btn:
        if st.button("＋ New Request", type="primary", use_container_width=True):
            st.session_state["page"] = "new_execution"
            st.rerun()

    filter_options = ["all", "pending", "running", "awaiting_input", "completed", "failed"]
    selected_filter = st.session_state.get("exec_filter", "all")
    cols = st.columns(len(filter_options))
    for i, f in enumerate(filter_options):
        with cols[i]:
            label = "Awaiting Input" if f == "awaiting_input" else f.capitalize()
            if st.button(label, use_container_width=True,
                         type="primary" if selected_filter == f else "secondary",
                         key=f"filter_{f}"):
                st.session_state["exec_filter"] = f
                st.rerun()

    st.divider()

    try:
        executions = api_get("/api/executions")
    except Exception as e:
        st.error(f"Failed to load executions: {e}")
        return

    selected_filter = st.session_state.get("exec_filter", "all")
    if selected_filter != "all":
        executions = [e for e in executions if e["status"] == selected_filter]

    if not executions:
        st.info("No executions found.")
        return

    for ex in executions:
        icon, _, _ = STATUS_COLORS.get(ex["status"], ("?", "", ""))
        wf_labels = {"new_partner": "New Partner Onboarding", "new_partner_user": "New Partner User"}
        wf_label = wf_labels.get(ex["workflow_name"], ex["workflow_name"])

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 1])
            with c1:
                st.markdown(f"**{wf_label}**")
                st.caption(f"`{ex['id'][:8]}…`")
            with c2:
                st.markdown(f"**Org:** {ex.get('organization_name') or '—'}")
                st.caption(f"Step {ex['current_step_order']}")
            with c3:
                st.markdown(status_badge(ex["status"]), unsafe_allow_html=True)
            with c4:
                st.caption(f"By: {ex.get('requested_by_email','—')}")
                st.caption(ex["created_at"][:16] if ex["created_at"] else "")
            with c5:
                if st.button("View", key=f"view_{ex['id']}", use_container_width=True):
                    st.session_state["viewing_execution_id"] = ex["id"]
                    st.session_state["page"] = "execution_detail"
                    st.rerun()


# ── New Execution ──────────────────────────────────────────────────────────

def show_new_execution():
    if st.button("← Back to Executions"):
        st.session_state["page"] = "executions"
        st.rerun()

    st.markdown("## New Onboarding Request")

    with st.form("new_exec_form"):
        wf_type = st.selectbox(
            "Workflow Type",
            options=["new_partner", "new_partner_user"],
            format_func=lambda x: {
                "new_partner": "New Partner Onboarding — set up a partner org from scratch",
                "new_partner_user": "New Partner User — add user to existing partner org",
            }.get(x, x)
        )
        submitted = st.form_submit_button("Start Workflow", type="primary")

    if submitted:
        with st.spinner("Starting workflow…"):
            try:
                ex = api_post("/api/executions", {"workflow_type": wf_type})
                time.sleep(0.5)
                st.session_state["viewing_execution_id"] = ex["id"]
                st.session_state["page"] = "execution_detail"
                st.rerun()
            except Exception as e:
                st.error(f"Failed to create execution: {e}")


# ── Execution Detail ───────────────────────────────────────────────────────

def show_execution_detail():
    exec_id = st.session_state.get("viewing_execution_id")
    if not exec_id:
        st.session_state["page"] = "executions"
        st.rerun()

    if st.button("← All Executions"):
        st.session_state.pop("viewing_execution_id", None)
        st.session_state["page"] = "executions"
        st.rerun()

    try:
        ex = api_get(f"/api/executions/{exec_id}")
    except Exception as e:
        st.error(f"Failed to load execution: {e}")
        return

    _show_execution_view(ex, exec_api_base="/api/executions")


def _show_execution_view(ex: dict, exec_api_base: str):
    """Shared execution detail renderer used by both admin and partner panels."""
    wf_labels = {"new_partner": "New Partner Onboarding", "new_partner_user": "New Partner User"}
    wf_label = wf_labels.get(ex["workflow_name"], ex["workflow_name"])

    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"## {wf_label}")
    with col2:
        st.markdown(status_badge(ex["status"]), unsafe_allow_html=True)

    meta_cols = st.columns(4)
    with meta_cols[0]:
        st.metric("Status", ex["status"].replace("_", " ").title())
    with meta_cols[1]:
        st.metric("Organization", ex.get("organization_name") or "—")
    with meta_cols[2]:
        st.metric("Requested By", ex.get("requested_by_email") or "—")
    with meta_cols[3]:
        st.metric("Step", f"{ex['current_step_order']}")

    st.caption(f"ID: `{ex['id']}` · Started: {ex['created_at'][:16] if ex['created_at'] else '—'}")

    if ex["status"] == "running":
        with st.spinner("Processing steps…"):
            time.sleep(1)
        ex = api_get(f"{exec_api_base}/{ex['id']}")

    st.divider()
    st.markdown("### Steps")

    for step in ex.get("steps", []):
        _render_step(step, ex, exec_api_base)


def _render_step(step: dict, ex: dict, exec_api_base: str):
    status = step["status"]
    num_icon = step_num_color(status)

    with st.container(border=True):
        hc1, hc2, hc3, hc4 = st.columns([0.4, 4, 1.5, 1.5])
        with hc1:
            st.markdown(f"### {num_icon}")
        with hc2:
            st.markdown(f"**{step['label']}**")
            st.caption(step.get("description", ""))
        with hc3:
            st.markdown(type_badge(step["step_type"]), unsafe_allow_html=True)
        with hc4:
            st.markdown(status_badge(status), unsafe_allow_html=True)

        if status == "completed" and step.get("output"):
            with st.expander("Output data", expanded=False):
                for k, v in step["output"].items():
                    st.code(f"{k}: {v}", language=None)

        if status == "completed" and step.get("manual_input"):
            mi = {k: v for k, v in step["manual_input"].items()
                  if k != "selected_studio_company_ids" and v is not None}
            if mi:
                with st.expander("Manual input submitted", expanded=False):
                    for k, v in mi.items():
                        label = k.replace("_", " ").title()
                        if isinstance(v, list):
                            st.text(f"{label}: {', '.join(v)}")
                        else:
                            st.text(f"{label}: {v}")
                    if step.get("completed_by_email"):
                        st.caption(f"Confirmed by {step['completed_by_email']}")

        if status == "failed":
            st.error(f"Error: {step.get('error', 'Unknown error')}")
            retry_path = f"{exec_api_base}/{ex['id']}/steps/{step['id']}/retry"
            if st.button("Retry", key=f"retry_{step['id']}", type="secondary"):
                with st.spinner("Retrying…"):
                    try:
                        api_post(retry_path)
                        time.sleep(1.5)
                    except Exception as e:
                        st.error(str(e))
                st.rerun()

        if status == "awaiting_input":
            st.divider()
            _render_manual_form(step, ex, exec_api_base)


def _render_manual_form(step: dict, ex: dict, exec_api_base: str):
    step_name = step["step_name"]
    step_id = step["id"]
    exec_id = ex["id"]

    def _submit(data: dict):
        with st.spinner("Processing…"):
            try:
                api_post(f"{exec_api_base}/{exec_id}/steps/{step_id}/input", data)
                time.sleep(0.5)
                poll_until_stable(exec_id, base=exec_api_base)
            except Exception as e:
                st.error(str(e))
                return
        st.success("Step completed!")
        time.sleep(0.5)
        st.rerun()

    if step_name == "input_studio_companies":
        st.markdown("**Enter Studio company details**")
        with st.form(f"form_{step_id}"):
            org_name = st.text_input("Organization Name *", placeholder="e.g. Acme Corp")
            col1, col2 = st.columns(2)
            with col1:
                test_name = st.text_input("Studio Company Name (TEST)", placeholder="Acme Corp TEST")
                test_id = st.text_input("Studio Company ID (TEST) *", placeholder="studio-test-001")
            with col2:
                prod_name = st.text_input("Studio Company Name (PROD)", placeholder="Acme Corp PROD")
                prod_id = st.text_input("Studio Company ID (PROD) *", placeholder="studio-prod-001")
            submitted = st.form_submit_button("Confirm & Continue", type="primary")
        if submitted:
            if not org_name or not test_id or not prod_id:
                st.warning("Organization Name and both Studio IDs are required.")
            else:
                _submit({
                    "organization_name": org_name,
                    "studio_company_name_test": test_name or f"{org_name} TEST",
                    "studio_company_id_test": test_id,
                    "studio_company_name_prod": prod_name or f"{org_name} PROD",
                    "studio_company_id_prod": prod_id,
                })

    elif step_name == "trigger_infrabot":
        ctx = _build_ctx(ex)
        st.markdown("**Copy these parameters to Infrabot, then confirm below.**")
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Organization:** {ctx.get('organization_name', '—')}")
            st.info(f"**Studio ID (TEST):** {ctx.get('studio_company_id_test', '—')}")
        with col2:
            st.info(f"**Studio ID (PROD):** {ctx.get('studio_company_id_prod', '—')}")
        with st.form(f"form_{step_id}"):
            cluster = st.selectbox("Cluster *", ["prod-eu", "prod-us"])
            scopes = st.text_input("Scopes", placeholder="read, write, admin")
            submitted = st.form_submit_button("Mark as Completed", type="primary")
        if submitted:
            _submit({"keycloak_cluster": cluster, "scopes": scopes, "keycloak_confirmed": True})

    elif step_name == "lms_setup":
        st.info("Add the partner learning path in LMS, then confirm here.")
        with st.form(f"form_{step_id}"):
            submitted = st.form_submit_button("Mark as Completed ✓", type="primary")
        if submitted:
            _submit({"lms_confirmed": True})

    elif step_name == "select_organization":
        try:
            orgs = api_get("/api/organizations")
        except Exception as e:
            st.error(str(e))
            return
        if not orgs:
            st.warning("No organizations exist yet. Create a partner org first.")
            return
        org_options = {o["name"]: o["id"] for o in orgs}
        with st.form(f"form_{step_id}"):
            selected_name = st.selectbox("Partner Organization *", list(org_options.keys()))
            submitted = st.form_submit_button("Select & Continue", type="primary")
        if submitted:
            _submit({"organization_id": org_options[selected_name]})

    elif step_name == "input_user_details":
        st.info("This user will automatically receive their own personal Studio company upon onboarding.")
        with st.form(f"form_{step_id}"):
            col1, col2 = st.columns(2)
            with col1:
                firstname = st.text_input("First Name *")
            with col2:
                lastname = st.text_input("Last Name *")
            email = st.text_input("Email *", placeholder="user@partner.com")
            col3, col4 = st.columns(2)
            with col3:
                languages = st.text_input("Languages (comma-separated)", placeholder="en, de, fr")
            with col4:
                skills = st.text_input("Skills (comma-separated)", placeholder="analytics, reporting")
            roles = st.text_input("Roles (comma-separated)", placeholder="analyst, viewer")
            submitted = st.form_submit_button("Confirm & Continue", type="primary")
        if submitted:
            if not firstname or not lastname or not email:
                st.warning("First name, last name, and email are required.")
            else:
                _submit({
                    "firstname": firstname,
                    "lastname": lastname,
                    "email": email,
                    "languages": [x.strip() for x in languages.split(",") if x.strip()],
                    "skills": [x.strip() for x in skills.split(",") if x.strip()],
                    "roles": [x.strip() for x in roles.split(",") if x.strip()],
                })
    else:
        st.info("Complete the required action, then confirm below.")
        with st.form(f"form_{step_id}"):
            notes = st.text_area("Notes (optional)")
            submitted = st.form_submit_button("Confirm & Continue", type="primary")
        if submitted:
            _submit({"notes": notes})


def _build_ctx(ex: dict) -> dict:
    ctx = {}
    for step in ex.get("steps", []):
        if step.get("output"):
            ctx.update(step["output"])
        if step.get("manual_input"):
            ctx.update(step["manual_input"])
    return ctx


# ── Organizations ──────────────────────────────────────────────────────────

def show_organizations():
    st.markdown("## Organizations")

    editing_org = st.session_state.get("editing_org")
    if editing_org:
        _show_edit_org_form(editing_org)
        return

    try:
        orgs = api_get("/api/organizations")
    except Exception as e:
        st.error(str(e))
        return

    if not orgs:
        st.info("No organizations yet. Start a New Partner Onboarding workflow to create one.")
        return

    for org in orgs:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 1])
            with c1:
                st.markdown(f"**{org['name']}**")
                types = org.get("account_types", ["partner"])
                st.caption(" · ".join(types))
            with c2:
                st.caption(f"Created: {org['created_at'][:10] if org['created_at'] else '—'}")
            with c3:
                if st.button("Details", key=f"org_{org['id']}", use_container_width=True):
                    st.session_state["viewing_org_id"] = org["id"]
                    st.session_state["page"] = "org_detail"
                    st.rerun()
            with c4:
                if st.button("Edit", key=f"edit_org_{org['id']}", use_container_width=True):
                    st.session_state["editing_org"] = org
                    st.rerun()
            with c5:
                if st.button("Delete", key=f"del_org_{org['id']}", use_container_width=True, type="secondary"):
                    st.session_state["confirm_delete_org"] = org["id"]
                    st.rerun()

        if st.session_state.get("confirm_delete_org") == org["id"]:
            st.warning(f"Delete **{org['name']}**? All associated users, studio companies and integrations will also be removed.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, delete", key=f"yes_del_org_{org['id']}", type="primary"):
                    try:
                        api_delete(f"/api/organizations/{org['id']}")
                        st.session_state.pop("confirm_delete_org", None)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with col_no:
                if st.button("Cancel", key=f"no_del_org_{org['id']}"):
                    st.session_state.pop("confirm_delete_org", None)
                    st.rerun()


def _show_edit_org_form(org: dict):
    if st.button("← Back to Organizations"):
        st.session_state.pop("editing_org", None)
        st.rerun()

    st.markdown(f"## Edit Organization — {org['name']}")

    with st.form("edit_org_form"):
        name = st.text_input("Organization Name *", value=org.get("name", ""))
        current_types = org.get("account_types", ["partner"])
        account_types_str = st.text_input(
            "Account Types (comma-separated)",
            value=", ".join(current_types)
        )
        submitted = st.form_submit_button("Save Changes", type="primary")

    if submitted:
        if not name:
            st.warning("Organization name is required.")
        else:
            types = [t.strip() for t in account_types_str.split(",") if t.strip()]
            try:
                api_put(f"/api/organizations/{org['id']}", {
                    "name": name,
                    "account_types": types or ["partner"],
                })
                st.success("Organization updated.")
                st.session_state.pop("editing_org", None)
                st.rerun()
            except Exception as e:
                st.error(str(e))


def show_org_detail():
    org_id = st.session_state.get("viewing_org_id")
    if not org_id:
        st.session_state["page"] = "organizations"
        st.rerun()

    if st.button("← All Organizations"):
        st.session_state.pop("viewing_org_id", None)
        st.session_state["page"] = "organizations"
        st.rerun()

    try:
        org = api_get(f"/api/organizations/{org_id}")
    except Exception as e:
        st.error(str(e))
        return

    st.markdown(f"## {org['name']}")
    st.caption(f"Account types: {', '.join(org.get('account_types', []))}")
    st.divider()

    col1, col2 = st.columns(2)

    groups = org.get("system_groups", [])
    groups_by_tool = {g["tool"]: g for g in groups}

    with col1:
        st.markdown("### System Groups")
        if not groups:
            st.caption("None provisioned yet.")
        else:
            for g in groups:
                with st.container(border=True):
                    st.markdown(f"**{g['tool'].title()}** · `{g['external_name']}`")
                    if g.get("external_id"):
                        st.caption(f"External ID: `{g['external_id']}`")

    with col2:
        st.markdown("### Studio Companies")
        companies = org.get("studio_companies", [])
        if not companies:
            st.caption("None created yet.")
        else:
            for sc in companies:
                env_color = "🟢" if sc["environment"] == "prod" else "🔵"
                with st.container(border=True):
                    st.markdown(f"{env_color} **{sc['name']}** `{sc['environment'].upper()}`")
                    st.caption(f"Studio ID: `{sc['studio_id']}`")

    integ = org.get("integrations")
    if integ:
        st.divider()
        st.markdown("### Integrations")
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            kc = "✅ Confirmed" if integ.get("keycloak_confirmed") else "⏳ Pending"
            cluster = f" ({integ['keycloak_cluster']})" if integ.get("keycloak_cluster") else ""
            st.metric("KeyCloak", kc + cluster)
        with ic2:
            mb = integ.get("metabase_collection_id") or "—"
            st.metric("Metabase Collection", mb)
        with ic3:
            lms = "✅ Confirmed" if integ.get("lms_confirmed") else "⏳ Pending"
            st.metric("LMS", lms)

    # ── Documentation links ────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Documentation Links")
    doc = org.get("documentation") or {}
    doc_fields = [
        ("Internal Documentation", "internal_docu"),
        ("General Documentation",  "generique_docu"),
        ("Additional Documentation", "add_docu"),
    ]

    any_doc = any(doc.get(k) for _, k in doc_fields)
    if any_doc:
        for label, key in doc_fields:
            url = doc.get(key)
            if url:
                st.markdown(f"**{label}:** [{url}]({url})")
    else:
        st.caption("No documentation links configured yet.")

    with st.expander("Edit documentation links"):
        doc_id_key = f"doc_{org_id}"
        with st.form(doc_id_key):
            internal = st.text_input(
                "Internal Documentation URL",
                value=doc.get("internal_docu") or "",
                placeholder="https://internal.example.com/docs/partner-xyz",
            )
            generique = st.text_input(
                "General Documentation URL",
                value=doc.get("generique_docu") or "",
                placeholder="https://docs.example.com",
            )
            add = st.text_input(
                "Additional Documentation URL",
                value=doc.get("add_docu") or "",
                placeholder="https://example.com/getting-started",
            )
            doc_submitted = st.form_submit_button("Save Links", type="primary")
        if doc_submitted:
            try:
                api_put(f"/api/organizations/{org_id}/documentation", {
                    "internal_docu": internal.strip() or None,
                    "generique_docu": generique.strip() or None,
                    "add_docu": add.strip() or None,
                })
                st.success("Documentation links saved.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.divider()
    with st.expander("Edit / add group IDs"):
        grp_tools = [
            ("metabase", "Metabase", "Permission group integer ID, e.g. 12"),
            ("teams",    "Teams",    "Teams channel / group ID"),
            ("slack",    "Slack",    "Slack usergroup ID"),
        ]
        gcols = st.columns(len(grp_tools))
        for i, (tool, label, id_hint) in enumerate(grp_tools):
            existing_g = groups_by_tool.get(tool, {})
            id_key   = f"grp_id_{tool}_{org_id}"
            name_key = f"grp_name_{tool}_{org_id}"
            # Seed session state from DB only on first render (preserve user edits)
            if id_key not in st.session_state:
                st.session_state[id_key] = existing_g.get("external_id") or ""
            if name_key not in st.session_state:
                st.session_state[name_key] = existing_g.get("external_name") or ""
            with gcols[i]:
                st.markdown(f"**{label}**")
                ext_id   = st.text_input("External ID",   key=id_key,   placeholder=id_hint)
                ext_name = st.text_input("Display name",  key=name_key, placeholder="ext-partnerA")
                if st.button(f"Save {label}", key=f"grp_save_{tool}_{org_id}", use_container_width=True):
                    try:
                        api_put(f"/api/organizations/{org_id}/groups", {
                            "tool": tool,
                            "external_id": ext_id.strip() or None,
                            "external_name": ext_name.strip() or None,
                        })
                        # Clear so next render re-seeds from DB
                        st.session_state.pop(id_key, None)
                        st.session_state.pop(name_key, None)
                        st.success(f"{label} saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


# ── Users ──────────────────────────────────────────────────────────────────

def show_users():
    st.markdown("## Users")

    editing_user = st.session_state.get("editing_user")
    if editing_user:
        _show_edit_user_form(editing_user)
        return

    try:
        users = api_get("/api/users")
    except Exception as e:
        st.error(str(e))
        return

    if not users:
        st.info("No users yet.")
        return

    for user in users:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
            with c1:
                st.markdown(f"**{user['firstname']} {user['lastname']}**")
                st.caption(user["email"])
            with c2:
                icon = _role_icon(user["app_role"])
                st.markdown(f"{icon} `{user['app_role']}`")
            with c3:
                st.caption(f"Org: {user.get('organization_name') or '—'}")
                if user.get("personal_studio_name"):
                    st.caption(f"Studio: {user['personal_studio_name']}")
            with c4:
                if st.button("Edit", key=f"edit_user_{user['id']}", use_container_width=True):
                    st.session_state["editing_user"] = user
                    st.rerun()
            with c5:
                if st.button("Delete", key=f"del_user_{user['id']}", use_container_width=True, type="secondary"):
                    st.session_state["confirm_delete_user"] = user["id"]
                    st.rerun()

        if st.session_state.get("confirm_delete_user") == user["id"]:
            st.warning(f"Delete **{user['firstname']} {user['lastname']}**? This cannot be undone.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, delete", key=f"yes_del_user_{user['id']}", type="primary"):
                    try:
                        api_delete(f"/api/users/{user['id']}")
                        st.session_state.pop("confirm_delete_user", None)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with col_no:
                if st.button("Cancel", key=f"no_del_user_{user['id']}"):
                    st.session_state.pop("confirm_delete_user", None)
                    st.rerun()


def _show_edit_user_form(user: dict):
    if st.button("← Back to Users"):
        st.session_state.pop("editing_user", None)
        st.rerun()

    st.markdown(f"## Edit User — {user['firstname']} {user['lastname']}")

    try:
        orgs = api_get("/api/organizations")
    except Exception:
        orgs = []

    org_options = {"— None —": None}
    org_options.update({o["name"]: o["id"] for o in orgs})
    current_org_name = user.get("organization_name") or "— None —"

    with st.form("edit_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            firstname = st.text_input("First Name *", value=user.get("firstname", ""))
        with col2:
            lastname = st.text_input("Last Name *", value=user.get("lastname", ""))
        email = st.text_input("Email *", value=user.get("email", ""))

        col3, col4 = st.columns(2)
        with col3:
            languages = st.text_input("Languages", value=", ".join(user.get("languages") or []))
        with col4:
            skills = st.text_input("Skills", value=", ".join(user.get("skills") or []))
        roles_val = st.text_input("Roles", value=", ".join(user.get("roles") or []))

        col5, col6 = st.columns(2)
        with col5:
            org_names = list(org_options.keys())
            org_index = org_names.index(current_org_name) if current_org_name in org_names else 0
            selected_org = st.selectbox("Organization", org_names, index=org_index)
        with col6:
            all_roles = ["admin", "partner_admin", "user"]
            current_role = user.get("app_role", "user")
            role_index = all_roles.index(current_role) if current_role in all_roles else 2
            app_role = st.selectbox("Role", all_roles, index=role_index)

        st.divider()
        st.caption("Set Password (leave blank to keep existing)")
        col7, col8 = st.columns(2)
        with col7:
            new_password = st.text_input("New Password", type="password", placeholder="Min. 8 characters")
        with col8:
            confirm_password = st.text_input("Confirm Password", type="password")

        submitted = st.form_submit_button("Save Changes", type="primary")

    if submitted:
        if not firstname or not lastname or not email:
            st.warning("First name, last name, and email are required.")
        elif new_password and new_password != confirm_password:
            st.warning("Passwords do not match.")
        elif new_password and len(new_password) < 8:
            st.warning("Password must be at least 8 characters.")
        else:
            payload = {
                "firstname": firstname,
                "lastname": lastname,
                "email": email,
                "languages": [x.strip() for x in languages.split(",") if x.strip()],
                "skills": [x.strip() for x in skills.split(",") if x.strip()],
                "roles": [x.strip() for x in roles_val.split(",") if x.strip()],
                "organization_id": org_options[selected_org],
                "app_role": app_role,
            }
            if new_password:
                payload["password"] = new_password
            try:
                api_put(f"/api/users/{user['id']}", payload)
                st.success("User updated.")
                st.session_state.pop("editing_user", None)
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.markdown("### Metabase Group Membership")

    # Show persisted feedback from the previous rerun
    _mb_msg_key = f"mb_msg_{user['id']}"
    if _mb_msg_key in st.session_state:
        msg = st.session_state.pop(_mb_msg_key)
        if msg.get("type") == "success":
            st.success(msg["text"])
        else:
            st.error(msg["text"])

    # Load available groups and current memberships
    mb_groups = []
    mb_status = None
    mb_fetch_error = None
    try:
        mb_groups = api_get("/api/metabase/groups")
    except Exception as e:
        mb_fetch_error = str(e)
    try:
        mb_status = api_get(f"/api/users/{user['id']}/metabase")
    except Exception as e:
        mb_fetch_error = str(e)

    if mb_fetch_error:
        st.warning(f"Could not reach Metabase: {mb_fetch_error}")
    elif mb_status is None:
        st.caption("No Metabase data available.")
    else:
        mb_user_id = mb_status.get("metabase_user_id")
        current_memberships = mb_status.get("group_memberships", [])
        current_group_ids = {m["group_id"] for m in current_memberships}

        # Account status line
        if mb_user_id:
            st.caption(f"Metabase account ID: {mb_user_id}")
        else:
            st.caption("No Metabase account stored yet — one will be created automatically when adding to a group.")

        # Current memberships
        if current_memberships:
            st.caption("Current memberships:")
            for m in current_memberships:
                mcol_name, mcol_btn = st.columns([4, 1])
                with mcol_name:
                    st.write(m["group_name"])
                with mcol_btn:
                    if st.button("Remove", key=f"mb_rem_{user['id']}_{m['group_id']}", use_container_width=True):
                        try:
                            api_delete(f"/api/users/{user['id']}/metabase/{m['group_id']}")
                            st.session_state[_mb_msg_key] = {"type": "success", "text": f"Removed from {m['group_name']}."}
                        except Exception as e:
                            st.session_state[_mb_msg_key] = {"type": "error", "text": str(e)}
                        st.rerun()
        elif mb_user_id:
            st.caption("Not a member of any Metabase permission group.")

        # Add to a group
        available_groups = [g for g in mb_groups if g["id"] not in current_group_ids]
        if available_groups:
            group_options = {g["name"]: g["id"] for g in available_groups}
            selected_name = st.selectbox(
                "Add to group",
                options=list(group_options.keys()),
                key=f"mb_select_{user['id']}",
            )
            if st.button("Add to group", key=f"mb_add_{user['id']}", type="primary"):
                try:
                    result = api_post(
                        f"/api/users/{user['id']}/metabase",
                        {"group_id": group_options[selected_name]},
                    )
                    if result.get("account_created"):
                        st.session_state[_mb_msg_key] = {"type": "success", "text": f"Metabase account created and added to {selected_name}."}
                    else:
                        st.session_state[_mb_msg_key] = {"type": "success", "text": f"Added to {selected_name}."}
                except Exception as e:
                    st.session_state[_mb_msg_key] = {"type": "error", "text": str(e)}
                st.rerun()
        elif mb_groups:
            st.caption("User is already a member of all available groups.")


# ── Partner Admin Panel ────────────────────────────────────────────────────

def show_partner_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ HyOpps")
        user = st.session_state.get("user", {})
        st.caption(f"🏢 {user.get('firstname','')} {user.get('lastname','')}  ·  `partner admin`")
        st.divider()

        pages = {
            "🏠 Dashboard": "partner_dashboard",
            "➕ Add User": "partner_add_user",
            "📋 Workflows": "partner_executions",
        }
        current = st.session_state.get("page", "partner_dashboard")
        for label, key in pages.items():
            if st.button(label, use_container_width=True,
                         type="primary" if current == key else "secondary"):
                st.session_state["page"] = key
                st.session_state.pop("partner_viewing_exec_id", None)
                st.rerun()

        st.divider()
        if st.button("Sign Out", use_container_width=True):
            for k in list(st.session_state.keys()):
                st.session_state.pop(k, None)
            st.rerun()


def show_partner_dashboard():
    try:
        overview = api_get("/api/partner/me")
    except Exception as e:
        st.error(f"Failed to load organization: {e}")
        return

    st.markdown(f"## {overview['name']}")
    st.caption(" · ".join(overview.get("account_types", ["partner"])))
    st.divider()

    users = overview.get("users", [])
    st.markdown(f"### Team Members ({len(users)})")

    if not users:
        st.info("No users onboarded yet. Use 'Add User' to onboard your first team member.")
    else:
        for u in users:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.markdown(f"**{u['firstname']} {u['lastname']}**")
                    st.caption(u["email"])
                with c2:
                    icon = _role_icon(u["app_role"])
                    st.markdown(f"{icon} `{u['app_role']}`")
                with c3:
                    st.caption(f"Joined: {u['created_at'][:10] if u.get('created_at') else '—'}")

    integ = overview.get("integrations")
    if integ:
        st.divider()
        st.markdown("### Integrations")
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            kc = "✅" if integ.get("keycloak_confirmed") else "⏳"
            st.metric("KeyCloak", kc)
        with ic2:
            mb = "✅" if integ.get("metabase_collection_id") else "⏳"
            st.metric("Metabase", mb)
        with ic3:
            lms = "✅" if integ.get("lms_confirmed") else "⏳"
            st.metric("LMS", lms)


def show_partner_add_user():
    st.markdown("## Add New User")
    st.caption("Starts the onboarding workflow for a new team member in your organization.")

    if st.button("Start Onboarding", type="primary"):
        with st.spinner("Preparing workflow…"):
            try:
                ex = api_post("/api/partner/executions")
                time.sleep(0.5)
                st.session_state["partner_viewing_exec_id"] = ex["id"]
                st.session_state["page"] = "partner_execution_detail"
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start workflow: {e}")


def show_partner_executions():
    st.markdown("## Onboarding Workflows")

    if st.button("＋ Add New User", type="primary"):
        st.session_state["page"] = "partner_add_user"
        st.rerun()

    st.divider()

    try:
        executions = api_get("/api/partner/executions")
    except Exception as e:
        st.error(f"Failed to load workflows: {e}")
        return

    if not executions:
        st.info("No onboarding workflows yet.")
        return

    for ex in executions:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1:
                st.markdown("**New Partner User**")
                st.caption(f"`{ex['id'][:8]}…`")
            with c2:
                st.markdown(f"**User:** {ex.get('user_email') or '—'}")
                st.caption(f"Step {ex['current_step_order']}")
            with c3:
                st.markdown(status_badge(ex["status"]), unsafe_allow_html=True)
            with c4:
                if st.button("View", key=f"pview_{ex['id']}", use_container_width=True):
                    st.session_state["partner_viewing_exec_id"] = ex["id"]
                    st.session_state["page"] = "partner_execution_detail"
                    st.rerun()


def show_partner_execution_detail():
    exec_id = st.session_state.get("partner_viewing_exec_id")
    if not exec_id:
        st.session_state["page"] = "partner_executions"
        st.rerun()

    if st.button("← All Workflows"):
        st.session_state.pop("partner_viewing_exec_id", None)
        st.session_state["page"] = "partner_executions"
        st.rerun()

    try:
        ex = api_get(f"/api/partner/executions/{exec_id}")
    except Exception as e:
        st.error(f"Failed to load workflow: {e}")
        return

    _show_execution_view(ex, exec_api_base="/api/partner/executions")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if "token" not in st.session_state:
        show_login()
        return

    user = st.session_state.get("user", {})
    role = user.get("app_role", "user")

    if role == "partner_admin":
        show_partner_sidebar()
        page = st.session_state.get("page", "partner_dashboard")
        if page == "partner_dashboard":
            show_partner_dashboard()
        elif page == "partner_add_user":
            show_partner_add_user()
        elif page == "partner_executions":
            show_partner_executions()
        elif page == "partner_execution_detail":
            show_partner_execution_detail()
        else:
            show_partner_dashboard()
    else:
        show_sidebar()
        page = st.session_state.get("page", "executions")
        if page == "executions":
            show_executions()
        elif page == "new_execution":
            show_new_execution()
        elif page == "execution_detail":
            show_execution_detail()
        elif page == "organizations":
            show_organizations()
        elif page == "org_detail":
            show_org_detail()
        elif page == "users":
            show_users()
        else:
            show_executions()


if __name__ == "__main__":
    main()
else:
    main()
