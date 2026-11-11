from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Conversation, Enquiry, KnowledgeDocument, Message
from schemas import ActivityItem, DashboardStats
from services.security import AuthContext, require_client_admin

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    org_id = ctx.organization_id
    total_convs = db.query(Conversation).filter(Conversation.organization_id == org_id).count()
    total_enqs = db.query(Enquiry).filter(Enquiry.organization_id == org_id).count()
    app_enqs = (
        db.query(Enquiry)
        .filter(Enquiry.organization_id == org_id, Enquiry.category == "appointment")
        .count()
    )
    payment_requests = (
        db.query(Enquiry)
        .filter(Enquiry.organization_id == org_id, Enquiry.category == "payment_support")
        .count()
    )
    unresolved_convs = (
        db.query(Conversation)
        .filter(Conversation.organization_id == org_id, Conversation.status == "active")
        .count()
    )

    return DashboardStats(
        total_conversations=total_convs,
        total_enquiries=total_enqs,
        appointment_enquiries=app_enqs,
        payment_support_requests=payment_requests,
        unresolved_conversations=unresolved_convs,
    )


@router.get("/recent-activity", response_model=List[ActivityItem])
def get_recent_activity(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    org_id = ctx.organization_id
    activities: List[ActivityItem] = []

    enquiries = (
        db.query(Enquiry)
        .filter(Enquiry.organization_id == org_id)
        .order_by(Enquiry.created_at.desc())
        .limit(5)
        .all()
    )
    for e in enquiries:
        activities.append(
            ActivityItem(
                id=e.id,
                type="enquiry",
                title=f"Enquiry: {e.parent_name} ({e.interested_service})",
                subtitle=f"{e.category.title()} enquiry via {e.preferred_contact} • Phone: {e.phone}",
                timestamp=e.created_at,
                status=e.status,
            )
        )

    convs = (
        db.query(Conversation)
        .filter(Conversation.organization_id == org_id)
        .order_by(Conversation.updated_at.desc())
        .limit(5)
        .all()
    )
    for c in convs:
        last_msg = (
            db.query(Message)
            .filter(Message.conversation_id == c.id, Message.organization_id == org_id)
            .order_by(Message.created_at.desc())
            .first()
        )
        snippet = (last_msg.content[:80] + "...") if last_msg else "No messages"
        activities.append(
            ActivityItem(
                id=c.id,
                type="conversation",
                title=f"Chat #{c.id[:8]} ({c.category.replace('_', ' ').title()})",
                subtitle=snippet,
                timestamp=c.updated_at,
                status=c.status,
            )
        )

    docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.organization_id == org_id)
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(3)
        .all()
    )
    for d in docs:
        activities.append(
            ActivityItem(
                id=d.id,
                type="document",
                title=f"Indexed: {d.filename}",
                subtitle=f"{d.chunk_count} chunks embedded ({d.source_type})",
                timestamp=d.created_at,
                status=d.status,
            )
        )

    activities.sort(key=lambda a: a.timestamp, reverse=True)
    return activities[:10]
