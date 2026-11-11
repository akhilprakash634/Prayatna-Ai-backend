import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AccountSetupToken,
    ChatbotSetting,
    Conversation,
    Enquiry,
    KnowledgeDocument,
    Organization,
    Subscription,
    UsageLog,
    utc_now,
)
from services.security import hash_token

PLAN_DEFAULTS: Dict[str, Dict[str, int]] = {
    "Basic": {
        "monthly_price": 999,
        "conversation_limit": 200,
        "ai_usage_limit": 2000,
    },
    "Professional": {
        "monthly_price": 2999,
        "conversation_limit": 1000,
        "ai_usage_limit": 10000,
    },
    "Enterprise": {
        "monthly_price": 7999,
        "conversation_limit": 10000,
        "ai_usage_limit": 100000,
    },
}


def normalize_plan_name(plan_name: Optional[str]) -> str:
    if not plan_name:
        return "Basic"
    for canonical in PLAN_DEFAULTS:
        if canonical.lower() == plan_name.strip().lower():
            return canonical
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Subscription plan must be one of: Basic, Professional, Enterprise.",
    )


def get_plan_defaults(plan_name: str) -> Dict[str, int]:
    canonical = normalize_plan_name(plan_name)
    return dict(PLAN_DEFAULTS[canonical])


def generate_unique_chatbot_id(db: Session, slug: str) -> str:
    if slug == "prayatna":
        existing = db.query(ChatbotSetting).filter(ChatbotSetting.chatbot_id == "prayatna-bot").first()
        if not existing:
            return "prayatna-bot"

    for _ in range(10):
        candidate = f"{slug}-{secrets.token_hex(3)}"
        if not db.query(ChatbotSetting).filter(ChatbotSetting.chatbot_id == candidate).first():
            return candidate
    return f"bot-{secrets.token_hex(6)}"


def create_setup_token_for_user(db: Session, user_id: str, expires_hours: int = 24) -> str:
    """Invalidate unused setup tokens for the user and create a new CSPRNG setup token."""
    now = utc_now()
    db.query(AccountSetupToken).filter(
        AccountSetupToken.user_id == user_id,
        AccountSetupToken.used_at.is_(None),
    ).update({"used_at": now})

    raw_token = secrets.token_urlsafe(32)
    record = AccountSetupToken(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(hours=expires_hours),
    )
    db.add(record)
    return raw_token


def record_usage(
    db: Session,
    organization_id: str,
    event_type: str,
    quantity: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> UsageLog:
    log = UsageLog(
        organization_id=organization_id,
        event_type=event_type,
        quantity=max(1, int(quantity)),
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(log)
    return log


def _billing_window_start(subscription: Optional[Subscription]) -> datetime:
    now = utc_now()
    if subscription and subscription.start_date:
        start = subscription.start_date
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        return start if start > thirty_days_ago else thirty_days_ago
    return now - timedelta(days=30)


def get_org_usage_summary(db: Session, organization_id: str) -> Dict[str, Any]:
    subscription = db.query(Subscription).filter(Subscription.organization_id == organization_id).first()
    window_start = _billing_window_start(subscription)

    # Periodic usage logs in current 30-day cycle
    rows = (
        db.query(UsageLog.event_type, func.coalesce(func.sum(UsageLog.quantity), 0))
        .filter(
            UsageLog.organization_id == organization_id,
            UsageLog.created_at >= window_start,
        )
        .group_by(UsageLog.event_type)
        .all()
    )
    cycle_counts = {event_type: int(total) for event_type, total in rows}

    # Lifetime aggregate usage logs
    all_rows = (
        db.query(UsageLog.event_type, func.coalesce(func.sum(UsageLog.quantity), 0))
        .filter(UsageLog.organization_id == organization_id)
        .group_by(UsageLog.event_type)
        .all()
    )
    lifetime_counts = {event_type: int(total) for event_type, total in all_rows}

    total_conversations = db.query(Conversation).filter(Conversation.organization_id == organization_id).count()
    total_enquiries = db.query(Enquiry).filter(Enquiry.organization_id == organization_id).count()
    total_documents = db.query(KnowledgeDocument).filter(KnowledgeDocument.organization_id == organization_id).count()

    return {
        "cycle_conversations": cycle_counts.get("conversation", 0),
        "cycle_ai_requests": cycle_counts.get("ai_request", 0),
        "cycle_document_uploads": cycle_counts.get("document_upload", 0),
        "cycle_website_scrapes": cycle_counts.get("website_scrape", 0),
        "total_conversations": total_conversations,
        "total_enquiries": total_enquiries,
        "total_documents": total_documents,
        "total_ai_requests": lifetime_counts.get("ai_request", 0),
        "conversation_limit": subscription.conversation_limit if subscription else 200,
        "ai_usage_limit": subscription.ai_usage_limit if subscription else 2000,
    }


def enforce_subscription_limits(db: Session, organization_id: str, is_new_conversation: bool = False) -> None:
    subscription = db.query(Subscription).filter(Subscription.organization_id == organization_id).first()
    if not subscription:
        return

    if subscription.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This organization's subscription is currently inactive.",
        )

    usage = get_org_usage_summary(db, organization_id)
    if usage["cycle_ai_requests"] >= subscription.ai_usage_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly AI usage limit reached for this organization.",
        )
    if is_new_conversation and usage["cycle_conversations"] >= subscription.conversation_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly conversation limit reached for this organization.",
        )


def resolve_public_chatbot(
    db: Session,
    chatbot_id: Optional[str] = None,
) -> Tuple[Organization, ChatbotSetting]:
    """
    Resolve an active organization and its chatbot settings for public endpoints.
    Defaults to Prayatna's bot when chatbot_id is omitted to preserve legacy links.
    """
    clean_bot_id = (chatbot_id or "").strip()

    if clean_bot_id:
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.chatbot_id == clean_bot_id).first()
        if not setting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot not found.")
        org = db.query(Organization).filter(Organization.id == setting.organization_id).first()
    else:
        org = db.query(Organization).filter(Organization.slug == "prayatna").first()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Default chatbot not configured.")
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()

    if not org or not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot configuration not found.")

    if org.status != "active" or not setting.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This organization's chatbot is currently suspended.",
        )

    subscription = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    if subscription and subscription.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This organization's chatbot subscription is currently suspended.",
        )

    return org, setting


def get_public_chatbot_metadata(db: Session, chatbot_id: Optional[str] = None) -> Dict[str, Any]:
    """Return safe public branding config (including suspended notice if inactive)."""
    clean_bot_id = (chatbot_id or "").strip()
    if clean_bot_id:
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.chatbot_id == clean_bot_id).first()
        org = db.query(Organization).filter(Organization.id == setting.organization_id).first() if setting else None
    else:
        org = db.query(Organization).filter(Organization.slug == "prayatna").first()
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first() if org else None

    if not org or not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot not found.")

    subscription = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    is_available = org.status == "active" and bool(setting.is_active) and (
        not subscription or subscription.status == "active"
    )
    unavailable_reason = None
    if not is_available:
        unavailable_reason = (
            f"{org.name}'s support assistant is currently unavailable. Please contact the organization directly."
        )

    return {
        "chatbot_id": setting.chatbot_id,
        "organization_name": org.name,
        "organization_slug": org.slug,
        "bot_name": setting.bot_name,
        "assistant_name": setting.assistant_name,
        "welcome_message": setting.welcome_message,
        "primary_color": setting.primary_color,
        "logo_url": setting.logo_url or org.logo_url,
        "website": org.website,
        "phone": org.phone,
        "is_available": is_available,
        "unavailable_reason": unavailable_reason,
    }

