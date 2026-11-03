import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models import Conversation, Message, Enquiry
from schemas import ChatRequest, ChatResponse, SourceCitation
from services.rag import rag_service
from services.gemini import gemini_service, extract_lead_info, detect_intent, generate_suggested_queries

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
    lead_info = extract_lead_info(message=message_text, history=history_dicts)
    if lead_info.get("phone") or lead_info.get("email"):
        existing_enquiry = db.query(Enquiry).filter(Enquiry.conversation_id == conversation.id).first()
        service_name = lead_info.get("interested_service")
        if not service_name or service_name == "General Consultation":
            if conversation.category and conversation.category not in ("general", None):
                service_name = conversation.category.replace("_", " ").title()
            else:
                service_name = "Comprehensive Developmental Assessment"

        cat = "payment_support" if intent == "payment_support" else "appointment"

        if not existing_enquiry:
            enquiry = Enquiry(
                conversation_id=conversation.id,
                parent_name=lead_info.get("parent_name") or "Website Visitor",
                email=lead_info.get("email") or "Not provided",
                phone=lead_info.get("phone") or "Not provided",
                child_age=lead_info.get("child_age"),
                interested_service=service_name,
                category=cat,
                description=f"Enquiry from chat: '{message_text[:200]}'",
                preferred_contact="phone" if lead_info.get("phone") else "email",
                status="New"
            )
            db.add(enquiry)
            db.commit()
            db.refresh(enquiry)
            existing_enquiry = enquiry
            conversation.status = "lead_captured"
        else:
            if lead_info.get("parent_name") and existing_enquiry.parent_name in ("Website Visitor", "Parent / Visitor", ""):
                existing_enquiry.parent_name = lead_info["parent_name"]
            if lead_info.get("child_age") and not existing_enquiry.child_age:
                existing_enquiry.child_age = lead_info["child_age"]
            if service_name and existing_enquiry.interested_service in ("General Consultation", "Comprehensive Developmental Assessment", ""):
                existing_enquiry.interested_service = service_name
            if lead_info.get("phone") and existing_enquiry.phone in ("Not provided", ""):
                existing_enquiry.phone = lead_info["phone"]
            if lead_info.get("email") and existing_enquiry.email in ("Not provided", ""):
                existing_enquiry.email = lead_info["email"]
            existing_enquiry.description = f"{existing_enquiry.description}\nFollow-up: '{message_text[:200]}'"
            db.commit()
            db.refresh(existing_enquiry)

        enquiry_data = {
            "id": existing_enquiry.id,
            "parent_name": existing_enquiry.parent_name,
            "phone": existing_enquiry.phone,
            "email": existing_enquiry.email,
            "child_age": existing_enquiry.child_age,
            "interested_service": existing_enquiry.interested_service,
            "category": existing_enquiry.category,
            "status": existing_enquiry.status
        }

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

    suggested_queries = generate_suggested_queries(intent, language)

    return ChatResponse(
        conversation_id=conversation.id,
        message=ai_response_text,
        sources=sources_list,
        intent=intent,
        requires_followup=requires_followup,
        enquiry_captured=enquiry_data,
        language=language,
        suggested_queries=suggested_queries
    )


@router.post("/stream")
def handle_chat_stream(payload: ChatRequest):
    """
    Streams the assistant response token-by-token using Server-Sent Events (SSE).
    Significantly reduces perceived latency (Time to First Token < 500ms).
    """
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")

    # 1. Retrieve or create conversation with an isolated session
    db = SessionLocal()
    try:
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

        # 3. Fast RAG retrieval (top 3 for low latency)
        retrieved_chunks = rag_service.query(message_text, top_k=3)
        intent = detect_intent(message_text)
        requires_followup = (intent in ("appointment_enquiry", "payment_support"))

        # Extract sources
        seen_urls = set()
        sources_list = []
        for chunk in retrieved_chunks:
            url = chunk.get("url") or "https://prayatna.co.in/"
            title = chunk.get("title") or "Prayatna Resource"
            if url not in seen_urls:
                seen_urls.add(url)
                sources_list.append({"title": title, "url": url})

        # Save user message immediately
        user_msg = Message(
            conversation_id=conversation.id,
            role="user",
            content=message_text
        )
        db.add(user_msg)
        db.commit()

        conv_id = conversation.id
    finally:
        db.close()

    def stream_generator():
        assembled_chunks = []
        stream_db = SessionLocal()
        try:
            # Emit init event immediately
            init_payload = json.dumps({
                "type": "init",
                "conversation_id": conv_id,
                "sources": sources_list,
                "intent": intent,
                "requires_followup": requires_followup,
                "language": language
            })
            yield f"data: {init_payload}\n\n"

            # Stream chunks from Gemini
            for token in gemini_service.generate_chat_response_stream(
                user_message=message_text,
                retrieved_chunks=retrieved_chunks,
                conversation_history=history_dicts,
                language=language
            ):
                assembled_chunks.append(token)
                chunk_payload = json.dumps({
                    "type": "chunk",
                    "text": token
                })
                yield f"data: {chunk_payload}\n\n"

            full_text = "".join(assembled_chunks)

            # Check lead / enquiry extraction safely
            enquiry_data = None
            try:
                captured_info = extract_lead_info(message=message_text, history=history_dicts)
                if captured_info.get("phone") or captured_info.get("email"):
                    existing_enquiry = stream_db.query(Enquiry).filter(Enquiry.conversation_id == conv_id).first()
                    service_name = captured_info.get("interested_service")
                    if not service_name or service_name == "General Consultation":
                        conv_record = stream_db.query(Conversation).filter(Conversation.id == conv_id).first()
                        if conv_record and conv_record.category and conv_record.category not in ("general", None):
                            service_name = conv_record.category.replace("_", " ").title()
                        else:
                            service_name = "Comprehensive Developmental Assessment"

                    cat = "payment_support" if intent == "payment_support" else "appointment"

                    if not existing_enquiry:
                        new_enquiry = Enquiry(
                            conversation_id=conv_id,
                            parent_name=captured_info.get("parent_name") or "Website Visitor",
                            phone=captured_info.get("phone") or "Not provided",
                            email=captured_info.get("email") or "Not provided",
                            child_age=captured_info.get("child_age"),
                            interested_service=service_name,
                            category=cat,
                            description=f"Enquiry from streaming chat: '{message_text[:200]}'",
                            preferred_contact="phone" if captured_info.get("phone") else "email",
                            status="New"
                        )
                        stream_db.add(new_enquiry)
                        stream_db.commit()
                        stream_db.refresh(new_enquiry)
                        existing_enquiry = new_enquiry
                    else:
                        if captured_info.get("parent_name") and existing_enquiry.parent_name in ("Website Visitor", "Parent / Visitor", ""):
                            existing_enquiry.parent_name = captured_info["parent_name"]
                        if captured_info.get("child_age") and not existing_enquiry.child_age:
                            existing_enquiry.child_age = captured_info["child_age"]
                        if service_name and existing_enquiry.interested_service in ("General Consultation", "Comprehensive Developmental Assessment", ""):
                            existing_enquiry.interested_service = service_name
                        if captured_info.get("phone") and existing_enquiry.phone in ("Not provided", ""):
                            existing_enquiry.phone = captured_info["phone"]
                        if captured_info.get("email") and existing_enquiry.email in ("Not provided", ""):
                            existing_enquiry.email = captured_info["email"]
                        existing_enquiry.description = f"{existing_enquiry.description}\nFollow-up: '{message_text[:200]}'"
                        stream_db.commit()
                        stream_db.refresh(existing_enquiry)

                    enquiry_data = {
                        "id": existing_enquiry.id,
                        "parent_name": existing_enquiry.parent_name,
                        "phone": existing_enquiry.phone,
                        "email": existing_enquiry.email,
                        "child_age": existing_enquiry.child_age,
                        "interested_service": existing_enquiry.interested_service,
                        "category": existing_enquiry.category,
                        "status": existing_enquiry.status
                    }
            except Exception as e_lead:
                logger.warning(f"Error extracting lead info in stream: {e_lead}")

            # Save assistant message to DB
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=full_text,
                sources_json=json.dumps(sources_list)
            )
            stream_db.add(assistant_msg)

            # Update conversation timestamp and category
            conv_record = stream_db.query(Conversation).filter(Conversation.id == conv_id).first()
            if conv_record:
                from models import utc_now
                conv_record.updated_at = utc_now()
                if conv_record.category in ("general", None) and intent != "general":
                    conv_record.category = intent
                if enquiry_data:
                    conv_record.status = "lead_captured"

            stream_db.commit()

            suggested_queries = generate_suggested_queries(intent, language)

            # Emit final done event
            done_payload = json.dumps({
                "type": "done",
                "conversation_id": conv_id,
                "sources": sources_list,
                "intent": intent,
                "requires_followup": requires_followup,
                "enquiry_captured": enquiry_data,
                "language": language,
                "suggested_queries": suggested_queries
            })
            yield f"data: {done_payload}\n\n"

        except Exception as err:
            logger.error(f"Error in stream_generator: {err}")
            err_payload = json.dumps({
                "type": "error",
                "message": str(err)
            })
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
        }
    )

