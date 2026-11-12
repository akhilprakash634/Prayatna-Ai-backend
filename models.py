import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(200), nullable=False)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(500), nullable=True)
    industry = Column(String(120), nullable=True)
    logo_url = Column(String(500), nullable=True)
    status = Column(String(30), nullable=False, default="active", index=True)  # active, suspended
    plan = Column(String(50), nullable=False, default="Basic")  # Basic, Professional, Enterprise
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    chatbot_setting = relationship("ChatbotSetting", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="organization", cascade="all, delete-orphan")
    enquiries = relationship("Enquiry", back_populates="organization", cascade="all, delete-orphan")
    knowledge_documents = relationship("KnowledgeDocument", back_populates="organization", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(120), nullable=False)
    email = Column(String(200), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, index=True)  # super_admin, client_admin
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="active")  # active, invited, suspended
    token_version = Column(Integer, nullable=False, default=1)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    organization = relationship("Organization", back_populates="users")
    setup_tokens = relationship("AccountSetupToken", back_populates="user", cascade="all, delete-orphan")


class AccountSetupToken(Base):
    __tablename__ = "account_setup_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="setup_tokens")


class ChatbotSetting(Base):
    __tablename__ = "chatbot_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    chatbot_id = Column(String(100), nullable=False, unique=True, index=True)
    bot_name = Column(String(150), nullable=False, default="Support Assistant")
    assistant_name = Column(String(100), nullable=False, default="AI Assistant")
    welcome_message = Column(Text, nullable=False, default="Hello! How can I help you today?")
    primary_color = Column(String(20), nullable=False, default="#0d9488")
    logo_url = Column(String(500), nullable=True)
    custom_instructions = Column(Text, nullable=True)
    theme_config_json = Column(Text, nullable=True)
    knowledge_collection = Column(String(120), nullable=False, default="default_knowledge")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    organization = relationship("Organization", back_populates="chatbot_setting")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan_name = Column(String(50), nullable=False, default="Basic")  # Basic, Professional, Enterprise
    monthly_price = Column(Integer, nullable=False, default=999)
    status = Column(String(30), nullable=False, default="active")  # active, suspended, expired
    start_date = Column(DateTime, default=utc_now)
    renewal_date = Column(DateTime, nullable=False)
    conversation_limit = Column(Integer, nullable=False, default=200)
    ai_usage_limit = Column(Integer, nullable=False, default=2000)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    organization = relationship("Organization", back_populates="subscription")


class UsageLog(Base):
    __tablename__ = "usage_logs"
    __table_args__ = (
        Index("ix_usage_logs_org_type_created", "organization_id", "event_type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # conversation, ai_request, document_upload, website_scrape
    quantity = Column(Integer, nullable=False, default=1)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=False, default=0.0)
    model_name = Column(String(100), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, index=True)

    organization = relationship("Organization", back_populates="usage_logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    details_json = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, index=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    chatbot_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    status = Column(String(50), default="active")  # active, closed, lead_captured
    category = Column(String(50), default="general")  # general, service_enquiry, appointment_enquiry, payment_support

    organization = relationship("Organization", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    enquiries = relationship("Enquiry", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)  # JSON-encoded array of {title, url}
    created_at = Column(DateTime, default=utc_now)

    conversation = relationship("Conversation", back_populates="messages")


class Enquiry(Base):
    __tablename__ = "enquiries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=False)
    phone = Column(String(50), nullable=False)
    child_age = Column(String(50), nullable=True)
    interested_service = Column(String(100), nullable=False)
    category = Column(String(50), default="appointment")  # appointment, therapy_service, payment_support, general
    description = Column(Text, nullable=False)
    preferred_contact = Column(String(50), default="phone")  # phone, email, whatsapp
    status = Column(String(50), default="New")  # New, Contacted, Resolved, Closed
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="enquiries")
    conversation = relationship("Conversation", back_populates="enquiries")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # website, pdf, docx, txt
    source_url = Column(String(500), nullable=True)
    chunk_count = Column(Integer, default=0)
    status = Column(String(50), default="processing")  # indexed, processing, error
    created_at = Column(DateTime, default=utc_now)

    organization = relationship("Organization", back_populates="knowledge_documents")
