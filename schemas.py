from pydantic import BaseModel, Field, field_serializer, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone

def _serialize_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

# Source metadata schema
class SourceCitation(BaseModel):
    title: str
    url: str

# Chat Schemas
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    chatbot_id: Optional[str] = Field(None, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field("Auto", description="Preferred response language")

class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    sources: List[SourceCitation] = []
    intent: str = "general"
    requires_followup: bool = False
    enquiry_captured: Optional[Dict[str, Any]] = None
    language: str = "English"
    suggested_queries: List[str] = Field(default_factory=list)

# Message Schema
class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    sources_json: Optional[str] = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True

# Conversation Schemas
class ConversationSummary(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: str
    category: str
    message_count: int = 0
    customer_name: Optional[str] = None

    @field_serializer("created_at", "updated_at")
    def serialize_dates(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True

class ConversationDetail(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: str
    category: str
    messages: List[MessageResponse] = []

    @field_serializer("created_at", "updated_at")
    def serialize_dates(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True

# Enquiry Schemas
class EnquiryCreate(BaseModel):
    conversation_id: Optional[str] = None
    chatbot_id: Optional[str] = Field(None, max_length=100)
    parent_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=120)
    phone: str = Field(..., min_length=6, max_length=50)
    child_age: Optional[str] = None
    interested_service: str = Field(..., min_length=2, max_length=100)
    category: str = Field("appointment", max_length=50)
    description: str = Field(..., min_length=2, max_length=2000)
    preferred_contact: str = Field("phone", max_length=50)

class EnquiryUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(New|Contacted|Resolved|Closed)$")
    category: Optional[str] = None
    description: Optional[str] = None

class EnquiryResponse(BaseModel):
    id: str
    conversation_id: Optional[str] = None
    parent_name: str
    email: str
    phone: str
    child_age: Optional[str] = None
    interested_service: str
    category: str
    description: str
    preferred_contact: str
    status: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True

# Knowledge Schemas
class ScrapeRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=500)

class TextKnowledgeRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    content: str = Field(..., min_length=20, max_length=200000)
    source_url: Optional[str] = Field(None, max_length=500)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            raise ValueError("Source URL must start with http:// or https://")
        return cleaned

class KnowledgeDocumentResponse(BaseModel):
    id: str
    filename: str
    source_type: str
    source_url: Optional[str] = None
    chunk_count: int
    status: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True

class KnowledgeTestRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)

class KnowledgeTestResult(BaseModel):
    content: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = {}

class KnowledgeTestResponse(BaseModel):
    query: str
    total_results: int
    results: List[KnowledgeTestResult]

# Dashboard Schemas
class DashboardStats(BaseModel):
    total_conversations: int
    total_enquiries: int
    appointment_enquiries: int
    payment_support_requests: int
    unresolved_conversations: int

class ActivityItem(BaseModel):
    id: str
    type: str  # conversation, enquiry, document
    title: str
    subtitle: str
    timestamp: datetime
    status: Optional[str] = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime):
        return _serialize_utc(v)


# -------------------- Multi-Tenant SaaS Schemas --------------------

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)


class SetupAccountRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=300)
    new_password: str = Field(..., min_length=8, max_length=128)
    name: Optional[str] = Field(None, min_length=2, max_length=120)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=128)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)


class AuthUserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    organization_id: Optional[str] = None
    status: str


class OrganizationBrief(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    plan: str
    chatbot_id: Optional[str] = None


class SessionResponse(BaseModel):
    user: AuthUserResponse
    organization: Optional[OrganizationBrief] = None
    is_impersonating: bool = False
    impersonator_user_id: Optional[str] = None
    csrf_token: Optional[str] = None


class ChatbotThemeConfig(BaseModel):
    theme_mode: Literal["light", "soft", "dark"] = "light"
    header_style: Literal["clean", "solid", "gradient"] = "clean"
    border_radius: Literal["rounded", "pill", "sharp"] = "rounded"
    font_family: Literal["inter", "plus_jakarta", "dm_sans", "system"] = "inter"
    tagline: Optional[str] = Field(default=None, max_length=120)
    starter_prompts: List[str] = Field(default_factory=list)
    enquiry_enabled: bool = True
    enquiry_button_label: str = Field(default="Request Callback", min_length=2, max_length=40)
    widget_position: Literal["right", "left"] = "right"
    launcher_label: Optional[str] = Field(default=None, max_length=32)
    show_powered_by: bool = True

    @field_validator("starter_prompts", mode="before")
    @classmethod
    def normalize_starter_prompts(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("starter_prompts must be a list of strings.")
        cleaned: List[str] = []
        for item in v:
            text = str(item or "").strip()
            if text:
                cleaned.append(text[:120])
            if len(cleaned) >= 6:
                break
        return cleaned

    @field_validator("tagline", "launcher_label", mode="before")
    @classmethod
    def strip_optional_text(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        val = str(v).strip()
        return val or None

    @field_validator("enquiry_button_label", mode="before")
    @classmethod
    def strip_cta_label(cls, v: Any) -> str:
        val = str(v or "").strip()
        return val or "Request Callback"


class PublicChatbotConfig(BaseModel):
    chatbot_id: str
    organization_name: str
    organization_slug: str
    bot_name: str
    assistant_name: str
    welcome_message: str
    primary_color: str
    logo_url: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    is_available: bool
    unavailable_reason: Optional[str] = None
    theme_config: ChatbotThemeConfig = Field(default_factory=ChatbotThemeConfig)


class ChatbotConfigResponse(BaseModel):
    id: str
    organization_id: str
    chatbot_id: str
    bot_name: str
    assistant_name: str
    welcome_message: str
    primary_color: str
    logo_url: Optional[str] = None
    custom_instructions: Optional[str] = None
    knowledge_collection: str
    is_active: bool
    organization_name: str
    organization_slug: str
    organization_status: str
    theme_config: ChatbotThemeConfig = Field(default_factory=ChatbotThemeConfig)


class ChatbotConfigUpdate(BaseModel):
    bot_name: Optional[str] = Field(None, min_length=2, max_length=150)
    assistant_name: Optional[str] = Field(None, min_length=2, max_length=100)
    welcome_message: Optional[str] = Field(None, min_length=2, max_length=2000)
    primary_color: Optional[str] = Field(None, max_length=20)
    logo_url: Optional[str] = Field(None, max_length=500)
    custom_instructions: Optional[str] = Field(None, max_length=4000)
    is_active: Optional[bool] = None
    theme_config: Optional[ChatbotThemeConfig] = None


class SubscriptionResponse(BaseModel):
    id: str
    organization_id: str
    plan_name: str
    monthly_price: int
    status: str
    start_date: datetime
    renewal_date: datetime
    conversation_limit: int
    ai_usage_limit: int

    @field_serializer("start_date", "renewal_date")
    def serialize_sub_dates(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True


class SubscriptionUpdateRequest(BaseModel):
    plan_name: str = Field(..., pattern="^(Basic|Professional|Enterprise)$")
    monthly_price: Optional[int] = Field(None, ge=0, le=1000000)
    status: Optional[str] = Field(None, pattern="^(active|suspended|expired)$")
    conversation_limit: Optional[int] = Field(None, ge=1, le=10000000)
    ai_usage_limit: Optional[int] = Field(None, ge=1, le=100000000)
    renewal_days: Optional[int] = Field(None, ge=1, le=3650)


class UsageSummaryResponse(BaseModel):
    cycle_conversations: int
    cycle_ai_requests: int
    cycle_document_uploads: int
    cycle_website_scrapes: int
    total_conversations: int
    total_enquiries: int
    total_documents: int
    total_ai_requests: int
    conversation_limit: int
    ai_usage_limit: int
    cycle_input_tokens: int = 0
    cycle_output_tokens: int = 0
    cycle_total_tokens: int = 0
    cycle_estimated_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    last_model_used: Optional[str] = None


class OrganizationCreateRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=200)
    organization_slug: str = Field(..., min_length=2, max_length=64)
    admin_name: str = Field(..., min_length=2, max_length=120)
    admin_email: str = Field(..., min_length=5, max_length=200)
    admin_password: Optional[str] = Field(None, min_length=8, max_length=128)
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)
    industry: Optional[str] = Field(None, max_length=120)
    subscription_plan: str = Field("Basic", pattern="^(Basic|Professional|Enterprise)$")
    account_status: str = Field("active", pattern="^(active|suspended)$")


class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)
    industry: Optional[str] = Field(None, max_length=120)
    logo_url: Optional[str] = Field(None, max_length=500)


class AdminUserBrief(BaseModel):
    id: str
    name: str
    email: str
    status: str
    last_login_at: Optional[datetime] = None

    @field_serializer("last_login_at")
    def serialize_last_login(self, v: Optional[datetime]):
        return _serialize_utc(v)


class OrganizationSummary(BaseModel):
    id: str
    name: str
    slug: str
    phone: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    status: str
    plan: str
    chatbot_id: Optional[str] = None
    admin_email: Optional[str] = None
    total_conversations: int = 0
    total_enquiries: int = 0
    total_ai_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created(self, v: datetime):
        return _serialize_utc(v)


class OrganizationDetailResponse(BaseModel):
    id: str
    name: str
    slug: str
    phone: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    logo_url: Optional[str] = None
    status: str
    plan: str
    created_at: datetime
    updated_at: datetime
    admins: List[AdminUserBrief] = []
    chatbot: Optional[ChatbotConfigResponse] = None
    subscription: Optional[SubscriptionResponse] = None
    usage: UsageSummaryResponse

    @field_serializer("created_at", "updated_at")
    def serialize_org_dates(self, v: datetime):
        return _serialize_utc(v)


class CreateClientResponse(BaseModel):
    organization: OrganizationDetailResponse
    setup_link: str
    setup_token_expires_hours: int = 24
    embed_snippet: str
    direct_chat_path: str


class ResetCredentialsRequest(BaseModel):
    new_password: Optional[str] = Field(None, min_length=8, max_length=128)


class ResetCredentialsResponse(BaseModel):
    user_id: str
    email: str
    setup_link: str
    password_updated: bool
    message: str


class DeleteOrganizationRequest(BaseModel):
    confirm_slug: str = Field(..., min_length=2, max_length=64)
    force: bool = False


class SuperAdminDashboardStats(BaseModel):
    total_organizations: int
    active_organizations: int
    suspended_organizations: int
    total_conversations: int
    total_enquiries: int
    total_ai_requests: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    target_user_id: Optional[str] = None
    target_organization_id: Optional[str] = None
    action: str
    details_json: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_audit_created(self, v: datetime):
        return _serialize_utc(v)

    class Config:
        from_attributes = True
