import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    status = Column(String(50), default="active")  # active, closed, lead_captured
    category = Column(String(50), default="general")  # general, service_enquiry, appointment_enquiry, payment_support

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    enquiries = relationship("Enquiry", back_populates="conversation")

class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)  # JSON-encoded array of {title, url}
    created_at = Column(DateTime, default=utc_now)

    conversation = relationship("Conversation", back_populates="messages")

class Enquiry(Base):
    __tablename__ = "enquiries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
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

    conversation = relationship("Conversation", back_populates="enquiries")

class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # website, pdf, docx, txt
    source_url = Column(String(500), nullable=True)
    chunk_count = Column(Integer, default=0)
    status = Column(String(50), default="processing")  # indexed, processing, error
    created_at = Column(DateTime, default=utc_now)
