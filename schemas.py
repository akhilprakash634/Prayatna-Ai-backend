from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Source metadata schema
class SourceCitation(BaseModel):
    title: str
    url: str

# Chat Schemas
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field("English", description="Preferred response language")

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

    class Config:
        from_attributes = True

class ConversationDetail(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: str
    category: str
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True

# Enquiry Schemas
class EnquiryCreate(BaseModel):
    conversation_id: Optional[str] = None
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

    class Config:
        from_attributes = True

# Knowledge Schemas
class ScrapeRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=500)

class KnowledgeDocumentResponse(BaseModel):
    id: str
    filename: str
    source_type: str
    source_url: Optional[str] = None
    chunk_count: int
    status: str
    created_at: datetime

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
