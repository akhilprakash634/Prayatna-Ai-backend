from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
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
    suggested_questions_enabled: bool = True
    enquiry_enabled: bool = True
    enquiry_button_label: str = Field(default="Request Callback", min_length=2, max_length=40)
    widget_position: Literal["right", "left"] = "right"
    launcher_label: Optional[str] = Field(default=None, max_length=32)
    show_powered_by: bool = True

    # 1. Widget Appearance & Launcher Styling
    launcher_style: Literal["default", "custom_image", "animated"] = "default"
    launcher_bg_color: Optional[str] = Field(default=None, max_length=9)
    launcher_icon_color: str = Field(default="#ffffff", max_length=9)
    launcher_size: Literal["small", "medium", "large", "xlarge"] = "medium"
    launcher_shape: Literal["circle", "rounded_square", "pill"] = "circle"

    # 2. Avatar / Character Animation Assets
    avatar_type: Literal["default", "custom_image", "gif", "lottie", "webm"] = "default"
    avatar_url: Optional[str] = Field(default=None, max_length=600)
    avatar_animation_url: Optional[str] = Field(default=None, max_length=600)
    avatar_preset: Optional[str] = Field(default=None, max_length=60)
    character_size: Literal["contain", "large", "overflow"] = "contain"

    # 3. Animation Behavior
    animation_enabled: bool = True
    animation_behavior: Literal["idle", "greeting", "hover", "click", "continuous"] = "continuous"
    reduced_motion: Literal["respect", "force_static", "always_animate"] = "respect"

    # 4. Greeting Tooltip
    greeting_enabled: bool = False
    greeting_text: Optional[str] = Field(default=None, max_length=160)
    greeting_bg_color: str = Field(default="#ffffff", max_length=9)
    greeting_text_color: str = Field(default="#0f172a", max_length=9)
    greeting_delay: int = Field(default=3, ge=0, le=60)
    greeting_auto_hide: int = Field(default=10, ge=0, le=120)

    # 5. Position & Placement Settings
    position_preset: Literal[
        "bottom_right",
        "bottom_right_elevated",
        "middle_right",
        "top_right",
        "bottom_left",
        "custom",
    ] = "bottom_right"
    vertical_position: Literal["bottom", "top", "middle"] = "bottom"
    desktop_top_offset: int = Field(default=24, ge=0, le=300)
    desktop_left_offset: int = Field(default=24, ge=0, le=300)
    desktop_right_offset: int = Field(default=24, ge=0, le=300)
    desktop_bottom_offset: int = Field(default=24, ge=0, le=300)
    desktop_side_offset: int = Field(default=24, ge=0, le=300)

    # Responsive Mobile Configuration
    mobile_position_preset: Literal[
        "bottom_right",
        "bottom_right_elevated",
        "middle_right",
        "top_right",
        "bottom_left",
        "custom",
    ] = "bottom_right"
    mobile_vertical_position: Literal["bottom", "top", "middle"] = "bottom"
    mobile_launcher_size: Literal["small", "medium", "large", "xlarge"] = "medium"
    mobile_position: Literal["right", "left"] = "right"
    mobile_top_offset: int = Field(default=16, ge=0, le=200)
    mobile_left_offset: int = Field(default=16, ge=0, le=200)
    mobile_right_offset: int = Field(default=16, ge=0, le=200)
    mobile_bottom_offset: int = Field(default=16, ge=0, le=200)
    mobile_side_offset: int = Field(default=16, ge=0, le=200)

    # 6. Built-in Character Gallery Selection
    selected_character_id: Optional[str] = Field(default=None, max_length=60)
    selected_character_type: Optional[str] = Field(default=None, max_length=30)
    selected_character_asset: Optional[str] = Field(default=None, max_length=600)
    animation_speed: float = Field(default=1.0, ge=0.25, le=3.0)
    character_settings: Optional[Dict[str, Any]] = None

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

    @field_validator("tagline", "launcher_label", "greeting_text", "avatar_preset", "selected_character_id", "selected_character_type", mode="before")
    @classmethod
    def strip_optional_text(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        val = str(v).strip()
        return val or None

    @field_validator("launcher_bg_color", "launcher_icon_color", "greeting_bg_color", "greeting_text_color", mode="before")
    @classmethod
    def validate_hex_or_none(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        clean = str(v).strip().lower()
        if not clean:
            return None
        import re
        if not re.match(r"^#[0-9a-f]{6}$", clean):
            raise ValueError(f"Color '{v}' must be a valid 6-digit hex string (e.g. #4f46e5).")
        return clean

    @field_validator("avatar_url", "avatar_animation_url", "selected_character_asset", mode="before")
    @classmethod
    def validate_asset_url(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        val = str(v).strip()
        if not val:
            return None
        if val.startswith("/") and not val.startswith("//"):
            return val
        lower = val.lower()
        if lower.startswith("https://") or lower.startswith("http://"):
            return val
        raise ValueError("Asset URL must start with https://, http://, or /.")

    @field_validator("enquiry_button_label", mode="before")
    @classmethod
    def strip_cta_label(cls, v: Any) -> str:
        val = str(v or "").strip()
        return val or "Request Callback"

    @model_validator(mode="after")
    def sync_position_offsets(self):
        # Sync desktop side offsets
        if self.desktop_side_offset != 24:
            if self.widget_position == "left" and self.desktop_left_offset == 24:
                self.desktop_left_offset = self.desktop_side_offset
            elif self.widget_position == "right" and self.desktop_right_offset == 24:
                self.desktop_right_offset = self.desktop_side_offset
        else:
            if self.widget_position == "left":
                self.desktop_side_offset = self.desktop_left_offset
            else:
                self.desktop_side_offset = self.desktop_right_offset

        # Sync mobile side offsets
        if self.mobile_side_offset != 16:
            if self.mobile_position == "left" and self.mobile_left_offset == 16:
                self.mobile_left_offset = self.mobile_side_offset
            elif self.mobile_position == "right" and self.mobile_right_offset == 16:
                self.mobile_right_offset = self.mobile_side_offset
        else:
            if self.mobile_position == "left":
                self.mobile_side_offset = self.mobile_left_offset
            else:
                self.mobile_side_offset = self.mobile_right_offset
        return self


class WidgetAssetUploadResponse(BaseModel):
    url: str
    filename: str
    size: int
    asset_type: str


class WidgetPresetItem(BaseModel):
    id: str
    name: str
    description: str
    type: Literal["lottie", "gif", "image"]
    preview_url: str
    animation_url: str
    category: str


class CharacterAssetResponse(BaseModel):
    id: str
    character_id: str
    name: str
    category: str
    description: str
    preview_image: Optional[str] = None
    animation_url: str
    animation_type: str = "lottie"
    supported_animations: List[str] = Field(default_factory=lambda: ["continuous", "idle", "greeting", "hover", "click"])
    default_size: int = 56
    is_active: bool = True
    display_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CreateCharacterAssetRequest(BaseModel):
    character_id: str = Field(..., min_length=2, max_length=60)
    name: str = Field(..., min_length=2, max_length=100)
    category: str = Field(..., min_length=2, max_length=50)
    description: str = Field(..., min_length=2, max_length=255)
    preview_image: Optional[str] = Field(default=None, max_length=500)
    animation_url: str = Field(..., min_length=1, max_length=500)
    animation_type: Literal["lottie", "gif", "webm"] = "lottie"
    supported_animations: List[str] = Field(default_factory=lambda: ["continuous", "idle", "greeting", "hover", "click"])
    default_size: int = Field(default=56, ge=32, le=128)
    is_active: bool = True
    display_order: int = 0


class UpdateCharacterAssetRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    category: Optional[str] = Field(default=None, min_length=2, max_length=50)
    description: Optional[str] = Field(default=None, min_length=2, max_length=255)
    preview_image: Optional[str] = Field(default=None, max_length=500)
    animation_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    animation_type: Optional[Literal["lottie", "gif", "webm"]] = None
    supported_animations: Optional[List[str]] = None
    default_size: Optional[int] = Field(default=None, ge=32, le=128)
    is_active: Optional[bool] = None
    display_order: Optional[int] = None



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


# ============================================================================
# Agent Studio Schemas
# ============================================================================

class SuggestedQuestionItem(BaseModel):
    id: str
    text: str
    enabled: bool = True


class AgentBehaviourConfig(BaseModel):
    ask_followup_questions: bool = True
    suggest_services: bool = True
    proactive_guidance: bool = True
    collect_customer_info: bool = True
    offer_human_assistance: bool = True
    ask_clarification: bool = True
    avoid_repetition: bool = True
    recommend_services: bool = True
    confirm_before_enquiry: bool = True
    escalate_issues: bool = True
    fallback_action: str = Field("acknowledge", pattern="^(acknowledge|offer_human|collect_details|suggest_contact)$")
    custom_behaviour_instructions: Optional[str] = None


class AgentWelcomeConfig(BaseModel):
    welcome_message: str = "Hello! Welcome to our support desk. How can I help you today?"
    agent_intro: str = "I'm your virtual assistant."
    greeting_style: str = Field("Friendly", pattern="^(Friendly|Professional|Casual|Personalized)$")
    initial_behaviour: str = Field(
        "welcome_and_suggestions",
        pattern="^(welcome_only|welcome_and_suggestions|ask_assistance|predefined_question)$",
    )
    predefined_question: Optional[str] = None
    suggested_questions_enabled: bool = True
    suggested_questions: List[SuggestedQuestionItem] = Field(default_factory=list)


class AgentResponseConfig(BaseModel):
    custom_response_instructions: Optional[str] = None
    max_response_length: str = Field("standard", pattern="^(concise|standard|detailed|short|balanced)$")
    prioritize_org_knowledge: bool = True
    dont_invent_info: bool = True
    display_sources: bool = True
    acknowledge_unavailable: bool = True
    followup_strategy: str = Field(
        "one_at_a_time",
        pattern="^(one_at_a_time|multiple_together|avoid_unnecessary|confirm_before_enquiry)$",
    )
    fallback_message: str = "I'm sorry, I don't have that information at the moment. Would you like me to connect you with our team?"


class ConversationFlowStep(BaseModel):
    id: str
    title: str
    description: str
    step_type: str = "step"
    enabled: bool = True


class ConversationFlowConfig(BaseModel):
    enable_welcome: bool = True
    enable_requirement_triage: bool = True
    enable_service_explanation: bool = True
    enable_detail_collection: bool = True
    enable_enquiry_creation: bool = True
    enable_human_escalation: bool = True
    completion_message: Optional[str] = "Thank you! Our team has received your enquiry and will get in touch shortly."
    steps: List[ConversationFlowStep] = Field(default_factory=list)


class AgentSettingsResponse(BaseModel):
    id: str
    organization_id: str
    agent_name: str
    agent_role: str
    agent_description: str
    organization_name: str
    primary_responsibility: Optional[str] = None
    personality: List[str]
    tone: str
    attitude: str
    response_length: str
    communication_style: str
    formality: str
    emoji_usage: str
    language_preference: str
    custom_instructions: Optional[str] = None
    behaviour_config: AgentBehaviourConfig
    welcome_config: AgentWelcomeConfig
    response_config: AgentResponseConfig
    is_active: bool
    has_draft_changes: bool = False
    last_activated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("last_activated_at", "created_at", "updated_at")
    def serialize_agent_dates(self, v: Optional[datetime]):
        return _serialize_utc(v)


class AgentSettingsUpdate(BaseModel):
    agent_name: Optional[str] = Field(None, min_length=1, max_length=120)
    agent_role: Optional[str] = Field(None, min_length=1, max_length=150)
    agent_description: Optional[str] = Field(None, min_length=1, max_length=2000)
    organization_name: Optional[str] = Field(None, min_length=1, max_length=200)
    primary_responsibility: Optional[str] = Field(None, max_length=500)
    personality: Optional[List[str]] = None
    tone: Optional[str] = None
    attitude: Optional[str] = None
    response_length: Optional[str] = Field(None, pattern="^(short|balanced|detailed|concise|standard)$")
    communication_style: Optional[str] = None
    formality: Optional[str] = Field(None, pattern="^(casual|semi-formal|formal)$")
    emoji_usage: Optional[str] = Field(None, pattern="^(disabled|minimal|moderate)$")
    language_preference: Optional[str] = None
    custom_instructions: Optional[str] = None
    behaviour_config: Optional[AgentBehaviourConfig] = None
    welcome_config: Optional[AgentWelcomeConfig] = None
    response_config: Optional[AgentResponseConfig] = None


class AgentPreviewRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    language: Optional[str] = "Auto"
    draft_settings: Optional[AgentSettingsUpdate] = None


class AgentPreviewResponse(BaseModel):
    message: str
    intent: str
    sources: List[SourceCitation] = []
    requires_followup: bool = False
    suggested_queries: List[str] = []
    language: str = "English"


class ConversationFlowResponse(BaseModel):
    id: str
    organization_id: str
    flow_name: str
    flow_type: str
    flow_config: ConversationFlowConfig
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_flow_dates(self, v: datetime):
        return _serialize_utc(v)


class ConversationFlowCreate(BaseModel):
    flow_name: str = Field(..., min_length=2, max_length=120)
    flow_type: str = Field("default", min_length=2, max_length=50)
    flow_config: ConversationFlowConfig
    is_active: bool = True


class ConversationFlowUpdate(BaseModel):
    flow_name: Optional[str] = Field(None, min_length=2, max_length=120)
    flow_type: Optional[str] = Field(None, min_length=2, max_length=50)
    flow_config: Optional[ConversationFlowConfig] = None
    is_active: Optional[bool] = None
