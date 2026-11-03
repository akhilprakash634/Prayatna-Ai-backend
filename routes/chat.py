import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import Conversation, Message, Enquiry
from schemas import ChatRequest, ChatResponse, SourceCitation
from services.rag import rag_service
from services.gemini import gemini_service, extract_lead_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
def handle_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")

    # 1. Retrieve or create conversation
    conversation = None
    if payload.conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()

    if not conversation:
        conversation = Conversation()
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # 2. Retrieve recent conversation history
    past_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history_dicts = [{"role": m.role, "content": m.content} for m in past_messages]

    language = (payload.language or "English").strip()

    # 3. Retrieve relevant knowledge chunks from ChromaDB
    retrieved_chunks = rag_service.query(message_text, top_k=5)
    
    # 4. Generate AI response
    ai_response_text, intent, requires_followup = gemini_service.generate_chat_response(
        user_message=message_text,
        retrieved_chunks=retrieved_chunks,
        conversation_history=history_dicts,
        language=language
    )

    # Update conversation category if not already specialized
    if conversation.category in ("general", None) and intent != "general":
        conversation.category = intent

    # 5. Extract unique sources for frontend citations
    seen_urls = set()
    sources_list = []
    for chunk in retrieved_chunks:
        url = chunk.get("url") or "https://prayatna.co.in/"
        title = chunk.get("title") or "Prayatna Resource"
        if url not in seen_urls:
            seen_urls.add(url)
            sources_list.append(SourceCitation(title=title, url=url))

    # 6. Save customer message to DB
    user_msg_record = Message(
        conversation_id=conversation.id,
        role="user",
        content=message_text,
        sources_json=None
    )
    db.add(user_msg_record)

    # 7. Check for conversational lead capture
    enquiry_data = None
    lead_info = extract_lead_info(message_text, history_dicts)
    if lead_info["phone"] or lead_info["email"]:
        # If the user shared phone/email, we can register or link an enquiry
        existing_enquiry = db.query(Enquiry).filter(Enquiry.conversation_id == conversation.id).first()
        if not existing_enquiry:
            # Create preliminary enquiry record
            cat = "payment_support" if intent == "payment_support" else "appointment"
            enquiry = Enquiry(
                conversation_id=conversation.id,
                parent_name=lead_info.get("parent_name") or "Website Visitor",
                email=lead_info.get("email") or "Not provided",
                phone=lead_info.get("phone") or "Not provided",
                child_age=lead_info.get("child_age"),
                interested_service=conversation.category.replace("_", " ").title(),
                category=cat,
                description=f"Enquiry initiated via chat: '{message_text[:200]}'",
                preferred_contact="phone" if lead_info.get("phone") else "email",
                status="New"
            )
            db.add(enquiry)
            db.commit()
            db.refresh(enquiry)
            enquiry_data = {
                "id": enquiry.id,
                "parent_name": enquiry.parent_name,
                "phone": enquiry.phone,
                "email": enquiry.email,
                "category": enquiry.category,
                "status": enquiry.status
            }
            conversation.status = "lead_captured"

    # 8. Save AI response to DB
    sources_json_str = json.dumps([s.model_dump() for s in sources_list])
    assistant_msg_record = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=ai_response_text,
        sources_json=sources_json_str
    )
    db.add(assistant_msg_record)

    db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        message=ai_response_text,
        sources=sources_list,
        intent=intent,
        requires_followup=requires_followup,
        enquiry_captured=enquiry_data,
        language=language
    )
