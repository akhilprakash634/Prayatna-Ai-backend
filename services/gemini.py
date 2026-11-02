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

def extract_lead_info(message: str, history: List[Dict[str, str]]) -> Dict[str, Optional[str]]:
    """Simple heuristic extractor to detect contact information shared by parent."""
    text_corpus = " ".join([h.get("content", "") for h in history] + [message])
    
    # Phone extraction (10+ digits or formatted phone)
    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3}[-.\s]?\d{3,4}", text_corpus)
    phone = phone_match.group(0).strip() if phone_match and len(re.sub(r"\D", "", phone_match.group(0))) >= 10 else None

    # Email extraction
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text_corpus)
    email = email_match.group(0).strip() if email_match else None

    # Child age
    age_match = re.search(r"(\d{1,2})\s*(?:year|yr|month|mth)s?\s*(?:old)?", text_corpus, re.IGNORECASE)
    child_age = age_match.group(0).strip() if age_match else None

    return {
        "phone": phone,
        "email": email,
        "child_age": child_age
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

    def generate_chat_response(
        self,
        user_message: str,
        retrieved_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]]
    ) -> Tuple[str, str, bool]:
        """
        Generate response using Gemini API or friendly fallback.
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
                # Provide a direct, factual summary from the indexed knowledge
                top_source = retrieved_chunks[0]
                fallback_msg = (
                    f"Hello! Prayatna Centre for Child Development offers specialized support in this area.\n\n"
                    f"Here is information from our knowledge base:\n"
                    f"{top_source.get('content', '')[:350]}...\n\n"
                    f"Would you like to book an appointment or speak with our clinical coordinator? "
                    f"Please share your name, phone number, and email, and our team will get in touch with you right away.\n\n"
                    f"*(Note: Gemini live generation is in offline standby. To enable full AI answers, configure `GEMINI_API_KEY` in `backend/.env`.)*"
                )
            else:
                fallback_msg = (
                    "Hello! Welcome to Prayatna Centre for Child Development. "
                    "I would be glad to help connect you with our clinical team or guide you through our developmental programs.\n\n"
                    "If you would like to schedule an appointment or have a question about our services, "
                    "please share your name, phone number, and interested service so our coordinators can reach out to you.\n\n"
                    "*(Note: To enable live Gemini AI generation, please set `GEMINI_API_KEY` in your `backend/.env` file.)*"
                )
            return fallback_msg, intent, requires_followup

        # Build prompt for Gemini
        history_formatted = []
        for msg in conversation_history[-8:]:  # Keep recent context
            role = "Customer" if msg.get("role") == "user" else "Assistant"
            history_formatted.append(f"{role}: {msg.get('content', '')}")
        history_str = "\n".join(history_formatted)

        full_prompt = (
            f"SYSTEM INSTRUCTIONS:\n{self.system_prompt}\n\n"
            f"ORGANIZATIONAL KNOWLEDGE RETRIEVED:\n{context_text}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_str}\n\n"
            f"CURRENT CUSTOMER MESSAGE:\n{user_message}\n\n"
            f"Please respond as Prayatna Assistant following all healthcare safety, personality, and enquiry collection guidelines:"
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
            )
            response_text = response.text.strip() if response.text else ""
            if not response_text:
                raise ValueError("Empty response received from Gemini.")
            return response_text, intent, requires_followup
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            error_fallback = (
                "Thank you for reaching out to Prayatna. We encountered a temporary issue connecting to our AI service, "
                "but your conversation is preserved. Would you like to leave your name and phone number so our team can follow up with you directly?"
            )
            return error_fallback, intent, True

gemini_service = GeminiService()
