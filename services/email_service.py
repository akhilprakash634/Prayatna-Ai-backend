import json
import logging
import os
import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("prayatna_email")


def is_smtp_configured() -> bool:
    """Check if SMTP host is configured in environment."""
    return bool(os.getenv("SMTP_HOST", "").strip())


def get_smtp_config() -> Dict[str, Any]:
    """Retrieve default SMTP configuration from environment with sensible defaults."""
    port_str = os.getenv("SMTP_PORT", "587").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    tls_env = os.getenv("SMTP_TLS", "true").strip().lower()
    use_tls = tls_env in ("true", "1", "yes")

    ssl_env = os.getenv("SMTP_SSL", "false").strip().lower()
    use_ssl = ssl_env in ("true", "1", "yes") or port == 465

    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": port,
        "user": os.getenv("SMTP_USER", "").strip() or None,
        "password": os.getenv("SMTP_PASSWORD", "").strip() or None,
        "from_email": os.getenv("SMTP_FROM_EMAIL", "notifications@thescalecraft.in").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "AssistStudio Lead Alert").strip(),
        "use_tls": use_tls,
        "use_ssl": use_ssl,
    }


def resolve_org_smtp_config(
    email_cfg_data: Optional[Any] = None,
    ignore_disabled: bool = False,
) -> Dict[str, Any]:
    """
    Resolve SMTP configuration for an organization.
    If org has custom SMTP configured (or provider in custom, gmail, office365, zoho),
    uses that configuration.
    If ignore_disabled=False, only applies if enabled is True.
    Otherwise, returns platform environment defaults.
    """
    base = get_smtp_config()
    if not email_cfg_data:
        return base

    cfg: Dict[str, Any] = {}
    if isinstance(email_cfg_data, str):
        try:
            cfg = json.loads(email_cfg_data)
        except Exception:
            cfg = {}
    elif isinstance(email_cfg_data, dict):
        cfg = email_cfg_data

    provider = cfg.get("provider", "system_default")
    is_custom = provider in ("smtp_custom", "gmail", "office365", "zoho")
    is_enabled = cfg.get("enabled", True) if not ignore_disabled else True
    host = (cfg.get("smtp_host") or "").strip()

    if (is_custom or host) and is_enabled and host:
        port = cfg.get("smtp_port") or (465 if cfg.get("smtp_encryption") == "ssl" else 587)
        try:
            port = int(port)
        except ValueError:
            port = 587

        enc = (cfg.get("smtp_encryption") or "tls").strip().lower()
        use_ssl = enc == "ssl" or port == 465
        use_tls = enc == "tls" and not use_ssl

        user = (cfg.get("smtp_user") or "").strip() or None
        from_email = (cfg.get("from_email") or "").strip()
        # For authenticated SMTP (Zoho, Gmail, etc.), the envelope sender address
        # MUST match the authenticated user domain to prevent 550 Relay Access Denied errors.
        if user and "@" in user:
            u_domain = user.split("@")[-1].lower()
            f_domain = from_email.split("@")[-1].lower() if (from_email and "@" in from_email) else ""
            if not from_email or u_domain != f_domain:
                from_email = user
        elif not from_email:
            from_email = base["from_email"]
        from_name = (cfg.get("from_name") or base["from_name"]).strip()

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": (cfg.get("smtp_password") or "").strip() or None,
            "from_email": from_email,
            "from_name": from_name,
            "use_tls": use_tls,
            "use_ssl": use_ssl,
        }

    # If provider is system_default or no custom host, allow custom from_name / from_email if set
    if cfg.get("from_name"):
        base["from_name"] = str(cfg["from_name"]).strip()
    if cfg.get("from_email"):
        base["from_email"] = str(cfg["from_email"]).strip()

    return base


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[str] = None,
    smtp_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send an email via SMTP.
    If SMTP is not configured, logs the email safely and returns True (simulated delivery).
    """
    to_email = to_email.strip().lower()
    if not to_email or "@" not in to_email:
        logger.warning(f"Invalid recipient email: {to_email}")
        return False

    cfg = smtp_config or get_smtp_config()

    if not cfg.get("host"):
        logger.info(
            f"[Email Simulated - No SMTP configured] To: {to_email} | Subject: '{subject}' | Reply-To: {reply_to}"
        )
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    sender_name = from_name or cfg.get("from_name") or "Notification"
    user_addr = (cfg.get("user") or "").strip()
    configured_from = (cfg.get("from_email") or "").strip()

    # For envelope sender, modern mail servers (Zoho, Gmail, etc.) enforce that
    # the sender address matches the authenticated user or an approved alias.
    if user_addr and "@" in user_addr:
        user_domain = user_addr.split("@")[-1].lower()
        from_domain = configured_from.split("@")[-1].lower() if ("@" in configured_from) else ""
        if not configured_from or user_domain != from_domain:
            sender_email = user_addr
        else:
            sender_email = configured_from
    elif configured_from:
        sender_email = configured_from
    else:
        sender_email = "noreply@thescalecraft.in"

    msg["From"] = formataddr((sender_name, sender_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else None)

    if reply_to and "@" in reply_to:
        msg["Reply-To"] = reply_to
    if cc and "@" in cc:
        msg["Cc"] = cc

    plain_body = text_content or html_content.replace("<br>", "\n").replace("</p>", "\n\n")
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    recipients = [to_email]
    if cc and "@" in cc:
        recipients.append(cc.strip().lower())

    try:
        if cfg.get("use_ssl"):
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=12) as server:
                if cfg.get("user") and cfg.get("password"):
                    server.login(cfg["user"], cfg["password"])
                server.sendmail(sender_email, recipients, msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=12) as server:
                server.ehlo()
                if cfg.get("use_tls"):
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if cfg.get("user") and cfg.get("password"):
                    server.login(cfg["user"], cfg["password"])
                server.sendmail(sender_email, recipients, msg.as_string())

        logger.info(f"Email sent successfully to {to_email} via {cfg.get('host')} (Subject: '{subject}')")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email} via {cfg.get('host')}: {e}", exc_info=True)
        return False


def test_smtp_connection(cfg: Dict[str, Any], to_email: str) -> Tuple[bool, str, Optional[str]]:
    """
    Test SMTP server connectivity and dispatch a test email with specific diagnostics.
    Returns (success, user_message, diagnostic_detail).
    """
    host = (cfg.get("host") or "").strip()
    if not host:
        return False, "SMTP Host is required to test email connection.", "Missing SMTP host"

    to_email = to_email.strip().lower()
    if not to_email or "@" not in to_email:
        return False, "A valid test recipient email address is required.", "Invalid test recipient email"

    port = cfg.get("port") or 587
    try:
        port = int(port)
    except ValueError:
        port = 587

    user = cfg.get("user")
    password = cfg.get("password")
    use_ssl = cfg.get("use_ssl", False)
    use_tls = cfg.get("use_tls", False)

    subject = f"✅ Test Email: SMTP Connected Successfully ({cfg.get('from_name') or 'Mail Service'})"
    sec_str = "SSL (Port 465)" if use_ssl else ("TLS (Port 587)" if use_tls else "Plain")
    sender_name = cfg.get("from_name") or "Mail Service"

    user_addr = (user or "").strip()
    configured_from = (cfg.get("from_email") or "").strip()

    # For envelope sender, modern mail servers (Zoho, Gmail, etc.) enforce that
    # the sender address matches the authenticated user or an approved alias.
    if user_addr and "@" in user_addr:
        user_domain = user_addr.split("@")[-1].lower()
        from_domain = configured_from.split("@")[-1].lower() if ("@" in configured_from) else ""
        if not configured_from or user_domain != from_domain:
            sender_email = user_addr
        else:
            sender_email = configured_from
    elif configured_from:
        sender_email = configured_from
    else:
        sender_email = "noreply@thescalecraft.in"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; padding: 24px; margin: 0;">
      <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 14px; border: 1px solid #e2e8f0; padding: 28px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <div style="text-align: center; margin-bottom: 16px;">
          <span style="background-color: #ecfdf5; color: #047857; font-size: 13px; font-weight: 700; padding: 6px 14px; border-radius: 9999px;">
            ✓ SMTP Connection Confirmed
          </span>
        </div>
        <h2 style="color: #0f172a; font-size: 20px; font-weight: 700; text-align: center; margin: 0 0 12px;">
          Your Mail Service is Working!
        </h2>
        <p style="color: #475569; font-size: 14px; line-height: 1.6; text-align: center; margin: 0 0 20px;">
          This test confirms that your business mail server is properly connected. When visitors submit new enquiries or callback requests on your website, real-time alerts will arrive directly in your inbox.
        </p>
        <div style="background-color: #f1f5f9; border-radius: 10px; padding: 14px 18px; font-size: 13px; color: #334155; margin-bottom: 20px;">
          <div style="margin-bottom: 6px;"><strong>SMTP Server:</strong> {host}:{port}</div>
          <div style="margin-bottom: 6px;"><strong>Security:</strong> {sec_str}</div>
          <div style="margin-bottom: 6px;"><strong>Authenticated User:</strong> {user or 'None'}</div>
          <div><strong>Sender:</strong> {sender_name} &lt;{sender_email}&gt;</div>
        </div>
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 0;">
          Sent by AssistStudio Email Configuration Test.
        </p>
      </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, sender_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else None)
    reply_target = configured_from if (configured_from and "@" in configured_from) else (cfg.get("company_email") or "")
    if reply_target and reply_target.lower() != sender_email.lower():
        msg["Reply-To"] = reply_target
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=12) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(sender_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if user and password:
                    server.login(user, password)
                server.sendmail(sender_email, [to_email], msg.as_string())

        logger.info(f"Test email sent successfully to {to_email} via {host}:{port}")
        return True, f"Test email sent successfully to {to_email}. Please check your inbox (and spam/promotions folder).", None

    except smtplib.SMTPAuthenticationError as auth_err:
        raw_msg = str(auth_err)
        return (
            False,
            f"Authentication failed with {host}. Please verify your username and password. Note: If 2-Factor Authentication is enabled on your email account (Zoho, Google, Microsoft), you must generate and use an App Password.",
            f"SMTPAuthenticationError: {raw_msg}",
        )
    except smtplib.SMTPServerDisconnected as disc_err:
        return (
            False,
            f"Server disconnected unexpectedly on {host}:{port}. Check if Port 465 (with SSL) or Port 587 (with STARTTLS) is required.",
            f"SMTPServerDisconnected: {str(disc_err)}",
        )
    except (socket.timeout, TimeoutError):
        return (
            False,
            f"Connection timed out trying to reach {host}:{port}. Check that the host name and port are correct (e.g. Zoho standard is port 465 for SSL or 587 for TLS, not {port}).",
            f"Timeout connecting to {host}:{port}",
        )
    except ssl.SSLError as ssl_err:
        return (
            False,
            f"SSL/TLS handshake failed on {host}:{port}. Check if your port matches the encryption mode (Port 465 for SSL, Port 587 for TLS).",
            f"SSLError: {str(ssl_err)}",
        )
    except Exception as e:
        err_str = str(e)
        logger.error(f"Test email failed for {host}:{port}: {e}", exc_info=True)
        if "5.7.1" in err_str or "relay" in err_str.lower():
            hint = f"Sender is not allowed to relay (550 5.7.1). The outgoing mail server ({host}) rejected the sender address. The Sender Email (From Email) must match your authenticated username ({user}) or a verified alias in your Zoho/email account."
            return False, hint, f"SMTP relay rejected: {err_str}"
        return (
            False,
            f"Failed to deliver email through {host}:{port}: {str(e)}",
            f"SMTP error: {str(e)}",
        )


def send_lead_alert_email(
    admin_email: str,
    org_name: str,
    enquiry_data: Dict[str, Any],
    bot_name: Optional[str] = None,
    smtp_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send an email notification to the organization administrator when an actionable lead
    (callback request or service enquiry) is captured.
    """
    visitor_name = enquiry_data.get("parent_name") or "Website Visitor"
    service_name = enquiry_data.get("interested_service") or "Service Request"
    phone = enquiry_data.get("phone") or "Not provided"
    email = enquiry_data.get("email") or "Not provided"
    pref_contact = enquiry_data.get("preferred_contact") or "phone"
    description = enquiry_data.get("description") or "None"
    category = enquiry_data.get("category") or "General"
    app_url = os.getenv("PUBLIC_APP_URL", "https://assiststudio.thescalecraft.in").rstrip("/")

    subject = f"🔔 New Lead ({service_name}): {visitor_name} - {org_name}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px; }}
        .card {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
        .header {{ background: #4f46e5; padding: 24px 28px; color: #ffffff; }}
        .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
        .header p {{ margin: 4px 0 0; font-size: 13px; opacity: 0.9; }}
        .content {{ padding: 28px; }}
        .badge {{ display: inline-block; padding: 4px 10px; font-size: 11px; font-weight: 700; text-transform: uppercase; background: #e0e7ff; color: #4338ca; border-radius: 9999px; margin-bottom: 16px; }}
        .field {{ margin-bottom: 14px; }}
        .field-label {{ font-size: 11px; font-weight: 600; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; margin-bottom: 3px; }}
        .field-value {{ font-size: 15px; font-weight: 600; color: #0f172a; }}
        .field-value a {{ color: #4f46e5; text-decoration: none; }}
        .notes-box {{ background: #f1f5f9; border-radius: 10px; padding: 12px 14px; font-size: 13px; color: #334155; margin-top: 6px; white-space: pre-wrap; }}
        .btn {{ display: inline-block; padding: 12px 24px; background: #4f46e5; color: #ffffff !important; text-decoration: none; font-size: 13px; font-weight: 600; border-radius: 10px; margin-top: 20px; text-align: center; }}
        .footer {{ border-top: 1px solid #f1f5f9; padding: 16px 28px; font-size: 11px; color: #94a3b8; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h1>New Lead Captured</h1>
          <p>{org_name} &bull; {bot_name or 'Chat Assistant'}</p>
        </div>
        <div class="content">
          <div class="badge">Actionable Enquiry</div>

          <div class="field">
            <div class="field-label">Visitor / Customer Name</div>
            <div class="field-value">{visitor_name}</div>
          </div>

          <div class="field">
            <div class="field-label">Phone Number</div>
            <div class="field-value"><a href="tel:{phone}">{phone}</a></div>
          </div>

          <div class="field">
            <div class="field-label">Email Address</div>
            <div class="field-value">{f'<a href="mailto:{email}">{email}</a>' if email != 'Not provided' else 'Not provided'}</div>
          </div>

          <div class="field">
            <div class="field-label">Interested Service / Topic</div>
            <div class="field-value">{service_name} ({category})</div>
          </div>

          <div class="field">
            <div class="field-label">Preferred Contact Method</div>
            <div class="field-value" style="text-transform: capitalize;">{pref_contact}</div>
          </div>

          <div class="field">
            <div class="field-label">Enquiry Notes / Message</div>
            <div class="notes-box">{description}</div>
          </div>

          <div style="text-align: center;">
            <a href="{app_url}/admin/enquiries" class="btn">View in Admin Dashboard &rarr;</a>
          </div>
        </div>
        <div class="footer">
          Captured via {bot_name or 'AssistStudio'} for {org_name}.
        </div>
      </div>
    </body>
    </html>
    """

    text = f"""New Lead Captured for {org_name}

Visitor: {visitor_name}
Phone: {phone}
Email: {email}
Service: {service_name} ({category})
Preferred Contact: {pref_contact}

Notes:
{description}

View in dashboard: {app_url}/admin/enquiries
"""
    from_name = (smtp_config.get("from_name") if smtp_config and smtp_config.get("from_name") else None) or org_name
    reply_to = email if (email and "@" in email and email != "Not provided") else None
    return send_email(
        to_email=admin_email,
        subject=subject,
        html_content=html,
        text_content=text,
        from_name=from_name,
        reply_to=reply_to,
        smtp_config=smtp_config,
    )


def send_enquiry_reply_email(
    to_email: str,
    visitor_name: str,
    org_name: str,
    subject: str,
    body_text: str,
    admin_reply_to: Optional[str] = None,
    smtp_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send an email reply directly to a visitor from the business admin panel.
    """
    formatted_body = body_text.replace("\n", "<br>")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; }}
        .header {{ background: #0f172a; padding: 20px 24px; color: #ffffff; }}
        .header h1 {{ margin: 0; font-size: 18px; font-weight: 700; }}
        .content {{ padding: 24px; font-size: 14px; color: #334155; }}
        .content p {{ margin-top: 0; }}
        .footer {{ border-top: 1px solid #f1f5f9; padding: 14px 24px; font-size: 11px; color: #94a3b8; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h1>{org_name}</h1>
        </div>
        <div class="content">
          <p>Dear {visitor_name},</p>
          <div>{formatted_body}</div>
          <br>
          <p>Best regards,<br><strong>{org_name} Team</strong></p>
        </div>
        <div class="footer">
          This message was sent by {org_name}.
        </div>
      </div>
    </body>
    </html>
    """

    return send_email(
        to_email=to_email,
        subject=subject,
        html_content=html,
        text_content=f"Dear {visitor_name},\n\n{body_text}\n\nBest regards,\n{org_name} Team",
        from_name=org_name,
        reply_to=admin_reply_to,
        smtp_config=smtp_config,
    )


def dispatch_lead_alert(
    db: Any,
    organization_id: str,
    enquiry_data: Dict[str, Any],
    source_label: str = "chat",
) -> None:
    """
    Unified lead alert dispatcher.
    Resolves company notification recipients, organization SMTP config, and safely
    dispatches alert emails via a background daemon thread.
    """
    try:
        from threading import Thread
        from models import ChatbotSetting, Organization, User
        from services.tenant import resolve_chatbot_theme_config

        org = db.query(Organization).filter(Organization.id == organization_id).first()
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == organization_id).first()
        admin_user = (
            db.query(User)
            .filter(User.organization_id == organization_id, User.role == "client_admin")
            .first()
        )
        theme_cfg = resolve_chatbot_theme_config(org, setting) if org and setting else {}

        org_email_cfg: dict = {}
        if org and org.email_config_json:
            try:
                org_email_cfg = json.loads(org.email_config_json)
            except Exception:
                org_email_cfg = {}

        resolved_smtp = resolve_org_smtp_config(org_email_cfg)

        recipients = []
        if org_email_cfg.get("company_email"):
            comp_e = org_email_cfg["company_email"].strip().lower()
            if comp_e and "@" in comp_e:
                recipients.append(comp_e)

        # Include authenticated SMTP user (e.g. sales@growyourbusiness.today) so the sales mailbox
        # also receives a direct copy of all captured website enquiries
        smtp_u = (org_email_cfg.get("smtp_user") or "").strip().lower()
        if smtp_u and "@" in smtp_u and smtp_u not in recipients:
            recipients.append(smtp_u)

        if org_email_cfg.get("additional_emails"):
            for em in org_email_cfg["additional_emails"]:
                if em and "@" in em and em.strip().lower() not in recipients:
                    recipients.append(em.strip().lower())

        if not recipients and theme_cfg.get("notification_email"):
            recipients.append(theme_cfg["notification_email"].strip().lower())
        if not recipients and admin_user and admin_user.email:
            recipients.append(admin_user.email.strip().lower())

        is_enabled = org_email_cfg.get("enabled", True)
        # If the organization has custom SMTP credentials configured, guarantee that lead alerts are active
        if org_email_cfg.get("smtp_host") and org_email_cfg.get("smtp_user"):
            is_enabled = True

        if recipients and is_enabled:
            logger.info(
                "Dispatching lead alert for enquiry '%s' from %s to %d recipient(s): %s",
                enquiry_data.get("id"),
                source_label,
                len(recipients),
                recipients,
            )
            for rcpt in recipients:
                Thread(
                    target=send_lead_alert_email,
                    kwargs={
                        "admin_email": rcpt,
                        "org_name": org.name if org else "Your Organization",
                        "enquiry_data": enquiry_data,
                        "bot_name": setting.bot_name if setting else None,
                        "smtp_config": resolved_smtp,
                    },
                    daemon=True,
                ).start()
        else:
            logger.warning(
                "Lead alert not dispatched: recipients=%s, is_enabled=%s",
                recipients,
                is_enabled,
            )
    except Exception as e:
        logger.error("Failed to dispatch lead alert email from %s: %s", source_label, e, exc_info=True)
