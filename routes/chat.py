import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import AgentSetting, ChatbotSetting, Conversation, ConversationFlow, Enquiry, Message, Organization, utc_now
from schemas import ChatRequest, ChatResponse, PublicChatbotConfig, SourceCitation
from services.gemini import detect_intent, extract_lead_info, gemini_service, generate_suggested_queries
from services.rag import rag_service
from services.security import assert_org_access, get_client_ip, public_chat_rate_limiter
from services.tenant import (
    enforce_subscription_limits,
    get_public_chatbot_metadata,
    record_usage,
    resolve_chatbot_theme_config,
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


def _resolve_tenant_for_chat(
    db: Session,
    chatbot_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Tuple[Organization, ChatbotSetting]:
    """
    Resolve organization and chatbot setting for a chat request.
    Prioritizes explicit chatbot_id through resolve_public_chatbot (enforcing active/suspension checks),
    falls back to conversation's owner organization if chatbot_id is omitted, and finally default chatbot.
    """
    clean_bot_id = (chatbot_id or "").strip()
    if clean_bot_id:
        return resolve_public_chatbot(db, clean_bot_id)

    if conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == conv.organization_id).first()
            if setting and setting.chatbot_id:
                return resolve_public_chatbot(db, setting.chatbot_id)

    return resolve_public_chatbot(db, None)


def _get_captured_contact_info(
    db: Session,
    organization_id: str,
    conversation_id: Optional[str],
    message_text: str,
    history_dicts: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """
    Check if visitor contact info has already been provided either in database enquiry
    records or in recent conversation history/current message.
    """
    if conversation_id:
        existing_enq = (
            db.query(Enquiry)
            .filter(Enquiry.conversation_id == conversation_id, Enquiry.organization_id == organization_id)
            .first()
        )
        if existing_enq:
            phone_val = existing_enq.phone if existing_enq.phone not in ("Not provided", "", None) else None
            email_val = existing_enq.email if existing_enq.email not in ("Not provided", "", None) else None
            if phone_val or email_val:
                return {
                    "parent_name": existing_enq.parent_name if existing_enq.parent_name not in ("Website Visitor", "Parent / Visitor", "", None) else "Visitor",
                    "phone": phone_val,
                    "email": email_val,
                }
    lead = extract_lead_info(message=message_text, history=history_dicts)
    if lead.get("phone") or lead.get("email"):
        return {
            "parent_name": lead.get("parent_name") or "Visitor",
            "phone": lead.get("phone"),
            "email": lead.get("email"),
        }
    return None


def _dispatch_enquiry_alert(
    db: Session,
    organization_id: str,
    enquiry: Enquiry,
    source_label: str = "chat",
):
    """
    Dispatch email notification alert to organization recipients for newly captured or newly contactable lead.
    """
    from services.email_service import dispatch_lead_alert

    lead_payload = {
        "id": getattr(enquiry, "id", None),
        "parent_name": enquiry.parent_name,
        "phone": enquiry.phone,
        "email": enquiry.email,
        "interested_service": enquiry.interested_service,
        "category": enquiry.category,
        "description": enquiry.description,
        "preferred_contact": enquiry.preferred_contact,
    }
    dispatch_lead_alert(db, organization_id, lead_payload, source_label=source_label)


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
    should_dispatch_alert = False

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
        should_dispatch_alert = True
    else:
        had_no_phone = existing_enquiry.phone in ("Not provided", "", None)
        had_no_email = existing_enquiry.email in ("Not provided", "", None)
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
        if lead_info.get("phone") and had_no_phone:
            existing_enquiry.phone = lead_info["phone"]
            should_dispatch_alert = True
        if lead_info.get("email") and had_no_email:
            existing_enquiry.email = lead_info["email"]
            should_dispatch_alert = True
        existing_enquiry.description = f"{existing_enquiry.description}\nFollow-up: '{message_text[:200]}'"
        db.commit()
        db.refresh(existing_enquiry)

    if should_dispatch_alert:
        _dispatch_enquiry_alert(db, organization_id, existing_enquiry, source_label=source_label)

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
    org, setting = _resolve_tenant_for_chat(db, payload.chatbot_id, payload.conversation_id)

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
    language = (payload.language or "Auto").strip()

    retrieved_chunks = rag_service.query(
        message_text,
        top_k=6,
        org_slug=org.slug,
        collection_name=setting.knowledge_collection,
    )

    # Check for active Agent Studio configuration and Conversation Flow
    active_agent_cfg = None
    agent_setting = (
        db.query(AgentSetting)
        .filter(AgentSetting.organization_id == org.id, AgentSetting.is_active == True)
        .first()
    )
    if agent_setting and agent_setting.published_config_json:
        try:
            active_agent_cfg = json.loads(agent_setting.published_config_json)
        except Exception:
            active_agent_cfg = None

    active_flow_cfg = None
    active_flow = (
        db.query(ConversationFlow)
        .filter(ConversationFlow.organization_id == org.id, ConversationFlow.is_active == True)
        .first()
    )
    if active_flow and active_flow.flow_config_json:
        try:
            active_flow_cfg = json.loads(active_flow.flow_config_json)
        except Exception:
            active_flow_cfg = None

    effective_assistant_name = (
        active_agent_cfg.get("agent_name") if active_agent_cfg else None
    ) or setting.assistant_name

    contact_info_captured = _get_captured_contact_info(
        db=db,
        organization_id=org.id,
        conversation_id=conversation.id,
        message_text=message_text,
        history_dicts=history_dicts,
    )

    token_usage = {}
    ai_response_text, intent, requires_followup = gemini_service.generate_chat_response(
        user_message=message_text,
        retrieved_chunks=retrieved_chunks,
        conversation_history=history_dicts,
        language=language,
        organization_name=org.name,
        organization_slug=org.slug,
        assistant_name=effective_assistant_name,
        custom_instructions=setting.custom_instructions,
        usage_out=token_usage,
        agent_config=active_agent_cfg,
        flow_config=active_flow_cfg,
        contact_info_captured=contact_info_captured,
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
    record_usage(
        db,
        org.id,
        "ai_request",
        1,
        {"conversation_id": conversation.id},
        token_usage=token_usage,
    )
    db.commit()

    theme_cfg = resolve_chatbot_theme_config(org, setting)
    init_mode = theme_cfg.get("initial_behaviour", "welcome_and_suggestions")
    suggestions_enabled = theme_cfg.get("suggested_questions_enabled", True)
    if init_mode == "welcome_only" or not suggestions_enabled:
        suggested_queries = []
    else:
        active_prompts = theme_cfg.get("starter_prompts")
        suggested_queries = generate_suggested_queries(
            intent,
            language,
            organization_name=org.name,
            starter_prompts=active_prompts,
            enable_suggestions=True,
        )

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
        org, setting = _resolve_tenant_for_chat(db, payload.chatbot_id, payload.conversation_id)

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
        language = (payload.language or "Auto").strip()

        retrieved_chunks = rag_service.query(
            message_text,
            top_k=6,
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

        # Check for active Agent Studio configuration and Conversation Flow
        active_agent_cfg = None
        agent_setting = (
            db.query(AgentSetting)
            .filter(AgentSetting.organization_id == org.id, AgentSetting.is_active == True)
            .first()
        )
        if agent_setting and agent_setting.published_config_json:
            try:
                active_agent_cfg = json.loads(agent_setting.published_config_json)
            except Exception:
                active_agent_cfg = None

        active_flow_cfg = None
        active_flow = (
            db.query(ConversationFlow)
            .filter(ConversationFlow.organization_id == org.id, ConversationFlow.is_active == True)
            .first()
        )
        if active_flow and active_flow.flow_config_json:
            try:
                active_flow_cfg = json.loads(active_flow.flow_config_json)
            except Exception:
                active_flow_cfg = None

        conv_id = conversation.id
        conv_category = conversation.category
        org_id = org.id
        org_name = org.name
        org_slug = org.slug
        assistant_name = (
            active_agent_cfg.get("agent_name") if active_agent_cfg else None
        ) or setting.assistant_name
        custom_instructions = setting.custom_instructions
        stream_theme_cfg = resolve_chatbot_theme_config(org, setting)
        contact_info_captured = _get_captured_contact_info(
            db=db,
            organization_id=org.id,
            conversation_id=conversation.id,
            message_text=message_text,
            history_dicts=history_dicts,
        )
    finally:
        db.close()

    def stream_generator():
        assembled_chunks = []
        token_usage = {}
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
                usage_out=token_usage,
                agent_config=active_agent_cfg,
                flow_config=active_flow_cfg,
                contact_info_captured=contact_info_captured,
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

            record_usage(
                stream_db,
                org_id,
                "ai_request",
                1,
                {"conversation_id": conv_id},
                token_usage=token_usage,
            )
            stream_db.commit()

            theme_cfg = stream_theme_cfg
            init_mode = theme_cfg.get("initial_behaviour", "welcome_and_suggestions")
            suggestions_enabled = theme_cfg.get("suggested_questions_enabled", True)
            if init_mode == "welcome_only" or not suggestions_enabled:
                suggested_queries = []
            else:
                active_prompts = theme_cfg.get("starter_prompts")
                suggested_queries = generate_suggested_queries(
                    intent,
                    language,
                    organization_name=org_name,
                    starter_prompts=active_prompts,
                    enable_suggestions=True,
                )
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
