import os
import secrets
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AuditLog,
    ChatbotSetting,
    Conversation,
    Enquiry,
    KnowledgeDocument,
    Organization,
    Subscription,
    UsageLog,
    User,
    utc_now,
)
from schemas import (
    AdminUserBrief,
    AuditLogResponse,
    ChatbotConfigResponse,
    CreateClientResponse,
    DeleteOrganizationRequest,
    OrganizationCreateRequest,
    OrganizationDetailResponse,
    OrganizationSummary,
    OrganizationUpdateRequest,
    ResetCredentialsRequest,
    ResetCredentialsResponse,
    SessionResponse,
    SubscriptionResponse,
    SubscriptionUpdateRequest,
    SuperAdminDashboardStats,
    UsageSummaryResponse,
)
from routes.auth import _build_session_response
from services.rag import rag_service
from services.security import (
    AuthContext,
    create_access_token,
    get_auth_context,
    get_client_ip,
    hash_password,
    require_super_admin,
    set_auth_cookies,
    validate_slug,
    verify_csrf,
    write_audit_log,
)
from services.tenant import (
    create_setup_token_for_user,
    generate_unique_chatbot_id,
    get_org_usage_summary,
    get_plan_defaults,
    get_token_usage_by_organization,
    get_token_usage_totals,
    normalize_plan_name,
)

router = APIRouter(prefix="/api/super-admin", tags=["Super Admin"])


def _build_org_detail(db: Session, org: Organization) -> OrganizationDetailResponse:
    admins = (
        db.query(User)
        .filter(User.organization_id == org.id, User.role == "client_admin")
        .order_by(User.created_at.asc())
        .all()
    )
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
    subscription = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    usage = get_org_usage_summary(db, org.id)

    chatbot_resp = None
    if setting:
        chatbot_resp = ChatbotConfigResponse(
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
        )

    return OrganizationDetailResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        phone=org.phone,
        website=org.website,
        industry=org.industry,
        logo_url=org.logo_url,
        status=org.status,
        plan=org.plan,
        created_at=org.created_at,
        updated_at=org.updated_at,
        admins=[
            AdminUserBrief(
                id=u.id,
                name=u.name,
                email=u.email,
                status=u.status,
                last_login_at=u.last_login_at,
            )
            for u in admins
        ],
        chatbot=chatbot_resp,
        subscription=SubscriptionResponse.model_validate(subscription) if subscription else None,
        usage=UsageSummaryResponse(**usage),
    )


@router.get("/dashboard", response_model=SuperAdminDashboardStats)
def get_super_admin_dashboard(
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    total_orgs = db.query(Organization).count()
    active_orgs = db.query(Organization).filter(Organization.status == "active").count()
    suspended_orgs = db.query(Organization).filter(Organization.status == "suspended").count()
    total_conversations = db.query(Conversation).count()
    total_enquiries = db.query(Enquiry).count()
    total_ai_requests = int(
        db.query(func.coalesce(func.sum(UsageLog.quantity), 0))
        .filter(UsageLog.event_type == "ai_request")
        .scalar()
        or 0
    )
    platform_tokens = get_token_usage_totals(db)

    return SuperAdminDashboardStats(
        total_organizations=total_orgs,
        active_organizations=active_orgs,
        suspended_organizations=suspended_orgs,
        total_conversations=total_conversations,
        total_enquiries=total_enquiries,
        total_ai_requests=total_ai_requests,
        total_input_tokens=platform_tokens["input_tokens"],
        total_output_tokens=platform_tokens["output_tokens"],
        total_tokens=platform_tokens["total_tokens"],
        total_estimated_cost_usd=platform_tokens["estimated_cost_usd"],
    )


@router.get("/clients", response_model=List[OrganizationSummary])
def list_clients(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Organization)
    if status_filter and status_filter in ("active", "suspended"):
        query = query.filter(Organization.status == status_filter)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(Organization.name.ilike(term) | Organization.slug.ilike(term))

    orgs = query.order_by(Organization.created_at.desc()).all()
    token_usage_by_org = get_token_usage_by_organization(db)

    results: List[OrganizationSummary] = []
    for org in orgs:
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
        admin = (
            db.query(User)
            .filter(User.organization_id == org.id, User.role == "client_admin")
            .order_by(User.created_at.asc())
            .first()
        )
        conv_count = db.query(Conversation).filter(Conversation.organization_id == org.id).count()
        enq_count = db.query(Enquiry).filter(Enquiry.organization_id == org.id).count()
        ai_count = int(
            db.query(func.coalesce(func.sum(UsageLog.quantity), 0))
            .filter(UsageLog.organization_id == org.id, UsageLog.event_type == "ai_request")
            .scalar()
            or 0
        )
        org_tokens = token_usage_by_org.get(org.id, {})

        results.append(
            OrganizationSummary(
                id=org.id,
                name=org.name,
                slug=org.slug,
                phone=org.phone,
                website=org.website,
                industry=org.industry,
                status=org.status,
                plan=org.plan,
                chatbot_id=setting.chatbot_id if setting else None,
                admin_email=admin.email if admin else None,
                total_conversations=conv_count,
                total_enquiries=enq_count,
                total_ai_requests=ai_count,
                total_input_tokens=org_tokens.get("input_tokens", 0),
                total_output_tokens=org_tokens.get("output_tokens", 0),
                total_tokens=org_tokens.get("total_tokens", 0),
                estimated_cost_usd=org_tokens.get("estimated_cost_usd", 0.0),
                created_at=org.created_at,
            )
        )

    return results


@router.post("/clients", response_model=CreateClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    req: OrganizationCreateRequest,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    slug = validate_slug(req.organization_slug)
    email = req.admin_email.strip().lower()

    if db.query(Organization).filter(Organization.slug == slug).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization slug '{slug}' is already in use.",
        )

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{email}' already exists.",
        )

    plan_name = normalize_plan_name(req.subscription_plan)
    plan_cfg = get_plan_defaults(plan_name)
    now = utc_now()

    # 1. Create organization
    org = Organization(
        name=req.organization_name.strip(),
        slug=slug,
        phone=req.phone.strip() if req.phone else None,
        website=req.website.strip() if req.website else None,
        industry=req.industry.strip() if req.industry else None,
        status=req.account_status,
        plan=plan_name,
    )
    db.add(org)
    db.flush()

    # 2 & 3. Create client admin & associate with organization
    raw_password = req.admin_password.strip() if req.admin_password else secrets.token_urlsafe(24)
    admin_user = User(
        name=req.admin_name.strip(),
        email=email,
        password_hash=hash_password(raw_password),
        role="client_admin",
        organization_id=org.id,
        status="active" if req.admin_password else "invited",
    )
    db.add(admin_user)
    db.flush()

    # 4, 5, 6. Initialize chatbot settings & isolated ChromaDB collection
    chatbot_id = generate_unique_chatbot_id(db, slug)
    collection_name = f"org_{slug.replace('-', '_')}"
    rag_service.ensure_org_collection(org_slug=slug, collection_name=collection_name)

    setting = ChatbotSetting(
        organization_id=org.id,
        chatbot_id=chatbot_id,
        bot_name=f"{org.name} Assistant",
        assistant_name="Support Assistant",
        welcome_message=f"Hello! Welcome to {org.name}. How can I help you today?",
        primary_color="#0d9488",
        knowledge_collection=collection_name,
        is_active=(org.status == "active"),
    )
    db.add(setting)

    # 7. Initialize subscription record
    subscription = Subscription(
        organization_id=org.id,
        plan_name=plan_name,
        monthly_price=plan_cfg["monthly_price"],
        status="active" if org.status == "active" else "suspended",
        start_date=now,
        renewal_date=now + timedelta(days=30),
        conversation_limit=plan_cfg["conversation_limit"],
        ai_usage_limit=plan_cfg["ai_usage_limit"],
    )
    db.add(subscription)

    # 8. Provide secure one-time account setup link
    raw_setup_token = create_setup_token_for_user(db, admin_user.id, expires_hours=24)

    write_audit_log(
        db,
        action="org_create",
        actor_user_id=ctx.user.id,
        target_user_id=admin_user.id,
        target_organization_id=org.id,
        details={"slug": slug, "plan": plan_name, "chatbot_id": chatbot_id},
        ip_address=get_client_ip(request),
    )
    db.commit()

    app_base = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
    setup_path = f"/setup-account?token={raw_setup_token}"
    setup_link = f"{app_base}{setup_path}" if app_base else setup_path
    direct_chat_path = f"/chat?bot={chatbot_id}"
    widget_src = f"{app_base}/widget.js" if app_base else "/widget.js"
    embed_snippet = (
        f'<script src="{widget_src}" data-bot="{chatbot_id}" defer></script>'
    )

    return CreateClientResponse(
        organization=_build_org_detail(db, org),
        setup_link=setup_link,
        setup_token_expires_hours=24,
        embed_snippet=embed_snippet,
        direct_chat_path=direct_chat_path,
    )


@router.get("/clients/{org_id}", response_model=OrganizationDetailResponse)
def get_client_detail(
    org_id: str,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return _build_org_detail(db, org)


@router.patch("/clients/{org_id}", response_model=OrganizationDetailResponse)
def update_client(
    org_id: str,
    req: OrganizationUpdateRequest,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
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

    write_audit_log(
        db,
        action="org_update",
        actor_user_id=ctx.user.id,
        target_organization_id=org.id,
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(org)
    return _build_org_detail(db, org)


@router.post("/clients/{org_id}/activate", response_model=OrganizationDetailResponse)
def activate_client(
    org_id: str,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    org.status = "active"
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
    if setting:
        setting.is_active = True
    subscription = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    if subscription and subscription.status == "suspended":
        subscription.status = "active"

    write_audit_log(
        db,
        action="org_activate",
        actor_user_id=ctx.user.id,
        target_organization_id=org.id,
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(org)
    return _build_org_detail(db, org)


@router.post("/clients/{org_id}/suspend", response_model=OrganizationDetailResponse)
def suspend_client(
    org_id: str,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    org.status = "suspended"
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
    if setting:
        setting.is_active = False

    write_audit_log(
        db,
        action="org_suspend",
        actor_user_id=ctx.user.id,
        target_organization_id=org.id,
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(org)
    return _build_org_detail(db, org)


@router.delete("/clients/{org_id}")
def delete_client(
    org_id: str,
    req: DeleteOrganizationRequest,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    if req.confirm_slug.strip().lower() != org.slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation slug does not match organization slug.",
        )

    conv_count = db.query(Conversation).filter(Conversation.organization_id == org.id).count()
    enq_count = db.query(Enquiry).filter(Enquiry.organization_id == org.id).count()
    doc_count = db.query(KnowledgeDocument).filter(KnowledgeDocument.organization_id == org.id).count()
    if (conv_count > 0 or enq_count > 0 or doc_count > 0) and not req.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Organization has existing data ({conv_count} conversations, {enq_count} enquiries, "
                f"{doc_count} documents). Set force=true after confirming backup to delete permanently."
            ),
        )

    slug = org.slug
    org_name = org.name

    write_audit_log(
        db,
        action="org_delete",
        actor_user_id=ctx.user.id,
        target_organization_id=None,
        details={"deleted_org_id": org.id, "slug": slug, "name": org_name},
        ip_address=get_client_ip(request),
    )
    db.delete(org)
    db.commit()

    rag_service.delete_org_store(slug)
    return {"status": "deleted", "slug": slug, "message": f"Organization '{org_name}' deleted."}


@router.patch("/clients/{org_id}/subscription", response_model=OrganizationDetailResponse)
def update_client_subscription(
    org_id: str,
    req: SubscriptionUpdateRequest,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    plan_name = normalize_plan_name(req.plan_name)
    defaults = get_plan_defaults(plan_name)
    now = utc_now()

    sub = db.query(Subscription).filter(Subscription.organization_id == org.id).first()
    if not sub:
        sub = Subscription(
            organization_id=org.id,
            plan_name=plan_name,
            monthly_price=req.monthly_price if req.monthly_price is not None else defaults["monthly_price"],
            status=req.status or "active",
            start_date=now,
            renewal_date=now + timedelta(days=req.renewal_days or 30),
            conversation_limit=(
                req.conversation_limit if req.conversation_limit is not None else defaults["conversation_limit"]
            ),
            ai_usage_limit=req.ai_usage_limit if req.ai_usage_limit is not None else defaults["ai_usage_limit"],
        )
        db.add(sub)
    else:
        sub.plan_name = plan_name
        sub.monthly_price = req.monthly_price if req.monthly_price is not None else defaults["monthly_price"]
        sub.conversation_limit = (
            req.conversation_limit if req.conversation_limit is not None else defaults["conversation_limit"]
        )
        sub.ai_usage_limit = (
            req.ai_usage_limit if req.ai_usage_limit is not None else defaults["ai_usage_limit"]
        )
        if req.status is not None:
            sub.status = req.status
        if req.renewal_days is not None:
            sub.renewal_date = now + timedelta(days=req.renewal_days)

    org.plan = plan_name

    write_audit_log(
        db,
        action="subscription_update",
        actor_user_id=ctx.user.id,
        target_organization_id=org.id,
        details={"plan": plan_name, "status": sub.status},
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(org)
    return _build_org_detail(db, org)


@router.post("/clients/{org_id}/reset-credentials", response_model=ResetCredentialsResponse)
def reset_client_admin_credentials(
    org_id: str,
    req: ResetCredentialsRequest,
    request: Request,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    admin = (
        db.query(User)
        .filter(User.organization_id == org.id, User.role == "client_admin")
        .order_by(User.created_at.asc())
        .first()
    )
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No client admin found for organization.")

    password_updated = False
    if req.new_password:
        admin.password_hash = hash_password(req.new_password)
        admin.status = "active"
        password_updated = True
    else:
        # Invalidate old password until user sets a new password via setup link
        admin.password_hash = hash_password(secrets.token_urlsafe(24))
        admin.status = "invited"

    admin.token_version += 1
    raw_token = create_setup_token_for_user(db, admin.id, expires_hours=24)

    write_audit_log(
        db,
        action="credentials_reset",
        actor_user_id=ctx.user.id,
        target_user_id=admin.id,
        target_organization_id=org.id,
        details={"password_updated_directly": password_updated},
        ip_address=get_client_ip(request),
    )
    db.commit()

    app_base = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
    setup_path = f"/setup-account?token={raw_token}"
    setup_link = f"{app_base}{setup_path}" if app_base else setup_path

    return ResetCredentialsResponse(
        user_id=admin.id,
        email=admin.email,
        setup_link=setup_link,
        password_updated=password_updated,
        message=(
            "Client admin password reset and existing sessions invalidated."
            if password_updated
            else "Existing sessions revoked and secure 24h setup link generated."
        ),
    )


@router.post("/clients/{org_id}/impersonate", response_model=SessionResponse)
def impersonate_client(
    org_id: str,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    write_audit_log(
        db,
        action="impersonate_start",
        actor_user_id=ctx.user.id,
        target_organization_id=org.id,
        details={"org_slug": org.slug},
        ip_address=get_client_ip(request),
    )
    db.commit()

    imp_token = create_access_token(
        {
            "sub": ctx.user.id,
            "role": ctx.user.role,
            "ver": ctx.user.token_version,
            "imp_org": org.id,
            "imp_by": ctx.user.id,
        },
        expires_minutes=120,
    )
    csrf = set_auth_cookies(response, request, imp_token)
    return _build_session_response(
        db=db,
        user=ctx.user,
        org=org,
        is_impersonating=True,
        impersonator_user_id=ctx.user.id,
        csrf_token=csrf,
    )


@router.post("/exit-impersonation", response_model=SessionResponse)
def exit_impersonation(
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    verify_csrf(request)
    if ctx.user.role != "super_admin" or not ctx.is_impersonating:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not inside an impersonation session.")

    write_audit_log(
        db,
        action="impersonate_end",
        actor_user_id=ctx.user.id,
        target_organization_id=ctx.organization_id,
        ip_address=get_client_ip(request),
    )
    db.commit()

    clean_token = create_access_token(
        {
            "sub": ctx.user.id,
            "role": ctx.user.role,
            "ver": ctx.user.token_version,
        }
    )
    csrf = set_auth_cookies(response, request, clean_token)
    return _build_session_response(db=db, user=ctx.user, org=None, csrf_token=csrf)


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    organization_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if organization_id:
        query = query.filter(AuditLog.target_organization_id == organization_id)
    return query.order_by(AuditLog.created_at.desc()).limit(limit).all()

