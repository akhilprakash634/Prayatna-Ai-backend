import json
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from database import DATA_DIR, get_db
from models import ChatbotSetting, Organization, Subscription
from schemas import (
    ChatbotConfigResponse,
    ChatbotConfigUpdate,
    ChatbotThemeConfig,
    OrganizationUpdateRequest,
    ProfileUpdateRequest,
    SubscriptionResponse,
    UsageSummaryResponse,
    WidgetAssetUploadResponse,
    WidgetPresetItem,
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


CURATED_WIDGET_PRESETS = [
    WidgetPresetItem(
        id="friendly_robot",
        name="Friendly Robot",
        description="Charming animated AI robot with glowing eyes and breathing tilt.",
        type="lottie",
        preview_url="/animations/friendly-robot.json",
        animation_url="/animations/friendly-robot.json",
        category="Characters",
    ),
    WidgetPresetItem(
        id="ai_sparkle",
        name="AI Sparkle",
        description="Modern glowing AI star with smooth rotation and pulsing glow.",
        type="lottie",
        preview_url="/animations/ai-sparkle.json",
        animation_url="/animations/ai-sparkle.json",
        category="Abstract",
    ),
    WidgetPresetItem(
        id="chatty_bubble",
        name="Chatty Bubble",
        description="Expressive floating speech bubble with animated typing dots.",
        type="lottie",
        preview_url="/animations/chatty-bubble.json",
        animation_url="/animations/chatty-bubble.json",
        category="Conversational",
    ),
]

ALLOWED_ASSET_EXTENSIONS = {
    ".json": "lottie",
    ".lottie": "lottie",
    ".gif": "gif",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".svg": "image",
    ".webm": "webm",
}

MAX_ASSET_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def sanitize_asset_filename(filename: str) -> str:
    """Sanitize uploaded widget asset filename and validate allowed extension."""
    import re
    basename = os.path.basename(filename)
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", basename)
    name, ext = os.path.splitext(cleaned)
    ext_lower = ext.lower()
    if ext_lower not in ALLOWED_ASSET_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_ASSET_EXTENSIONS.keys()))
        raise ValueError(f"Unsupported file format '{ext}'. Allowed formats: {allowed}")
    return cleaned


@router.get("/widget/presets", response_model=List[WidgetPresetItem])
def get_widget_presets(ctx: AuthContext = Depends(require_client_admin)):
    """Return curated animated character and avatar presets."""
    return CURATED_WIDGET_PRESETS


@router.post("/widget/upload-asset", response_model=WidgetAssetUploadResponse)
async def upload_widget_asset(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_client_admin),
):
    """Upload custom animation (Lottie JSON / GIF / WebM) or static avatar image with validation."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file selected.")

    try:
        clean_name = sanitize_asset_filename(file.filename)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    ext = os.path.splitext(clean_name)[1].lower()
    if ext not in ALLOWED_ASSET_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_ASSET_EXTENSIONS.keys()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {allowed}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    if len(file_bytes) > MAX_ASSET_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of 5MB (size: {len(file_bytes)} bytes).",
        )

    asset_type = ALLOWED_ASSET_EXTENSIONS[ext]

    # Content structure validation
    if ext in (".json", ".lottie"):
        try:
            parsed = json.loads(file_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Lottie JSON must be a JSON object.")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Lottie JSON file: {e}",
            )
    elif ext == ".gif":
        if not (file_bytes.startswith(b"GIF87a") or file_bytes.startswith(b"GIF89a")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid GIF file format header.",
            )

    # Isolated per-org asset directory
    org_folder = os.path.join(DATA_DIR, "widget_assets", ctx.organization_id)
    os.makedirs(org_folder, exist_ok=True)

    unique_token = uuid.uuid4().hex[:8]
    stored_filename = f"{unique_token}_{clean_name}"
    file_path = os.path.join(org_folder, stored_filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    public_url = f"/api/widget/assets/{ctx.organization_id}/{stored_filename}"

    return WidgetAssetUploadResponse(
        url=public_url,
        filename=clean_name,
        size=len(file_bytes),
        asset_type=asset_type,
    )


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

