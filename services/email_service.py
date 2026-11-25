import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Any, Dict, Optional

logger = logging.getLogger("prayatna_email")


def is_smtp_configured() -> bool:
    """Check if SMTP host is configured in environment."""
    return bool(os.getenv("SMTP_HOST", "").strip())


def get_smtp_config() -> Dict[str, Any]:
    """Retrieve SMTP configuration from environment with sensible defaults."""
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


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[str] = None,
) -> bool:
    """
    Send an email via SMTP.
    If SMTP is not configured, logs the email safely and returns True (simulated delivery).
    """
    to_email = to_email.strip().lower()
    if not to_email or "@" not in to_email:
        logger.warning(f"Invalid recipient email: {to_email}")
        return False

    cfg = get_smtp_config()

    if not cfg["host"]:
        logger.info(
            f"[Email Simulated - No SMTP configured] To: {to_email} | Subject: '{subject}' | Reply-To: {reply_to}"
        )
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    sender_name = from_name or cfg["from_name"]
    msg["From"] = formataddr((sender_name, cfg["from_email"]))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=cfg["from_email"].split("@")[-1] if "@" in cfg["from_email"] else None)

    if reply_to:
        msg["Reply-To"] = reply_to
    if cc:
        msg["Cc"] = cc

    plain_body = text_content or html_content.replace("<br>", "\n").replace("</p>", "\n\n")
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    recipients = [to_email]
    if cc:
        recipients.append(cc.strip().lower())

    try:
        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=12) as server:
                if cfg["user"] and cfg["password"]:
                    server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], recipients, msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=12) as server:
                server.ehlo()
                if cfg["use_tls"]:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if cfg["user"] and cfg["password"]:
                    server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], recipients, msg.as_string())

        logger.info(f"Email sent successfully to {to_email} (Subject: '{subject}')")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
        return False


def send_lead_alert_email(
    admin_email: str,
    org_name: str,
    enquiry_data: Dict[str, Any],
    bot_name: Optional[str] = None,
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
            <div class="field-label">Visitor / Parent Name</div>
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
    return send_email(to_email=admin_email, subject=subject, html_content=html, text_content=text, from_name=org_name)


def send_enquiry_reply_email(
    to_email: str,
    visitor_name: str,
    org_name: str,
    subject: str,
    body_text: str,
    admin_reply_to: Optional[str] = None,
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
    )
