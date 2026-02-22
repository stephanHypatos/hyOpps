"""
Email integration — sends onboarding documentation links to newly provisioned users.

Uses Python stdlib smtplib (no extra dependencies).

Credentials (python/.env):
    SMTP_HOST=smtp.example.com
    SMTP_PORT=587           # defaults to 587 (STARTTLS)
    SMTP_USER=sender@example.com
    SMTP_PASSWORD=your_password
    EMAIL_FROM=HyOpps <noreply@example.com>   # optional, defaults to SMTP_USER
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _smtp_config() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("EMAIL_FROM", os.environ.get("SMTP_USER", "")),
    }


def _check_smtp_config() -> None:
    cfg = _smtp_config()
    if not cfg["host"]:
        raise RuntimeError("SMTP_HOST is not configured")
    if not cfg["user"]:
        raise RuntimeError("SMTP_USER is not configured")
    if not cfg["password"]:
        raise RuntimeError("SMTP_PASSWORD is not configured")


def send_documentation_email(
    to_email: str,
    firstname: str,
    org_name: str,
    docs: dict,
) -> dict:
    """
    Send an HTML email with the org's documentation links to the newly onboarded user.

    docs keys: internal_docu, generique_docu, add_docu (all optional str | None)

    Returns {"sent": True, "links_sent": int} on success, raises on failure.
    """
    _check_smtp_config()
    cfg = _smtp_config()

    doc_items = [
        ("Internal Documentation", docs.get("internal_docu")),
        ("General Documentation", docs.get("generique_docu")),
        ("Additional Documentation", docs.get("add_docu")),
    ]
    links = [(label, url) for label, url in doc_items if url]

    # ── HTML body ──────────────────────────────────────────────────────────────
    if links:
        link_html = "".join(
            f'<tr><td style="padding:8px 0;border-bottom:1px solid #e2e8f0">'
            f'<span style="color:#64748b;font-size:13px">{label}</span><br>'
            f'<a href="{url}" style="color:#6366f1;font-weight:600">{url}</a>'
            f'</td></tr>'
            for label, url in links
        )
        links_section = f'<table style="width:100%;border-collapse:collapse">{link_html}</table>'
    else:
        links_section = '<p style="color:#94a3b8">No documentation links have been configured yet.</p>'

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;color:#1e293b;max-width:580px;margin:auto;padding:32px 24px">
  <h2 style="color:#6366f1;margin-bottom:4px">Welcome, {firstname}!</h2>
  <p style="color:#64748b;margin-top:0">You have been onboarded to <strong style="color:#1e293b">{org_name}</strong>.</p>
  <p>Here are your documentation resources:</p>
  {links_section}
  <br>
  <p style="color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;padding-top:16px">
    This message was sent automatically during your onboarding. Please do not reply.
  </p>
</body>
</html>"""

    # ── Plain-text fallback ────────────────────────────────────────────────────
    plain_links = "\n".join(f"  {label}: {url}" for label, url in links) or "  (none configured)"
    plain = (
        f"Welcome, {firstname}!\n\n"
        f"You have been onboarded to {org_name}.\n\n"
        f"Documentation resources:\n{plain_links}\n\n"
        f"This message was sent automatically during your onboarding."
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Welcome to {org_name} — Your Documentation Links"
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["from_addr"], [to_email], msg.as_string())

    return {"sent": True, "links_sent": len(links)}
