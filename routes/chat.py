import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import Conversation, Enquiry, Message, utc_now
from schemas import ChatRequest, ChatResponse, PublicChatbotConfig, SourceCitation
from services.gemini import detect_intent, extract_lead_info, gemini_service, generate_suggested_queries
from services.rag import rag_service
from services.security import assert_org_access, get_client_ip, public_chat_rate_limiter
from services.tenant import (
    enforce_subscription_limits,
    get_public_chatbot_metadata,
    record_usage,
    resolve_public_chatbot,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _build_sources(retrieved_chunks: List[Dict[str, Any]], org_name: str, org_website: Optional[str]) -> List[Dict[str, str]]:
    seen_keys = set()
    sources: List[Dict[str, str]] = []
    default_url = org_website or ""
    default_title = f"{org_name} Resource"

    for chunk in retrieved_chunks:
        url = chunk.get("url") or default_url
        title = chunk.get("title") or default_title
        key = f"{title}::{url}"
        if key not in seen_keys:
            seen_keys.add(key)
            sources.append({"title": title, "url": url})
    return sources


def _capture_or_update_enquiry(
    db: Session,
    organization_id: str,
    conversation_id: str,
    conversation_category: Optional[str],
    message_text: str,
    history_dicts: List[Dict[str, str]],
    intent: str,
    source_label: str = "chat",
) -> Optional[Dict[str, Any]]:
    lead_info = extract_lead_info(message=message_text, history=history_dicts)
    if not (lead_info.get("phone") or lead_info.get("email")):
        return None

    existing_enquiry = (
        db.query(Enquiry)
        .filter(Enquiry.conversation_id == conversation_id, Enquiry.organization_id == organization_id)
        .first()
    )

    service_name = lead_info.get("interested_service")
    if not service_name or service_name == "General Consultation":
        if conversation_category and conversation_category not in ("general", None):
            service_name = conversation_category.replace("_", " ").title()
        else:
            service_name = "General Enquiry"

    cat = "payment_support" if intent == "payment_support" else "appointment"

    if not existing_enquiry:
        existing_enquiry = Enquiry(
            organization_id=organization_id,
            conversation_id=conversation_id,
            parent_name=lead_info.get("parent_name") or "Website Visitor",
            email=lead_info.get("email") or "Not provided",
            phone=lead_info.get("phone") or "Not provided",
            child_age=lead_info.get("child_age"),
            interested_service=service_name,
            category=cat,
            description=f"Enquiry from {source_label}: '{message_text[:200]}'",
            preferred_contact="phone" if lead_info.get("phone") else "email",
            status="New",
        )
        db.add(existing_enquiry)
        db.commit()
        db.refresh(existing_enquiry)
    else:
        if lead_info.get("parent_name") and existing_enquiry.parent_name in ("Website Visitor", "Parent / Visitor", ""):
            existing_enquiry.parent_name = lead_info["parent_name"]
        if lead_info.get("child_age") and not existing_enquiry.child_age:
            existing_enquiry.child_age = lead_info["child_age"]
        if service_name and existing_enquiry.interested_service in (
            "General Consultation",
            "Comprehensive Developmental Assessment",
            "General Enquiry",
            "",
        ):
            existing_enquiry.interested_service = service_name
        if lead_info.get("phone") and existing_enquiry.phone in ("Not provided", ""):
            existing_enquiry.phone = lead_info["phone"]
        if lead_info.get("email") and existing_enquiry.email in ("Not provided", ""):
            existing_enquiry.email = lead_info["email"]
        existing_enquiry.description = f"{existing_enquiry.description}\nFollow-up: '{message_text[:200]}'"
        db.commit()
        db.refresh(existing_enquiry)

    return {
        "id": existing_enquiry.id,
        "parent_name": existing_enquiry.parent_name,
        "phone": existing_enquiry.phone,
        "email": existing_enquiry.email,
        "child_age": existing_enquiry.child_age,
        "interested_service": existing_enquiry.interested_service,
        "category": existing_enquiry.category,
        "status": existing_enquiry.status,
    }


@router.get("/config", response_model=PublicChatbotConfig)
def get_public_chatbot_config(
    bot: Optional[str] = Query(None, description="Unique chatbot identifier"),
    db: Session = Depends(get_db),
):
    """Public endpoint returning chatbot branding & availability status."""
    return PublicChatbotConfig(**get_public_chatbot_metadata(db, bot))


@router.post("", response_model=ChatResponse)
def handle_chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")

    public_chat_rate_limiter.check(f"chat:{get_client_ip(request)}:{payload.chatbot_id or 'default'}")
    org, setting = resolve_public_chatbot(db, payload.chatbot_id)

    conversation = None
    if payload.conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()
        if conversation:
            assert_org_access(conversation.organization_id, org.id, "Conversation")

    is_new_conversation = conversation is None
    enforce_subscription_limits(db, org.id, is_new_conversation=is_new_conversation)

    if is_new_conversation:
        conversation = Conversation(organization_id=org.id, chatbot_id=setting.chatbot_id)
        db.add(conversation)
        db.flush()
        record_usage(db, org.id, "conversation", 1, {"chatbot_id": setting.chatbot_id})
        db.commit()
        db.refresh(conversation)

    past_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id, Message.organization_id == org.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history_dicts = [{"role": m.role, "content": m.content} for m in past_messages]
    language = (payload.language or "English").strip()

    retrieved_chunks = rag_service.query(
        message_text,
        top_k=5,
        org_slug=org.slug,
        collection_name=setting.knowledge_collection,
    )

    ai_response_text, intent, requires_followup = gemini_service.generate_chat_response(
        user_message=message_text,
        retrieved_chunks=retrieved_chunks,
        conversation_history=history_dicts,
        language=language,
        organization_name=org.name,
        organization_slug=org.slug,
        assistant_name=setting.assistant_name,
        custom_instructions=setting.custom_instructions,
    )

    if conversation.category in ("general", None) and intent != "general":
        conversation.category = intent

    raw_sources = _build_sources(retrieved_chunks, org.name, org.website)
    sources_list = [SourceCitation(**s) for s in raw_sources]

    user_msg_record = Message(
        organization_id=org.id,
        conversation_id=conversation.id,
        role="user",
        content=message_text,
        sources_json=None,
    )
    db.add(user_msg_record)

    enquiry_data = _capture_or_update_enquiry(
        db=db,
        organization_id=org.id,
        conversation_id=conversation.id,
        conversation_category=conversation.category,
        message_text=message_text,
        history_dicts=history_dicts,
        intent=intent,
        source_label="chat",
    )
    if enquiry_data:
        conversation.status = "lead_captured"

    assistant_msg_record = Message(
        organization_id=org.id,
        conversation_id=conversation.id,
        role="assistant",
        content=ai_response_text,
        sources_json=json.dumps(raw_sources),
    )
    db.add(assistant_msg_record)
    conversation.updated_at = utc_now()
    record_usage(db, org.id, "ai_request", 1, {"conversation_id": conversation.id})
    db.commit()

    suggested_queries = generate_suggested_queries(intent, language, organization_name=org.name)

    return ChatResponse(
        conversation_id=conversation.id,
        message=ai_response_text,
        sources=sources_list,
        intent=intent,
        requires_followup=requires_followup,
        enquiry_captured=enquiry_data,
        language=language,
        suggested_queries=suggested_queries,
    )


@router.post("/stream")
def handle_chat_stream(payload: ChatRequest, request: Request):
    """Streams assistant responses token-by-token via SSE scoped to the target chatbot organization."""
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")

    public_chat_rate_limiter.check(f"chat:{get_client_ip(request)}:{payload.chatbot_id or 'default'}")

    db = SessionLocal()
    try:
        org, setting = resolve_public_chatbot(db, payload.chatbot_id)

        conversation = None
        if payload.conversation_id:
            conversation = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()
            if conversation:
                assert_org_access(conversation.organization_id, org.id, "Conversation")

        is_new_conversation = conversation is None
        enforce_subscription_limits(db, org.id, is_new_conversation=is_new_conversation)

        if is_new_conversation:
            conversation = Conversation(organization_id=org.id, chatbot_id=setting.chatbot_id)
            db.add(conversation)
            db.flush()
            record_usage(db, org.id, "conversation", 1, {"chatbot_id": setting.chatbot_id})
            db.commit()
            db.refresh(conversation)

        past_messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id, Message.organization_id == org.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        history_dicts = [{"role": m.role, "content": m.content} for m in past_messages]
        language = (payload.language or "English").strip()

        retrieved_chunks = rag_service.query(
            message_text,
            top_k=3,
            org_slug=org.slug,
            collection_name=setting.knowledge_collection,
        )
        intent = detect_intent(message_text)
        requires_followup = intent in ("appointment_enquiry", "payment_support")

        sources_list = _build_sources(retrieved_chunks, org.name, org.website)

        user_msg = Message(
            organization_id=org.id,
            conversation_id=conversation.id,
            role="user",
            content=message_text,
        )
        db.add(user_msg)
        db.commit()

        conv_id = conversation.id
        conv_category = conversation.category
        org_id = org.id
        org_name = org.name
        org_slug = org.slug
        assistant_name = setting.assistant_name
        custom_instructions = setting.custom_instructions
    finally:
        db.close()

    def stream_generator():
        assembled_chunks = []
        stream_db = SessionLocal()
        try:
            init_payload = json.dumps(
                {
                    "type": "init",
                    "conversation_id": conv_id,
                    "sources": sources_list,
                    "intent": intent,
                    "requires_followup": requires_followup,
                    "language": language,
                }
            )
            yield f"data: {init_payload}\n\n"

            for token in gemini_service.generate_chat_response_stream(
                user_message=message_text,
                retrieved_chunks=retrieved_chunks,
                conversation_history=history_dicts,
                language=language,
                organization_name=org_name,
                organization_slug=org_slug,
                assistant_name=assistant_name,
                custom_instructions=custom_instructions,
            ):
                assembled_chunks.append(token)
                chunk_payload = json.dumps({"type": "chunk", "text": token})
                yield f"data: {chunk_payload}\n\n"

            full_text = "".join(assembled_chunks)

            enquiry_data = None
            try:
                enquiry_data = _capture_or_update_enquiry(
                    db=stream_db,
                    organization_id=org_id,
                    conversation_id=conv_id,
                    conversation_category=conv_category,
                    message_text=message_text,
                    history_dicts=history_dicts,
                    intent=intent,
                    source_label="streaming chat",
                )
            except Exception as e_lead:
                logger.warning("Error extracting lead info in stream: %s", e_lead)

            assistant_msg = Message(
                organization_id=org_id,
                conversation_id=conv_id,
                role="assistant",
                content=full_text,
                sources_json=json.dumps(sources_list),
            )
            stream_db.add(assistant_msg)

            conv_record = stream_db.query(Conversation).filter(Conversation.id == conv_id).first()
            if conv_record:
                conv_record.updated_at = utc_now()
                if conv_record.category in ("general", None) and intent != "general":
                    conv_record.category = intent
                if enquiry_data:
                    conv_record.status = "lead_captured"

            record_usage(stream_db, org_id, "ai_request", 1, {"conversation_id": conv_id})
            stream_db.commit()

            suggested_queries = generate_suggested_queries(intent, language, organization_name=org_name)
            done_payload = json.dumps(
                {
                    "type": "done",
                    "conversation_id": conv_id,
                    "sources": sources_list,
                    "intent": intent,
                    "requires_followup": requires_followup,
                    "enquiry_captured": enquiry_data,
                    "language": language,
                    "suggested_queries": suggested_queries,
                }
            )
            yield f"data: {done_payload}\n\n"

        except Exception as err:
            logger.error("Error in stream_generator: %s", err)
            err_payload = json.dumps(
                {"type": "error", "message": "Unable to complete response stream. Please try again."}
            )
            yield f"data: {err_payload}\n\n"
        finally:
            stream_db.close()

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
