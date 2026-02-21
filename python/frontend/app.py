"""
HyOpps — Streamlit Admin Panel
Calls the FastAPI backend at API_URL (default: http://localhost:8000)
"""

import os
import time
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


def api_get(path: str) -> list | dict:
    resp = requests.get(f"{API_URL}{path}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str, body: dict = None) -> dict:
    resp = requests.post(f"{API_URL}{path}", json=body or {}, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def poll_until_stable(execution_id: str, max_wait: float = 5.0) -> dict:
    """Poll execution until status is not 'running'."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        ex = api_get(f"/api/executions/{execution_id}")
        if ex["status"] != "running":
            return ex
        time.sleep(0.4)
    return api_get(f"/api/executions/{execution_id}")


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
                st.session_state["page"] = "executions"
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")


# ── Sidebar ────────────────────────────────────────────────────────────────

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
                # Clear any detail state
                st.session_state.pop("viewing_execution_id", None)
                st.session_state.pop("viewing_org_id", None)
                st.rerun()

        st.divider()
        if st.button("Sign Out", use_container_width=True):
            for k in ["token", "user", "page", "viewing_execution_id", "viewing_org_id"]:
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

    # Status filter
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

    wf_labels = {"new_partner": "New Partner Onboarding", "new_partner_user": "New Partner User"}
    wf_label = wf_labels.get(ex["workflow_name"], ex["workflow_name"])

    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"## {wf_label}")
    with col2:
        st.markdown(status_badge(ex["status"]), unsafe_allow_html=True)

    # Meta row
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
        ex = api_get(f"/api/executions/{exec_id}")

    st.divider()
    st.markdown("### Steps")

    for step in ex.get("steps", []):
        _render_step(step, ex)


def _render_step(step: dict, ex: dict):
    status = step["status"]
    num_icon = step_num_color(status)
    is_active = status == "awaiting_input"

    with st.container(border=True):
        # Step header
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

        # Completed auto step output
        if status == "completed" and step.get("output"):
            with st.expander("Output data", expanded=False):
                for k, v in step["output"].items():
                    st.code(f"{k}: {v}", language=None)

        # Completed manual step — show what was entered
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

        # Failed step
        if status == "failed":
            st.error(f"Error: {step.get('error', 'Unknown error')}")
            if st.button("Retry", key=f"retry_{step['id']}", type="secondary"):
                with st.spinner("Retrying…"):
                    try:
                        api_post(f"/api/executions/{ex['id']}/steps/{step['id']}/retry")
                        time.sleep(1.5)
                    except Exception as e:
                        st.error(str(e))
                st.rerun()

        # Awaiting input — show the appropriate form
        if status == "awaiting_input":
            st.divider()
            _render_manual_form(step, ex)


def _render_manual_form(step: dict, ex: dict):
    step_name = step["step_name"]
    step_id = step["id"]
    exec_id = ex["id"]

    def _submit(data: dict):
        with st.spinner("Processing…"):
            try:
                api_post(f"/api/executions/{exec_id}/steps/{step_id}/input", data)
                time.sleep(0.5)
                stable = poll_until_stable(exec_id)
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
        org_id = ex.get("organization_id")
        studio_companies = []
        if org_id:
            try:
                org_detail = api_get(f"/api/organizations/{org_id}")
                studio_companies = org_detail.get("studio_companies", [])
            except Exception:
                pass

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

            selected_companies: list[str] = []
            if studio_companies:
                st.markdown("**Studio Company Access**")
                checked = {}
                for sc in studio_companies:
                    env_icon = "🟢" if sc["environment"] == "prod" else "🔵"
                    checked[sc["id"]] = st.checkbox(
                        f"{env_icon} {sc['name']} ({sc['environment'].upper()})",
                        value=True,
                        key=f"sc_{sc['id']}"
                    )
                selected_companies = [sc_id for sc_id, val in checked.items() if val]

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
                    "selected_studio_company_ids": selected_companies,
                })
    else:
        # Generic manual confirmation
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
            c1, c2, c3 = st.columns([3, 2, 1])
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

    with col1:
        st.markdown("### System Groups")
        groups = org.get("system_groups", [])
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


# ── Users ──────────────────────────────────────────────────────────────────

def show_users():
    st.markdown("## Users")

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
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1:
                st.markdown(f"**{user['firstname']} {user['lastname']}**")
                st.caption(user["email"])
            with c2:
                role_icon = "🔑" if user["app_role"] == "admin" else "👤"
                st.markdown(f"{role_icon} `{user['app_role']}`")
            with c3:
                st.caption(f"Org: {user.get('organization_name') or '—'}")
            with c4:
                st.caption(user["created_at"][:10] if user.get("created_at") else "")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if "token" not in st.session_state:
        show_login()
        return

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
