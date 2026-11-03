import os
import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "system_prompt.txt")

def load_system_prompt() -> str:
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading system prompt from {SYSTEM_PROMPT_PATH}: {e}")
        return "You are the official virtual support assistant for Prayatna Centre for Child Development."

def detect_intent(message: str) -> str:
    """Analyze user message for high-level intent."""
    m = message.lower()
    if any(k in m for k in ["payment", "fee", "receipt", "deducted", "refund", "transaction", "paid"]):
        return "payment_support"
    if any(k in m for k in ["appointment", "book", "schedule", "consult", "visit", "slot"]):
        return "appointment_enquiry"
    if any(k in m for k in [
        "speech therapy", "occupational therapy", "aba therapy", "behavior", 
        "physiotherapy", "assessment", "autism", "adhd", "service", "special education"
    ]):
        return "service_enquiry"
    return "general"

def extract_lead_info(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    user_message: Optional[str] = None,
    **kwargs
) -> Dict[str, Optional[str]]:
    """Simple heuristic extractor to detect contact information shared by parent."""
    all_texts = []
    if history:
        all_texts.extend([h.get("content", "") for h in history if isinstance(h, dict)])
    if message:
        all_texts.append(message)
    if user_message:
        all_texts.append(user_message)
    
    text_corpus = " ".join(all_texts)
    
    # Phone extraction (10+ digits or formatted phone)
    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3}[-.\s]?\d{3,4}", text_corpus)
    phone = phone_match.group(0).strip() if phone_match and len(re.sub(r"\D", "", phone_match.group(0))) >= 10 else None

    # Email extraction
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text_corpus)
    email = email_match.group(0).strip() if email_match else None

    # Child age
    age_match = re.search(r"(\d{1,2})\s*(?:year|yr|month|mth)s?\s*(?:old)?", text_corpus, re.IGNORECASE)
    child_age = age_match.group(0).strip() if age_match else None

    # Name extraction heuristic (e.g. "Name: John", "My name is John")
    name_match = re.search(r"(?:name\s*[:\-]?\s*|my name is\s+|i am\s+|this is\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text_corpus, re.IGNORECASE)
    parent_name = name_match.group(1).strip() if name_match else None

    return {
        "phone": phone,
        "email": email,
        "child_age": child_age,
        "parent_name": parent_name
    }

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        self.system_prompt = load_system_prompt()
        self._client = None
        self._init_client()

    def _init_client(self):
        # Refresh API key and model in case environment was updated
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logger.info(f"Gemini client initialized with model '{self.model_name}'.")
            except Exception as e:
                logger.error(f"Failed to initialize google-genai client: {e}")
                self._client = None
        else:
            self._client = None

    def _get_generation_config(self):
        try:
            from google.genai import types
            return types.GenerateContentConfig(
                max_output_tokens=350,
                temperature=0.3,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        except Exception as e:
            logger.warning(f"Failed to create GenerateContentConfig: {e}")
            return None

    def generate_chat_response(
        self,
        user_message: str,
        retrieved_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
        language: str = "English"
    ) -> Tuple[str, str, bool]:
        """
        Generate response using Gemini API or friendly fallback in user's preferred language.
        Returns: (assistant_message, intent, requires_followup)
        """
        intent = detect_intent(user_message)
        requires_followup = (intent in ("appointment_enquiry", "payment_support"))

        # Re-check client if key was added dynamically
        if not self._client and os.getenv("GEMINI_API_KEY"):
            self._init_client()

        # Format retrieved context
        context_blocks = []
        for idx, chunk in enumerate(retrieved_chunks):
            title = chunk.get("title", f"Document Chunk {idx+1}")
            url = chunk.get("url", "")
            content = chunk.get("content", "")
            context_blocks.append(f"--- SOURCE [{idx+1}]: {title} ({url}) ---\n{content}\n")
        
        context_text = "\n".join(context_blocks) if context_blocks else "No specific documents found in knowledge base."

        # If Gemini client is unavailable, provide transparent, friendly guidance based on retrieved context
        if not self._client:
            logger.warning("Gemini client is unconfigured or unavailable. Providing graceful fallback response.")
            if retrieved_chunks:
                top_source = retrieved_chunks[0]
                fallback_msg = (
                    f"Hello! Prayatna offers specialized pediatric developmental support.\n\n"
                    f"{top_source.get('content', '')[:250]}...\n\n"
                    f"Would you like to schedule an assessment or speak with our coordinator? "
                    f"Please share your Name and Phone Number, and our team will get in touch directly."
                )
            else:
                fallback_msg = (
                    f"Hello! Welcome to Prayatna Centre for Child Development.\n\n"
                    "We provide personalized developmental support for children. "
                    "If you would like to book an appointment or learn more, please share your Name and Phone Number."
                )
            return fallback_msg, intent, requires_followup

        # Build prompt for Gemini with explicit language enforcement and brevity
        history_formatted = []
        for msg in conversation_history[-6:]:  # Keep recent context compact
            role = "Customer" if msg.get("role") == "user" else "Assistant"
            history_formatted.append(f"{role}: {msg.get('content', '')}")
        history_str = "\n".join(history_formatted)

        language_instruction = (
            f"MANDATORY RESPONSE LANGUAGE: {language.upper()}\n"
            f"- Compose your ENTIRE response in {language}.\n"
            f"- Use natural, fluent, and respectful {language} phrasing suitable for concerned parents.\n"
        )

        brevity_instruction = (
            "CRITICAL LENGTH CONSTRAINT (STRICT):\n"
            "- Keep your response extremely brief: 2 to 4 sentences maximum (approx 45 to 80 words total).\n"
            "- Do NOT repeat greeting intros like 'Hello! I am the virtual support assistant for Prayatna...'.\n"
            "- Answer the parent's immediate question directly and concisely.\n"
            "- End with ONE brief call to action or question if needed.\n"
        )

        full_prompt = (
            f"SYSTEM INSTRUCTIONS:\n{self.system_prompt}\n\n"
            f"{brevity_instruction}\n"
            f"{language_instruction}\n"
            f"ORGANIZATIONAL KNOWLEDGE RETRIEVED:\n{context_text}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_str}\n\n"
            f"CURRENT CUSTOMER MESSAGE:\n{user_message}\n\n"
            f"Please respond concisely (under 80 words) entirely in {language}:"
        )

        try:
            config = self._get_generation_config()
            kwargs = {"model": self.model_name, "contents": full_prompt}
            if config:
                kwargs["config"] = config

            response = self._client.models.generate_content(**kwargs)
            response_text = response.text.strip() if response.text else ""
            if not response_text:
                raise ValueError("Empty response received from Gemini.")
            return response_text, intent, requires_followup
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            error_fallback = (
                "Thank you for reaching out to Prayatna. We encountered a temporary issue connecting to our AI service. "
                "Would you like to leave your name and phone number so our team can follow up directly?"
            )
            return error_fallback, intent, True

    def generate_chat_response_stream(
        self,
        user_message: str,
        retrieved_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
        language: str = "English"
    ):
        """
        Stream response tokens from Gemini in real time.
        Yields text chunks as they arrive.
        """
        if not self._client and os.getenv("GEMINI_API_KEY"):
            self._init_client()

        # Format retrieved context
        context_blocks = []
        for idx, chunk in enumerate(retrieved_chunks):
            title = chunk.get("title", f"Document Chunk {idx+1}")
            url = chunk.get("url", "")
            content = chunk.get("content", "")
            context_blocks.append(f"--- SOURCE [{idx+1}]: {title} ({url}) ---\n{content}\n")
        context_text = "\n".join(context_blocks) if context_blocks else "No specific documents found in knowledge base."

        if not self._client:
            # Fallback streamer
            fallback_text, _, _ = self.generate_chat_response(
                user_message=user_message,
                retrieved_chunks=retrieved_chunks,
                conversation_history=conversation_history,
                language=language
            )
            words = fallback_text.split(" ")
            for w in words:
                yield w + " "
            return

        history_formatted = []
        for msg in conversation_history[-6:]:
            role = "Customer" if msg.get("role") == "user" else "Assistant"
            history_formatted.append(f"{role}: {msg.get('content', '')}")
        history_str = "\n".join(history_formatted)

        language_instruction = (
            f"MANDATORY RESPONSE LANGUAGE: {language.upper()}\n"
            f"- Compose your ENTIRE response in {language}.\n"
            f"- Use natural, fluent, and respectful {language} phrasing suitable for concerned parents.\n"
        )

        brevity_instruction = (
            "CRITICAL LENGTH CONSTRAINT (STRICT):\n"
            "- Keep your response extremely brief: 2 to 4 sentences maximum (approx 45 to 80 words total).\n"
            "- Do NOT repeat greeting intros like 'Hello! I am the virtual support assistant for Prayatna...'.\n"
            "- Answer the parent's immediate question directly and concisely.\n"
            "- End with ONE brief call to action or question if needed.\n"
        )

        full_prompt = (
            f"SYSTEM INSTRUCTIONS:\n{self.system_prompt}\n\n"
            f"{brevity_instruction}\n"
            f"{language_instruction}\n"
            f"ORGANIZATIONAL KNOWLEDGE RETRIEVED:\n{context_text}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_str}\n\n"
            f"CURRENT CUSTOMER MESSAGE:\n{user_message}\n\n"
            f"Please respond concisely (under 80 words) entirely in {language}:"
        )

        try:
            config = self._get_generation_config()
            kwargs = {"model": self.model_name, "contents": full_prompt}
            if config:
                kwargs["config"] = config

            stream = self._client.models.generate_content_stream(**kwargs)
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Error streaming from Gemini: {e}")
            yield "Thank you for reaching out to Prayatna. We encountered a temporary connection issue. Would you like to leave your name and phone number so our team can follow up with you directly?"

gemini_service = GeminiService()
