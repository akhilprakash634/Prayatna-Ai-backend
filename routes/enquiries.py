import csv
import io
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models import ChatbotSetting, Conversation, Enquiry, Organization, User
from schemas import (
    EnquiryCreate,
    EnquiryResponse,
    EnquirySendEmailRequest,
    EnquirySendEmailResponse,
    EnquiryUpdate,
)
from services.email_service import send_enquiry_reply_email, send_lead_alert_email
from services.security import (
    AuthContext,
    assert_org_access,
    get_client_ip,
    public_chat_rate_limiter,
    require_client_admin,
)
from services.tenant import resolve_chatbot_theme_config, resolve_public_chatbot

router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])


def _sanitize_csv_cell(val: Any) -> str:
    """Sanitize cell value to prevent formula injection in Excel/CSV viewers."""
    if val is None:
        return ""
    s = str(val).strip()
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@router.post("", response_model=EnquiryResponse, status_code=status.HTTP_201_CREATED)
def create_enquiry(
    payload: EnquiryCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create an enquiry from the public chat widget/page scoped strictly to the target chatbot's organization.
    """
    public_chat_rate_limiter.check(f"enq:{get_client_ip(request)}:{payload.chatbot_id or 'default'}")
    org, _ = resolve_public_chatbot(db, payload.chatbot_id)

    if payload.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()
        if conv:
            assert_org_access(conv.organization_id, org.id, "Conversation")
            conv.status = "lead_captured"
            if payload.category:
                conv.category = payload.category

    new_enquiry = Enquiry(
        organization_id=org.id,
        conversation_id=payload.conversation_id,
        parent_name=payload.parent_name.strip(),
        email=payload.email.strip().lower(),
        phone=payload.phone.strip(),
        child_age=payload.child_age.strip() if payload.child_age else None,
        interested_service=payload.interested_service.strip(),
        category=payload.category,
        description=payload.description.strip(),
        preferred_contact=payload.preferred_contact,
        status="New",
    )

    db.add(new_enquiry)
    db.commit()
    db.refresh(new_enquiry)

    # Dispatch lead notification email if enabled and actionable
    try:
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
        theme_cfg = resolve_chatbot_theme_config(org, setting)
        if theme_cfg.get("lead_notifications_enabled", True):
            admin_user = (
                db.query(User)
                .filter(User.organization_id == org.id, User.role == "client_admin")
                .first()
            )
            recipient_email = theme_cfg.get("notification_email") or (admin_user.email if admin_user else None)
            if recipient_email:
                background_tasks.add_task(
                    send_lead_alert_email,
                    admin_email=recipient_email,
                    org_name=org.name,
                    enquiry_data={
                        "parent_name": new_enquiry.parent_name,
                        "phone": new_enquiry.phone,
                        "email": new_enquiry.email,
                        "interested_service": new_enquiry.interested_service,
                        "category": new_enquiry.category,
                        "description": new_enquiry.description,
                        "preferred_contact": new_enquiry.preferred_contact,
                    },
                    bot_name=setting.bot_name if setting else None,
                )
    except Exception:
        pass

    return new_enquiry


@router.get("/export")
def export_enquiries(
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """
    Export visitor enquiries to an RFC-4180 CSV file matching current active filters.
    """
    query = db.query(Enquiry).filter(Enquiry.organization_id == ctx.organization_id)
    if category:
        query = query.filter(Enquiry.category == category)
    if status_filter:
        query = query.filter(Enquiry.status == status_filter)

    enquiries = query.order_by(Enquiry.created_at.desc()).all()

    if search:
        s_lower = search.lower()
        enquiries = [
            e
            for e in enquiries
            if s_lower in e.parent_name.lower()
            or s_lower in e.phone.lower()
            or s_lower in e.email.lower()
            or s_lower in e.interested_service.lower()
            or s_lower in e.description.lower()
        ]

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # CSV Headers
    writer.writerow([
        "Enquiry ID",
        "Captured At (UTC)",
        "Visitor Name",
        "Phone Number",
        "Email Address",
        "Preferred Contact",
        "Category",
        "Interested Service / Topic",
        "Notes / Message",
        "Status",
        "Conversation ID",
    ])

    for e in enquiries:
        created_str = e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else ""
        writer.writerow([
            _sanitize_csv_cell(e.id),
            _sanitize_csv_cell(created_str),
            _sanitize_csv_cell(e.parent_name),
            _sanitize_csv_cell(e.phone),
            _sanitize_csv_cell(e.email),
            _sanitize_csv_cell(e.preferred_contact),
            _sanitize_csv_cell(e.category),
            _sanitize_csv_cell(e.interested_service),
            _sanitize_csv_cell(e.description),
            _sanitize_csv_cell(e.status),
            _sanitize_csv_cell(e.conversation_id or ""),
        ])

    csv_content = output.getvalue()
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"enquiries_export_{today_str}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("", response_model=List[EnquiryResponse])
def list_enquiries(
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Enquiry).filter(Enquiry.organization_id == ctx.organization_id)
    if category:
        query = query.filter(Enquiry.category == category)
    if status_filter:
        query = query.filter(Enquiry.status == status_filter)

    enquiries = query.order_by(Enquiry.created_at.desc()).all()

    if search:
        s_lower = search.lower()
        enquiries = [
            e
            for e in enquiries
            if s_lower in e.parent_name.lower()
            or s_lower in e.phone.lower()
            or s_lower in e.email.lower()
            or s_lower in e.interested_service.lower()
            or s_lower in e.description.lower()
        ]

    return enquiries


@router.get("/{enquiry_id}", response_model=EnquiryResponse)
def get_enquiry(
    enquiry_id: str,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found")

    assert_org_access(enquiry.organization_id, ctx.organization_id, "Enquiry")
    return enquiry


@router.post("/{enquiry_id}/send-email", response_model=EnquirySendEmailResponse)
def send_enquiry_email(
    enquiry_id: str,
    payload: EnquirySendEmailRequest,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """
    Send an email reply directly to the visitor from the client admin dashboard.
    Automatically marks enquiry as Contacted and logs the interaction.
    """
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found")

    assert_org_access(enquiry.organization_id, ctx.organization_id, "Enquiry")

    if not enquiry.email or enquiry.email == "Not provided" or "@" not in enquiry.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This enquiry does not have a valid email address to send to.",
        )

    org = db.query(Organization).filter(Organization.id == ctx.organization_id).first()
    org_name = org.name if org else "Support Team"

    sent_ok = send_enquiry_reply_email(
        to_email=enquiry.email,
        visitor_name=enquiry.parent_name,
        org_name=org_name,
        subject=payload.subject.strip(),
        body_text=payload.body.strip(),
        admin_reply_to=ctx.user.email,
    )

    if not sent_ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch email. Please check server SMTP configuration.",
        )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    enquiry.status = "Contacted"
    enquiry.description = f"{enquiry.description}\n[Email sent on {now_str} by {ctx.user.email}]: '{payload.subject}'"
    db.commit()
    db.refresh(enquiry)

    return EnquirySendEmailResponse(
        success=True,
        message="Email sent successfully to visitor.",
        sent_to=enquiry.email,
        status=enquiry.status,
    )


@router.patch("/{enquiry_id}", response_model=EnquiryResponse)
def update_enquiry(
    enquiry_id: str,
    payload: EnquiryUpdate,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found")

    assert_org_access(enquiry.organization_id, ctx.organization_id, "Enquiry")

    if payload.status is not None:
        enquiry.status = payload.status
    if payload.category is not None:
        enquiry.category = payload.category
    if payload.description is not None:
        enquiry.description = payload.description.strip()

    db.commit()
    db.refresh(enquiry)
    return enquiry

