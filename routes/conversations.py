from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models import Conversation, Enquiry, Message
from schemas import ConversationDetail, ConversationSummary, MessageResponse
from services.security import AuthContext, assert_org_access, require_client_admin

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=List[ConversationSummary])
def list_conversations(
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Conversation).filter(Conversation.organization_id == ctx.organization_id)
    if category:
        query = query.filter(Conversation.category == category)
    if status_filter:
        query = query.filter(Conversation.status == status_filter)

    conversations = query.order_by(Conversation.updated_at.desc()).all()
    results = []

    for conv in conversations:
        msg_count = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id, Message.organization_id == ctx.organization_id)
            .count()
        )
        enquiry = (
            db.query(Enquiry)
            .filter(Enquiry.conversation_id == conv.id, Enquiry.organization_id == ctx.organization_id)
            .first()
        )
        customer_name = enquiry.parent_name if enquiry else None

        if search:
            s_lower = search.lower()
            match_id = s_lower in conv.id.lower()
            match_name = customer_name and s_lower in customer_name.lower()
            if not (match_id or match_name):
                continue

        results.append(
            ConversationSummary(
                id=conv.id,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                status=conv.status,
                category=conv.category,
                message_count=msg_count,
                customer_name=customer_name,
            )
        )

    return results


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation_detail(
    conversation_id: str,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    assert_org_access(conv.organization_id, ctx.organization_id, "Conversation")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.organization_id == ctx.organization_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return ConversationDetail(
        id=conv.id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        status=conv.status,
        category=conv.category,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
def get_conversation_messages(
    conversation_id: str,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    assert_org_access(conv.organization_id, ctx.organization_id, "Conversation")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.organization_id == ctx.organization_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [MessageResponse.model_validate(m) for m in messages]
