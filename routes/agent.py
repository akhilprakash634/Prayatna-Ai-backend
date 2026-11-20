import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import AgentSetting, ChatbotSetting, ConversationFlow, Organization, utc_now
from schemas import (
    AgentBehaviourConfig,
    AgentPreviewRequest,
    AgentPreviewResponse,
    AgentResponseConfig,
    AgentSettingsResponse,
    AgentSettingsUpdate,
    AgentWelcomeConfig,
    ConversationFlowConfig,
    ConversationFlowCreate,
    ConversationFlowResponse,
    ConversationFlowStep,
    ConversationFlowUpdate,
    SourceCitation,
    SuggestedQuestionItem,
)
from services.gemini import detect_intent, gemini_service, generate_suggested_queries
from services.rag import rag_service
from services.security import AuthContext, require_client_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["Agent Studio"])

DEFAULT_PERSONALITIES = ["Friendly", "Professional", "Empathetic"]

DEFAULT_SUGGESTED_QUESTIONS = [
    SuggestedQuestionItem(id="q1", text="Explore Our Services", enabled=True),
    SuggestedQuestionItem(id="q2", text="Appointment Enquiry", enabled=True),
    SuggestedQuestionItem(id="q3", text="Payment Support", enabled=True),
    SuggestedQuestionItem(id="q4", text="Talk to Our Team", enabled=True),
]

DEFAULT_STEPS = [
    ConversationFlowStep(id="s1", title="Welcome & Greeting", description="Greet visitor and introduce digital assistant", step_type="greeting", enabled=True),
    ConversationFlowStep(id="s2", title="Requirement Triage", description="Determine whether user needs services, appointments, or billing help", step_type="question", enabled=True),
    ConversationFlowStep(id="s3", title="Knowledge Explanation", description="Provide factual answers strictly using internal documentation", step_type="explanation", enabled=True),
    ConversationFlowStep(id="s4", title="Lead Information Capture", description="Politely request Name and Phone number for appointment/callback", step_type="info_collection", enabled=True),
    ConversationFlowStep(id="s5", title="Enquiry Confirmation", description="Acknowledge request submission and reassure prompt response", step_type="enquiry", enabled=True),
    ConversationFlowStep(id="s6", title="Human Escalation", description="Offer connection with live team coordinator if needed", step_type="escalation", enabled=True),
]


def _default_agent_setting(org: Organization) -> AgentSetting:
    is_prayatna = (org.slug == "prayatna")
    agent_name = "Sarah" if is_prayatna else "Alex"
    role = "Customer Support Assistant"
    desc = (
        f"You are a friendly and professional virtual assistant representing {org.name}."
    )
    primary_resp = (
        "Assist parents with service enquiries, general information and appointment requests."
        if is_prayatna
        else f"Assist visitors and customers with enquiries, service bookings, and support for {org.name}."
    )
    welcome_msg = (
        f"Hello! Welcome to {org.name}. How can I help you today?"
    )

    welcome_cfg = AgentWelcomeConfig(
        welcome_message=welcome_msg,
        agent_intro=f"I'm {agent_name}, your virtual assistant.",
        greeting_style="Friendly",
        initial_behaviour="welcome_and_suggestions",
        suggested_questions=DEFAULT_SUGGESTED_QUESTIONS,
    )
    behaviour_cfg = AgentBehaviourConfig()
    response_cfg = AgentResponseConfig(
        fallback_message=f"I'm sorry, I don't have that information in our current documentation. Would you like me to connect you with our team at {org.name}?"
    )

    return AgentSetting(
        organization_id=org.id,
        agent_name=agent_name,
        agent_role=role,
        agent_description=desc,
        personality=json.dumps(DEFAULT_PERSONALITIES),
        tone="Friendly",
        attitude="Helpful",
        response_length="balanced",
        communication_style="conversational",
        formality="semi-formal",
        emoji_usage="minimal",
        language_preference="Auto",
        custom_instructions=None,
        behaviour_config_json=json.dumps(behaviour_cfg.model_dump()),
        welcome_config_json=json.dumps(welcome_cfg.model_dump()),
        response_config_json=json.dumps(response_cfg.model_dump()),
        is_active=False,
        published_config_json=None,
    )


def _parse_json_dict(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _serialize_draft_snapshot(setting: AgentSetting, org_name: str) -> Dict[str, Any]:
    try:
        pers = json.loads(setting.personality) if setting.personality else DEFAULT_PERSONALITIES
    except Exception:
        pers = DEFAULT_PERSONALITIES

    return {
        "agent_name": setting.agent_name,
        "agent_role": setting.agent_role,
        "agent_description": setting.agent_description,
        "organization_name": org_name,
        "personality": pers,
        "tone": setting.tone,
        "attitude": setting.attitude,
        "response_length": setting.response_length,
        "communication_style": setting.communication_style,
        "formality": setting.formality,
        "emoji_usage": setting.emoji_usage,
        "language_preference": setting.language_preference,
        "custom_instructions": setting.custom_instructions,
        "behaviour_config": _parse_json_dict(setting.behaviour_config_json),
        "welcome_config": _parse_json_dict(setting.welcome_config_json),
        "response_config": _parse_json_dict(setting.response_config_json),
    }


def _to_agent_response(setting: AgentSetting, org: Organization) -> AgentSettingsResponse:
    try:
        pers = json.loads(setting.personality) if setting.personality else DEFAULT_PERSONALITIES
        if not isinstance(pers, list):
            pers = [str(pers)]
    except Exception:
        pers = DEFAULT_PERSONALITIES

    beh_dict = _parse_json_dict(setting.behaviour_config_json)
    wel_dict = _parse_json_dict(setting.welcome_config_json)
    res_dict = _parse_json_dict(setting.response_config_json)

    current_snapshot = _serialize_draft_snapshot(setting, org.name)
    published_snapshot = _parse_json_dict(setting.published_config_json)

    # Check if draft has changes pending publication
    has_draft_changes = False
    if not setting.is_active or not setting.published_config_json:
        has_draft_changes = True
    else:
        has_draft_changes = (json.dumps(current_snapshot, sort_keys=True) != json.dumps(published_snapshot, sort_keys=True))

    return AgentSettingsResponse(
        id=setting.id,
        organization_id=setting.organization_id,
        agent_name=setting.agent_name,
        agent_role=setting.agent_role,
        agent_description=setting.agent_description,
        organization_name=org.name,
        personality=pers,
        tone=setting.tone,
        attitude=setting.attitude,
        response_length=setting.response_length,
        communication_style=setting.communication_style,
        formality=setting.formality,
        emoji_usage=setting.emoji_usage,
        language_preference=setting.language_preference,
        custom_instructions=setting.custom_instructions,
        behaviour_config=AgentBehaviourConfig(**beh_dict) if beh_dict else AgentBehaviourConfig(),
        welcome_config=AgentWelcomeConfig(**wel_dict) if wel_dict else AgentWelcomeConfig(),
        response_config=AgentResponseConfig(**res_dict) if res_dict else AgentResponseConfig(),
        is_active=bool(setting.is_active),
        has_draft_changes=has_draft_changes,
        last_activated_at=setting.last_activated_at,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


def _get_or_create_agent_setting(db: Session, org: Organization) -> AgentSetting:
    setting = db.query(AgentSetting).filter(AgentSetting.organization_id == org.id).first()
    if not setting:
        setting = _default_agent_setting(org)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.get("/settings", response_model=AgentSettingsResponse)
def get_agent_settings(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """Retrieve the authenticated organization's Agent Studio configuration."""
    org = ctx.organization
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    setting = _get_or_create_agent_setting(db, org)
    return _to_agent_response(setting, org)


@router.put("/settings", response_model=AgentSettingsResponse)
def update_agent_settings(
    req: AgentSettingsUpdate,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """Update draft Agent Studio settings for the authenticated organization."""
    org = ctx.organization
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    setting = _get_or_create_agent_setting(db, org)

    if req.agent_name is not None:
        setting.agent_name = req.agent_name.strip()
    if req.agent_role is not None:
        setting.agent_role = req.agent_role.strip()
    if req.agent_description is not None:
        setting.agent_description = req.agent_description.strip()
    if req.personality is not None:
        setting.personality = json.dumps(req.personality)
    if req.tone is not None:
        setting.tone = req.tone.strip()
    if req.attitude is not None:
        setting.attitude = req.attitude.strip()
    if req.response_length is not None:
        setting.response_length = req.response_length.strip()
    if req.communication_style is not None:
        setting.communication_style = req.communication_style.strip()
    if req.formality is not None:
        setting.formality = req.formality.strip()
    if req.emoji_usage is not None:
        setting.emoji_usage = req.emoji_usage.strip()
    if req.language_preference is not None:
        setting.language_preference = req.language_preference.strip()
    if req.custom_instructions is not None:
        setting.custom_instructions = req.custom_instructions.strip() or None
    if req.behaviour_config is not None:
        setting.behaviour_config_json = json.dumps(req.behaviour_config.model_dump())
    if req.welcome_config is not None:
        setting.welcome_config_json = json.dumps(req.welcome_config.model_dump())
    if req.response_config is not None:
        setting.response_config_json = json.dumps(req.response_config.model_dump())

    db.commit()
    db.refresh(setting)
    return _to_agent_response(setting, org)


@router.post("/activate", response_model=AgentSettingsResponse)
def activate_agent(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """
    Publish the current draft configuration as the active production agent.
    Snapshots the draft into published_config_json and synchronizes branding/welcome.
    """
    org = ctx.organization
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    setting = _get_or_create_agent_setting(db, org)

    snapshot = _serialize_draft_snapshot(setting, org.name)
    setting.published_config_json = json.dumps(snapshot)
    setting.is_active = True
    setting.last_activated_at = utc_now()

    # Synchronize relevant public chatbot settings so widget and direct chat immediately reflect active changes
    chatbot_setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
    if chatbot_setting:
        if setting.agent_name:
            chatbot_setting.assistant_name = setting.agent_name
        wel_cfg = _parse_json_dict(setting.welcome_config_json)
        if wel_cfg.get("welcome_message"):
            chatbot_setting.welcome_message = wel_cfg["welcome_message"]

        # Sync starter prompts respecting initial_behaviour mode
        init_mode = wel_cfg.get("initial_behaviour", "welcome_and_suggestions")
        try:
            theme_dict = json.loads(chatbot_setting.theme_config_json or "{}")
        except Exception:
            theme_dict = {}

        if init_mode == "welcome_only":
            theme_dict["starter_prompts"] = []
            chatbot_setting.theme_config_json = json.dumps(theme_dict)
        elif wel_cfg.get("suggested_questions") is not None:
            active_starters = [
                q["text"] for q in wel_cfg["suggested_questions"] if q.get("enabled", True) and q.get("text")
            ]
            theme_dict["starter_prompts"] = active_starters
            chatbot_setting.theme_config_json = json.dumps(theme_dict)

    db.commit()
    db.refresh(setting)
    return _to_agent_response(setting, org)


@router.post("/reset", response_model=AgentSettingsResponse)
def reset_draft_settings(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """
    Reset draft changes back to the currently published configuration (or defaults).
    """
    org = ctx.organization
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    setting = _get_or_create_agent_setting(db, org)

    if setting.published_config_json:
        published = _parse_json_dict(setting.published_config_json)
        setting.agent_name = published.get("agent_name", setting.agent_name)
        setting.agent_role = published.get("agent_role", setting.agent_role)
        setting.agent_description = published.get("agent_description", setting.agent_description)
        setting.personality = json.dumps(published.get("personality", DEFAULT_PERSONALITIES))
        setting.tone = published.get("tone", "Friendly")
        setting.attitude = published.get("attitude", "Helpful")
        setting.response_length = published.get("response_length", "balanced")
        setting.communication_style = published.get("communication_style", "conversational")
        setting.formality = published.get("formality", "semi-formal")
        setting.emoji_usage = published.get("emoji_usage", "minimal")
        setting.language_preference = published.get("language_preference", "Auto")
        setting.custom_instructions = published.get("custom_instructions")
        setting.behaviour_config_json = json.dumps(published.get("behaviour_config", {}))
        setting.welcome_config_json = json.dumps(published.get("welcome_config", {}))
        setting.response_config_json = json.dumps(published.get("response_config", {}))
    else:
        default_inst = _default_agent_setting(org)
        setting.agent_name = default_inst.agent_name
        setting.agent_role = default_inst.agent_role
        setting.agent_description = default_inst.agent_description
        setting.personality = default_inst.personality
        setting.tone = default_inst.tone
        setting.attitude = default_inst.attitude
        setting.response_length = default_inst.response_length
        setting.communication_style = default_inst.communication_style
        setting.formality = default_inst.formality
        setting.emoji_usage = default_inst.emoji_usage
        setting.language_preference = default_inst.language_preference
        setting.custom_instructions = default_inst.custom_instructions
        setting.behaviour_config_json = default_inst.behaviour_config_json
        setting.welcome_config_json = default_inst.welcome_config_json
        setting.response_config_json = default_inst.response_config_json

    db.commit()
    db.refresh(setting)
    return _to_agent_response(setting, org)


@router.post("/preview", response_model=AgentPreviewResponse)
def preview_agent_chat(
    req: AgentPreviewRequest,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """
    Test draft agent configuration in real-time.
    Runs the full 7-layer dynamic prompt engine against live Gemini and RAG knowledge
    WITHOUT mutating conversations, messages, or creating actual CRM enquiries.
    """
    org = ctx.organization
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    setting = _get_or_create_agent_setting(db, org)
    chatbot_setting = db.query(ChatbotSetting).filter(ChatbotSetting.organization_id == org.id).first()
    collection_name = chatbot_setting.knowledge_collection if chatbot_setting else f"org_{org.slug}"

    # Build effective draft configuration
    draft = _serialize_draft_snapshot(setting, org.name)
    if req.draft_settings:
        update_dict = req.draft_settings.model_dump(exclude_unset=True)
        for k, v in update_dict.items():
            if v is not None:
                if k in ("behaviour_config", "welcome_config", "response_config") and hasattr(v, "model_dump"):
                    draft[k] = v.model_dump()
                else:
                    draft[k] = v

    # Query organization's vector knowledge base
    message_text = req.message.strip()
    retrieved_chunks = rag_service.query(
        message_text,
        top_k=6,
        org_slug=org.slug,
        collection_name=collection_name,
    )

    intent = detect_intent(message_text)
    requires_followup = intent in ("appointment_enquiry", "payment_support")

    raw_sources = []
    seen = set()
    for chunk in retrieved_chunks:
        url = chunk.get("url") or org.website or ""
        title = chunk.get("title") or f"{org.name} Resource"
        key = f"{title}::{url}"
        if key not in seen:
            seen.add(key)
            raw_sources.append(SourceCitation(title=title, url=url))

    # Fetch active conversation flow if present
    active_flow = (
        db.query(ConversationFlow)
        .filter(ConversationFlow.organization_id == org.id, ConversationFlow.is_active == True)
        .first()
    )
    flow_cfg = _parse_json_dict(active_flow.flow_config_json) if active_flow else None

    # Generate response via 7-layer prompt engine
    effective_language = req.language or draft.get("language_preference") or "Auto"
    ai_response, detected_intent, followup_needed = gemini_service.generate_chat_response(
        user_message=message_text,
        retrieved_chunks=retrieved_chunks,
        conversation_history=req.conversation_history,
        language=effective_language,
        organization_name=org.name,
        organization_slug=org.slug,
        assistant_name=draft.get("agent_name"),
        agent_config=draft,
        flow_config=flow_cfg,
    )

    # Build suggested queries
    wel_cfg = draft.get("welcome_config") or {}
    suggested_queries = []
    if wel_cfg.get("suggested_questions"):
        suggested_queries = [
            q["text"] for q in wel_cfg["suggested_questions"] if q.get("enabled", True) and q.get("text")
        ][:4]
    if not suggested_queries:
        suggested_queries = generate_suggested_queries(detected_intent, effective_language, organization_name=org.name)

    return AgentPreviewResponse(
        message=ai_response,
        intent=detected_intent,
        sources=raw_sources,
        requires_followup=followup_needed,
        suggested_queries=suggested_queries,
        language=effective_language,
    )


# ============================================================================
# Conversation Flows
# ============================================================================

def _to_flow_response(flow: ConversationFlow) -> ConversationFlowResponse:
    cfg_dict = _parse_json_dict(flow.flow_config_json)
    return ConversationFlowResponse(
        id=flow.id,
        organization_id=flow.organization_id,
        flow_name=flow.flow_name,
        flow_type=flow.flow_type,
        flow_config=ConversationFlowConfig(**cfg_dict) if cfg_dict else ConversationFlowConfig(steps=DEFAULT_STEPS),
        is_active=bool(flow.is_active),
        created_at=flow.created_at,
        updated_at=flow.updated_at,
    )


@router.get("/flows", response_model=List[ConversationFlowResponse])
def get_conversation_flows(
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """List all conversation flows for the authenticated organization."""
    flows = (
        db.query(ConversationFlow)
        .filter(ConversationFlow.organization_id == ctx.organization_id)
        .order_by(ConversationFlow.created_at.asc())
        .all()
    )

    if not flows and ctx.organization:
        # Seed default conversation flow
        default_flow_cfg = ConversationFlowConfig(steps=DEFAULT_STEPS)
        flow = ConversationFlow(
            organization_id=ctx.organization_id,
            flow_name="Standard Triage & Lead Capture Flow",
            flow_type="default",
            flow_config_json=json.dumps(default_flow_cfg.model_dump()),
            is_active=True,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        flows = [flow]

    return [_to_flow_response(f) for f in flows]


@router.post("/flows", response_model=ConversationFlowResponse, status_code=status.HTTP_201_CREATED)
def create_conversation_flow(
    req: ConversationFlowCreate,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """Create a new conversation flow for the authenticated organization."""
    flow = ConversationFlow(
        organization_id=ctx.organization_id,
        flow_name=req.flow_name.strip(),
        flow_type=req.flow_type.strip(),
        flow_config_json=json.dumps(req.flow_config.model_dump()),
        is_active=bool(req.is_active),
    )
    db.add(flow)
    db.commit()
    db.refresh(flow)
    return _to_flow_response(flow)


@router.put("/flows/{flow_id}", response_model=ConversationFlowResponse)
def update_conversation_flow(
    flow_id: str,
    req: ConversationFlowUpdate,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """Update a conversation flow owned by the authenticated organization."""
    flow = (
        db.query(ConversationFlow)
        .filter(ConversationFlow.id == flow_id, ConversationFlow.organization_id == ctx.organization_id)
        .first()
    )
    if not flow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation flow not found.")

    if req.flow_name is not None:
        flow.flow_name = req.flow_name.strip()
    if req.flow_type is not None:
        flow.flow_type = req.flow_type.strip()
    if req.flow_config is not None:
        flow.flow_config_json = json.dumps(req.flow_config.model_dump())
    if req.is_active is not None:
        flow.is_active = bool(req.is_active)

    db.commit()
    db.refresh(flow)
    return _to_flow_response(flow)


@router.delete("/flows/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation_flow(
    flow_id: str,
    ctx: AuthContext = Depends(require_client_admin),
    db: Session = Depends(get_db),
):
    """Delete a conversation flow owned by the authenticated organization."""
    flow = (
        db.query(ConversationFlow)
        .filter(ConversationFlow.id == flow_id, ConversationFlow.organization_id == ctx.organization_id)
        .first()
    )
    if not flow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation flow not found.")

    db.delete(flow)
    db.commit()
    return None
