from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Conversation, Enquiry, KnowledgeDocument, Message
from schemas import DashboardStats, ActivityItem

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    total_convs = db.query(Conversation).count()
    total_enqs = db.query(Enquiry).count()
    app_enqs = db.query(Enquiry).filter(Enquiry.category == "appointment").count()
    payment_requests = db.query(Enquiry).filter(Enquiry.category == "payment_support").count()
    unresolved_convs = db.query(Conversation).filter(Conversation.status == "active").count()

    return DashboardStats(
        total_conversations=total_convs,
        total_enquiries=total_enqs,
        appointment_enquiries=app_enqs,
        payment_support_requests=payment_requests,
        unresolved_conversations=unresolved_convs
    )

@router.get("/recent-activity", response_model=List[ActivityItem])
def get_recent_activity(db: Session = Depends(get_db)):
    activities: List[ActivityItem] = []

    # Recent enquiries (up to 5)
    enquiries = db.query(Enquiry).order_by(Enquiry.created_at.desc()).limit(5).all()
    for e in enquiries:
        activities.append(ActivityItem(
            id=e.id,
            type="enquiry",
            title=f"Enquiry: {e.parent_name} ({e.interested_service})",
            subtitle=f"{e.category.title()} enquiry via {e.preferred_contact} • Phone: {e.phone}",
            timestamp=e.created_at,
            status=e.status
        ))

    # Recent conversations (up to 5)
    convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(5).all()
    for c in convs:
        last_msg = db.query(Message).filter(Message.conversation_id == c.id).order_by(Message.created_at.desc()).first()
        snippet = (last_msg.content[:80] + "...") if last_msg else "No messages"
        activities.append(ActivityItem(
            id=c.id,
            type="conversation",
            title=f"Chat #{c.id[:8]} ({c.category.replace('_', ' ').title()})",
            subtitle=snippet,
            timestamp=c.updated_at,
            status=c.status
        ))

    # Recent knowledge documents (up to 3)
    docs = db.query(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).limit(3).all()
    for d in docs:
        activities.append(ActivityItem(
            id=d.id,
            type="document",
            title=f"Indexed: {d.filename}",
            subtitle=f"{d.chunk_count} chunks embedded ({d.source_type})",
            timestamp=d.created_at,
            status=d.status
        ))

    # Sort all by timestamp descending
    activities.sort(key=lambda a: a.timestamp, reverse=True)
    return activities[:10]
