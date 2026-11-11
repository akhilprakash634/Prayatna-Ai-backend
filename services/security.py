import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog, Organization, User

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "sa_session"
CSRF_COOKIE_NAME = "csrf_token"
TOKEN_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "720"))  # 12h

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SECRET_FILE = os.path.join(BASE_DIR, "data", ".jwt_secret")
_secret_lock = threading.Lock()
_cached_ephemeral_secret: Optional[str] = None


def _get_jwt_secret() -> str:
    """Resolve JWT signing key from env or persistent CSPRNG secret file (never hardcoded)."""
    global _cached_ephemeral_secret

    env_secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if env_secret:
        return env_secret

    secret_file = os.getenv("JWT_SECRET_FILE", DEFAULT_SECRET_FILE)
    with _secret_lock:
        if os.path.exists(secret_file):
            try:
                with open(secret_file, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if len(val) >= 32:
                    return val
            except Exception as e:
                logger.warning("Could not read JWT secret file %s: %s", secret_file, e)

        generated = secrets.token_hex(32)
        try:
            os.makedirs(os.path.dirname(secret_file), exist_ok=True)
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(generated)
            return generated
        except Exception as e:
            logger.warning("Using ephemeral CSPRNG JWT secret because persisting failed: %s", e)
            if _cached_ephemeral_secret is None:
                _cached_ephemeral_secret = generated
            return _cached_ephemeral_secret


def hash_password(password: str) -> str:
    if not password or not isinstance(password, str):
        raise ValueError("Password cannot be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


def create_access_token(payload: Dict[str, Any], expires_minutes: int = TOKEN_TTL_MINUTES) -> str:
    """Create HS256 JWT token with explicit exp and iat."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        **payload,
        "iat": now,
        "exp": now + (expires_minutes * 60),
        "jti": secrets.token_hex(12),
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(_get_jwt_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and strictly verify an HS256 JWT token (rejects alg=none or invalid signatures)."""
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")

    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header")

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token algorithm")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(_get_jwt_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided_sig = _b64url_decode(sig_b64)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    if not isinstance(payload, dict) or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token payload")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or int(time.time()) >= int(exp):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please sign in again.")

    return payload


def _is_secure_request(request: Request) -> bool:
    if os.getenv("COOKIE_SECURE", "").lower() == "true":
        return True
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto == "https" or request.url.scheme == "https"


def set_auth_cookies(response: Response, request: Request, jwt_token: str) -> str:
    csrf = secrets.token_urlsafe(24)
    secure = _is_secure_request(request)
    max_age = TOKEN_TTL_MINUTES * 60

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=jwt_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age,
    )
    return csrf


def clear_auth_cookies(response: Response, request: Request) -> None:
    secure = _is_secure_request(request)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite="lax", secure=secure)
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/", samesite="lax", secure=secure)


def verify_csrf(request: Request) -> None:
    """Enforce Double-Submit CSRF verification on cookie-authenticated unsafe methods."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    has_session_cookie = bool(request.cookies.get(SESSION_COOKIE_NAME))
    auth_header = request.headers.get("authorization", "")
    # Bearer-only non-browser requests don't carry cookies; cookie requests must match X-CSRF-Token.
    if not has_session_cookie and auth_header.lower().startswith("bearer "):
        return

    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_csrf = request.headers.get("x-csrf-token", "")
    if not cookie_csrf or not header_csrf or not hmac.compare_digest(cookie_csrf, header_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF verification failed. Please refresh and try again.",
        )


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def validate_slug(slug: str) -> str:
    normalized = (slug or "").strip().lower()
    if len(normalized) < 2 or len(normalized) > 64 or not SLUG_PATTERN.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Slug must be 2-64 lowercase alphanumeric characters or hyphens (cannot start or end with a hyphen).",
        )
    return normalized


def validate_hex_color(color: str) -> str:
    val = (color or "").strip()
    if not HEX_COLOR_PATTERN.match(val):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Color must be a 6-digit hex code such as #0d9488.",
        )
    return val.lower()


@dataclass
class AuthContext:
    user: User
    effective_role: str
    organization_id: Optional[str]
    organization: Optional[Organization]
    is_impersonating: bool
    impersonator_user_id: Optional[str]
    payload: Dict[str, Any]


def _extract_token(request: Request) -> Optional[str]:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def get_auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_access_token(token)
    user_id = str(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")

    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    if int(payload.get("ver", -1)) != int(user.token_version):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalidated. Please sign in again.")

    imp_org_id = payload.get("imp_org")
    imp_by = payload.get("imp_by")

    if imp_org_id or imp_by:
        if user.role != "super_admin" or str(imp_by) != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid impersonation claim")
        org = db.query(Organization).filter(Organization.id == str(imp_org_id)).first()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target organization not found")
        return AuthContext(
            user=user,
            effective_role="client_admin",
            organization_id=org.id,
            organization=org,
            is_impersonating=True,
            impersonator_user_id=user.id,
            payload=payload,
        )

    org: Optional[Organization] = None
    if user.organization_id:
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()

    return AuthContext(
        user=user,
        effective_role=user.role,
        organization_id=user.organization_id,
        organization=org,
        is_impersonating=False,
        impersonator_user_id=None,
        payload=payload,
    )


def require_super_admin(request: Request, ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    verify_csrf(request)
    if ctx.user.role != "super_admin" or ctx.is_impersonating:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super Admin access required")
    return ctx


def require_client_admin(request: Request, ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    verify_csrf(request)
    if ctx.is_impersonating:
        if not ctx.organization_id or not ctx.organization:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid impersonated organization")
        return ctx

    if ctx.user.role != "client_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client Admin access required")

    if not ctx.organization_id or not ctx.organization:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not assigned to an organization")

    if ctx.organization.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is suspended. Contact platform support.")

    return ctx


def assert_org_access(resource_org_id: Optional[str], active_org_id: str, resource_name: str = "Resource") -> None:
    """Explicitly reject cross-tenant resource access with HTTP 403."""
    if not resource_org_id or resource_org_id != active_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: {resource_name} does not belong to your organization.",
        )


def write_audit_log(
    db: Session,
    action: str,
    actor_user_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    target_organization_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        target_organization_id=target_organization_id,
        action=action,
        details_json=json.dumps(details) if details else None,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry


class SlidingWindowRateLimiter:
    """Thread-safe in-memory per-key rate limiter for public chat endpoints."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: Optional[int] = None) -> None:
        max_req = limit if limit is not None else self.max_requests
        if max_req <= 0:
            return
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            dq = self._buckets[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_req:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please wait a few seconds before sending more messages.",
                )
            dq.append(now)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


public_chat_rate_limiter = SlidingWindowRateLimiter(
    max_requests=int(os.getenv("PUBLIC_CHAT_RATE_LIMIT", "30")),
    window_seconds=60,
)

