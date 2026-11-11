from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models import AccountSetupToken, ChatbotSetting, Organization, User, utc_now
from schemas import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    OrganizationBrief,
    SessionResponse,
    SetupAccountRequest,
)
from services.security import (
    AuthContext,
    CSRF_COOKIE_NAME,
    clear_auth_cookies,
    create_access_token,
    get_auth_context,
    get_client_ip,
    hash_password,
    hash_token,
    set_auth_cookies,
    verify_csrf,
    verify_password,
)
from services.security import write_audit_log

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _build_session_response(
    db: Session,
    user: User,
    org: Organization | None,
    is_impersonating: bool = False,
    impersonator_user_id: str | None = None,
    csrf_token: str | None = None,
) -> SessionResponse:
    org_brief = None
    if org:
        setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
        org_brief = OrganizationBrief(
            id=org.id,
            name=org.name,
            slug=org.slug,
            status=org.status,
            plan=org.plan,
            chatbot_id=setting.chatbot_id if setting else None,
        )

    return SessionResponse(
        user=AuthUserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            organization_id=org.id if org else user.organization_id,
            status=user.status,
        ),
        organization=org_brief,
        is_impersonating=is_impersonating,
        impersonator_user_id=impersonator_user_id,
        csrf_token=csrf_token,
    )


@router.post("/login", response_model=SessionResponse)
def client_admin_login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate a Client Admin into their organization's dashboard."""
    email = req.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(req.password, user.password_hash):
        write_audit_log(
            db,
            action="login_failed",
            details={"email": email, "portal": "client_admin"},
            ip_address=get_client_ip(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.role != "client_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please sign in through the Super Admin portal.",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending activation or disabled. Please use your setup link or contact support.",
        )

    org = db.query(Organization).filter(Organization.id == user.organization_id).first() if user.organization_id else None
    if not org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization is associated with this account.",
        )

    if org.status != "active":
        write_audit_log(
            db,
            action="login_blocked_suspended",
            actor_user_id=user.id,
            target_organization_id=org.id,
            details={"email": email},
            ip_address=get_client_ip(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization account is suspended. Access to the client dashboard is blocked.",
        )

    user.last_login_at = utc_now()
    write_audit_log(
        db,
        action="login_success",
        actor_user_id=user.id,
        target_organization_id=org.id,
        ip_address=get_client_ip(request),
    )
    db.commit()

    token = create_access_token(
        {
            "sub": user.id,
            "role": user.role,
            "org_id": org.id,
            "ver": user.token_version,
        }
    )
    csrf = set_auth_cookies(response, request, token)
    return _build_session_response(db, user, org, csrf_token=csrf)


@router.post("/super-admin/login", response_model=SessionResponse)
def super_admin_login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate a Super Admin into the platform management portal."""
    email = req.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(req.password, user.password_hash):
        write_audit_log(
            db,
            action="login_failed",
            details={"email": email, "portal": "super_admin"},
            ip_address=get_client_ip(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin privileges required.",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin account is not active.",
        )

    user.last_login_at = utc_now()
    write_audit_log(
        db,
        action="super_admin_login_success",
        actor_user_id=user.id,
        ip_address=get_client_ip(request),
    )
    db.commit()

    token = create_access_token(
        {
            "sub": user.id,
            "role": user.role,
            "ver": user.token_version,
        }
    )
    csrf = set_auth_cookies(response, request, token)
    return _build_session_response(db, user, None, csrf_token=csrf)


@router.post("/logout")
def logout(request: Request, response: Response):
    if request.cookies.get("sa_session"):
        verify_csrf(request)
    clear_auth_cookies(response, request)
    return {"status": "ok", "message": "Signed out successfully."}


@router.get("/me", response_model=SessionResponse)
def get_me(
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    csrf = request.cookies.get(CSRF_COOKIE_NAME)
    return _build_session_response(
        db=db,
        user=ctx.user,
        org=ctx.organization,
        is_impersonating=ctx.is_impersonating,
        impersonator_user_id=ctx.impersonator_user_id,
        csrf_token=csrf,
    )


@router.post("/setup-account")
def setup_account(
    req: SetupAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Complete account onboarding or password reset via single-use hashed token."""
    token_hash_val = hash_token(req.token.strip())
    record = db.query(AccountSetupToken).filter(AccountSetupToken.token_hash == token_hash_val).first()

    now = utc_now()
    if not record or record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This setup link is invalid or has already been used.",
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        from datetime import timezone
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now >= expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This setup link has expired. Please request a new link from your administrator.",
        )

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    user.password_hash = hash_password(req.new_password)
    if req.name:
        user.name = req.name.strip()
    user.status = "active"
    user.token_version += 1
    record.used_at = now

    write_audit_log(
        db,
        action="account_setup_completed",
        actor_user_id=user.id,
        target_user_id=user.id,
        target_organization_id=user.organization_id,
        ip_address=get_client_ip(request),
    )
    db.commit()

    return {
        "status": "ok",
        "email": user.email,
        "role": user.role,
        "message": "Password configured successfully. You can now sign in.",
    }


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    verify_csrf(request)
    if ctx.is_impersonating:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change a user's password during an impersonation session.",
        )

    if not verify_password(req.current_password, ctx.user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    ctx.user.password_hash = hash_password(req.new_password)
    ctx.user.token_version += 1

    write_audit_log(
        db,
        action="password_changed",
        actor_user_id=ctx.user.id,
        target_user_id=ctx.user.id,
        target_organization_id=ctx.user.organization_id,
        ip_address=get_client_ip(request),
    )
    db.commit()

    payload = {
        "sub": ctx.user.id,
        "role": ctx.user.role,
        "ver": ctx.user.token_version,
    }
    if ctx.user.organization_id:
        payload["org_id"] = ctx.user.organization_id

    new_jwt = create_access_token(payload)
    csrf = set_auth_cookies(response, request, new_jwt)
    return {"status": "ok", "message": "Password updated successfully.", "csrf_token": csrf}

