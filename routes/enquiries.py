from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models import Conversation, Enquiry
from schemas import EnquiryCreate, EnquiryResponse, EnquiryUpdate
from services.security import (
    AuthContext,
    assert_org_access,
    get_client_ip,
    public_chat_rate_limiter,
    require_client_admin,
)
from services.tenant import resolve_public_chatbot

router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])


@router.post("", response_model=EnquiryResponse, status_code=status.HTTP_201_CREATED)
def create_enquiry(
    payload: EnquiryCreate,
    request: Request,
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
    return new_enquiry


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
