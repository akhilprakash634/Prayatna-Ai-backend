from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models import ChatbotSetting, Organization, Subscription
from schemas import (
    ChatbotConfigResponse,
    ChatbotConfigUpdate,
    ChatbotThemeConfig,
    OrganizationUpdateRequest,
    ProfileUpdateRequest,
    SubscriptionResponse,
    UsageSummaryResponse,
)
from services.security import (
    AuthContext,
    require_client_admin,
    validate_hex_color,
    validate_safe_url_or_path,
)
from services.tenant import (
    get_org_usage_summary,
    resolve_chatbot_theme_config,
    serialize_chatbot_theme_config,
)

router = APIRouter(prefix="/api/admin", tags=["Client Admin Settings"])


def _to_chatbot_response(org: Organization, setting: ChatbotSetting) -> ChatbotConfigResponse:
    return ChatbotConfigResponse(
        id=setting.id,
        organization_id=setting.organization_id,
        chatbot_id=setting.chatbot_id,
        bot_name=setting.bot_name,
        assistant_name=setting.assistant_name,
        welcome_message=setting.welcome_message,
        primary_color=setting.primary_color,
        logo_url=setting.logo_url,
        custom_instructions=setting.custom_instructions,
        knowledge_collection=setting.knowledge_collection,
        is_active=setting.is_active,
        organization_name=org.name,
        organization_slug=org.slug,
        organization_status=org.status,
        theme_config=ChatbotThemeConfig(**resolve_chatbot_theme_config(org, setting)),
    )


@router.get("/chatbot", response_model=ChatbotConfigResponse)
def get_chatbot_config(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == ctx.organization_id).first()
    if not setting or not ctx.organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot configuration not found.")
    return _to_chatbot_response(ctx.organization, setting)


@router.patch("/chatbot", response_model=ChatbotConfigResponse)
def update_chatbot_config(
    req: ChatbotConfigUpdate,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == ctx.organization_id).first()
    if not setting or not ctx.organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot configuration not found.")

    if req.bot_name is not None:
        setting.bot_name = req.bot_name.strip()
    if req.assistant_name is not None:
        setting.assistant_name = req.assistant_name.strip()
    if req.welcome_message is not None:
        setting.welcome_message = req.welcome_message.strip()
    if req.primary_color is not None:
        setting.primary_color = validate_hex_color(req.primary_color)
    if req.logo_url is not None:
        setting.logo_url = validate_safe_url_or_path(req.logo_url, "logo_url")
    if req.custom_instructions is not None:
        setting.custom_instructions = req.custom_instructions.strip() or None
    if req.is_active is not None:
        setting.is_active = bool(req.is_active)
    if req.theme_config is not None:
        setting.theme_config_json = serialize_chatbot_theme_config(req.theme_config)

    db.commit()
    db.refresh(setting)
    return _to_chatbot_response(ctx.organization, setting)


@router.get("/account")
def get_account_overview(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == ctx.organization_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
    sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    usage = get_org_usage_summary(db, org.id)

    return {
        "user": {
            "id": ctx.user.id,
            "name": ctx.user.name,
            "email": ctx.user.email,
            "role": ctx.effective_role,
            "is_impersonating": ctx.is_impersonating,
        },
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "phone": org.phone,
            "website": org.website,
            "industry": org.industry,
            "logo_url": org.logo_url,
            "status": org.status,
            "plan": org.plan,
        },
        "chatbot": _to_chatbot_response(org, setting) if setting else None,
        "subscription": SubscriptionResponse.model_validate(sub) if sub else None,
        "usage": UsageSummaryResponse(**usage),
    }


@router.patch("/account/organization")
def update_own_organization(
    req: OrganizationUpdateRequest,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == ctx.organization_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    if req.name is not None:
        org.name = req.name.strip()
    if req.phone is not None:
        org.phone = req.phone.strip() or None
    if req.website is not None:
        org.website = req.website.strip() or None
    if req.industry is not None:
        org.industry = req.industry.strip() or None
    if req.logo_url is not None:
        org.logo_url = req.logo_url.strip() or None

    db.commit()
    db.refresh(org)
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "phone": org.phone,
        "website": org.website,
        "industry": org.industry,
        "logo_url": org.logo_url,
        "status": org.status,
        "plan": org.plan,
    }


@router.patch("/account/profile")
def update_own_profile(
    req: ProfileUpdateRequest,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    if ctx.is_impersonating:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Profile edits are disabled during Super Admin impersonation.",
        )
    ctx.user.name = req.name.strip()
    db.commit()
    return {"id": ctx.user.id, "name": ctx.user.name, "email": ctx.user.email}

