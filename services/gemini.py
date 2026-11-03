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

SERVICES_MAP = [
    (r"speech(\s+and\s+language)?(\s+therapy)?", "Speech Therapy"),
    (r"occupational(\s+therapy)?|sensory(\s+integration)?", "Occupational Therapy"),
    (r"aba(\s+therapy)?|behavio(u)?r(al)?(\s+therapy)?", "Behavioral & ABA Therapy"),
    (r"autism|asd", "Autism Spectrum Support"),
    (r"adhd", "ADHD Support"),
    (r"physio(therapy)?|motor\s+skills", "Physiotherapy"),
    (r"special\s+education|learning\s+disability", "Special Education"),
    (r"assess(ment)?|screening|evaluation", "Developmental Assessment"),
]

def detect_service(corpus: str) -> Optional[str]:
    c = corpus.lower()
    for pattern, service_name in SERVICES_MAP:
        if re.search(pattern, c):
            return service_name
    return None

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
    msg_only = (message or user_message or "").strip()

    # 1. Phone extraction (10+ digits or formatted phone)
    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3}[-.\s]?\d{3,4}", text_corpus)
    phone = phone_match.group(0).strip() if phone_match and len(re.sub(r"\D", "", phone_match.group(0))) >= 10 else None

    # 2. Email extraction
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text_corpus)
    email = email_match.group(0).strip() if email_match else None

    # 3. Child age extraction
    child_age = None
    # Pattern A: e.g. "12 years", "4 yrs", "18 months"
    age_match = re.search(r"(\d{1,2})\s*(?:years?|yrs?|months?|mths?)\s*(?:old)?", text_corpus, re.IGNORECASE)
    if age_match:
        child_age = age_match.group(0).strip()
    
    # Pattern B: e.g. "age: 12", "age 12", "age - 5"
    if not child_age:
        age_label_match = re.search(r"(?:age|child\s*age)\s*[:=\-]?\s*(\d{1,2})", text_corpus, re.IGNORECASE)
        if age_label_match:
            child_age = f"{age_label_match.group(1)} years"

    # 4. Parent Name extraction
    parent_name = None
    # Pattern A: e.g. "Name: Akhil", "My name is Akhil", "I am Akhil"
    name_match = re.search(r"(?:name\s*[:\-]?\s*|my name is\s+|i am\s+|this is\s+)([A-Za-z]+(?:\s+[A-Za-z]+)?)", msg_only, re.IGNORECASE)
    if name_match:
        parent_name = name_match.group(1).strip()

    # 5. Comma / Delimiter parsing for direct replies (e.g. "Akhil, 7902819158, 12")
    tokens = [t.strip() for t in re.split(r"[,;\n|/]", msg_only) if t.strip()]
    cleaned_tokens = []
    for t in tokens:
        # If token is phone, skip
        if phone and re.sub(r"\D", "", t) == re.sub(r"\D", "", phone):
            continue
        # If token is email, skip
        if email and t.lower() == email.lower():
            continue
        cleaned_tokens.append(t)

    for t in cleaned_tokens:
        # Check if token is just age number (e.g. '12' or '4')
        if not child_age and re.fullmatch(r"\d{1,2}", t):
            val = int(t)
            if 1 <= val <= 20:
                child_age = f"{val} years"
                continue

        # Check if token is person's name (1 to 3 words, pure alphabetic)
        if not parent_name and re.fullmatch(r"[A-Za-z\s]{2,30}", t):
            t_low = t.lower()
            if t_low not in [
                "yes", "no", "hi", "hello", "appointment", "assessment", 
                "speech therapy", "therapy", "general", "okay", "ok", "please", "thanks"
            ]:
                parent_name = t.title()

    # 6. Service extraction across message and past conversation history
    interested_service = detect_service(text_corpus)

    return {
        "phone": phone,
        "email": email,
        "child_age": child_age,
        "parent_name": parent_name,
        "interested_service": interested_service
    }

def generate_suggested_queries(intent: str, language: str = "English") -> List[str]:
    """Generate 2-3 relevant follow-up question chips based on conversation intent and language."""
    lang = (language or "English").lower()
    
    # Malayalam
    if "malayalam" in lang:
        if intent == "appointment_enquiry":
            return [
                "സെന്റർ ലൊക്കേഷനുകളും സമയവും എപ്പോഴാണ്?",
                "അസസ്സ്മെന്റിന് എന്തൊക്കെ വിവരങ്ങൾ വേണം?",
                "ഓൺലൈൻ കൺസൾട്ടേഷൻ ലഭ്യമാണോ?"
            ]
        elif intent == "payment_support":
            return [
                "പണം കുറഞ്ഞതിന്റെ സ്റ്റാറ്റസ് പരിശോധിക്കൂ",
                "അക്കൗണ്ട്സ് ടീമുമായി സംസാരിക്കണം",
                "ഫീസ് റസീറ്റ് എങ്ങനെ ലഭിക്കും?"
            ]
        elif intent == "service_enquiry":
            return [
                "ഒരു അസസ്സ്മെന്റ് എങ്ങനെ ബുക്ക് ചെയ്യാം?",
                "തെറാപ്പി ഫീസ് വിവരങ്ങൾ അറിയാമോ?",
                "മാതാപിതാക്കൾക്ക് സെഷനിൽ ഇരിക്കാമോ?"
            ]
        else:
            return [
                "പ്രയത്നയിലെ പ്രധാന സേവനങ്ങൾ എന്തൊക്കെയാണ്?",
                "അസസ്സ്മെന്റ് എങ്ങനെ ബുക്ക് ചെയ്യാം?",
                "ഏത് പ്രായത്തിലുള്ള കുട്ടികൾക്കാണ് സഹായം?"
            ]
            
    # Hindi
    elif "hindi" in lang:
        if intent == "appointment_enquiry":
            return [
                "सेंटर का पता और समय क्या है?",
                "असेसमेंट के लिए क्या जानकारी चाहिए?",
                "क्या ऑनलाइन कंसल्टेशन मिल सकता है?"
            ]
        elif intent == "payment_support":
            return [
                "कटे हुए पेमेंट का स्टेटस बताएं",
                "अकाउंट्स टीम से बात करनी है",
                "पेमेंट रसीद कैसे प्राप्त करें?"
            ]
        elif intent == "service_enquiry":
            return [
                "असेसमेंट कैसे बुक करें?",
                "थेरेपी सेशन की फीस कितनी है?",
                "क्या माता-पिता सेशन में रह सकते हैं?"
            ]
        else:
            return [
                "प्रयत्न में कौन-सी थेरेपी उपलब्ध हैं?",
                "असेसमेंट कैसे बुक करें?",
                "किस उम्र के बच्चों के लिए थेरेपी है?"
            ]
            
    # Tamil
    elif "tamil" in lang:
        if intent == "appointment_enquiry":
            return [
                "மையத்தின் முகவரி மற்றும் நேரம் என்ன?",
                "மதிப்பீட்டிற்கு என்ன கொண்டு வர வேண்டும்?",
                "ஆன்லைன் ஆலோசனை கிடைக்குமா?"
            ]
        elif intent == "payment_support":
            return [
                "கட்டண நிலையை சரிபார்க்கவும்",
                "கணக்கு குழுவுடன் பேசவும்",
                "ரசீது எவ்வாறு பெறுவது?"
            ]
        else:
            return [
                "மதிப்பீட்டை எவ்வாறு பதிவு செய்வது?",
                "சிகிச்சை கட்டணங்கள் எவ்வளவு?",
                "என்னென்ன சிகிச்சைகள் வழங்கப்படுகின்றன?"
            ]
            
    # Kannada
    elif "kannada" in lang:
        if intent == "appointment_enquiry":
            return [
                "ಕೇಂದ್ರದ ಸ್ಥಳ ಮತ್ತು ಸಮಯಗಳು ಯಾವುವು?",
                "ಮೌಲ್ಯಮಾಪನಕ್ಕೆ ಏನು ತರಬೇಕು?",
                "ಆನ್‌ಲೈನ್ ಸಮಾಲೋಚನೆ ಲಭ್ಯವಿದೆಯೇ?"
            ]
        elif intent == "payment_support":
            return [
                "ಪಾವತಿ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಿ",
                "ಖಾತೆಗಳ ತಂಡದೊಂದಿಗೆ ಮಾತನಾಡಿ",
                "ರಶೀದಿ ಪಡೆಯುವುದು ಹೇಗೆ?"
            ]
        else:
            return [
                "ಮೌಲ್ಯಮಾಪನವನ್ನು ಹೇಗೆ ಬುಕ್ ಮಾಡುವುದು?",
                "ಥೆರಪಿ ಶುಲ್ಕಗಳು ಎಷ್ಟು?",
                "ಯಾವ ಚಿಕಿತ್ಸೆಗಳು ಲಭ್ಯವಿವೆ?"
            ]
            
    # Telugu
    elif "telugu" in lang:
        if intent == "appointment_enquiry":
            return [
                "సెంటర్ లొకేషన్ మరియు సమయాలు ఏమిటి?",
                "అసెస్మెంట్‌కు ఏమి తీసుకురావాలి?",
                "ఆన్‌లైన్ కన్సల్టేషన్ అందుబాటులో ఉందా?"
            ]
        elif intent == "payment_support":
            return [
                "చెల్లింపు స్థితిని తనిఖీ చేయండి",
                "అకౌంట్స్ బృందంతో మాట్లాడాలి",
                "రసీదు ఎలా పొందాలి?"
            ]
        else:
            return [
                "అసెస్మెంట్‌ను ఎలా బుక్ చేయాలి?",
                "థెరపీ ఫీజుల వివరాలు ఏమిటి?",
                "ఏ థెరపీలు అందుబాటులో ఉన్నాయి?"
            ]
            
    # Default: English
    else:
        if intent == "appointment_enquiry":
            return [
                "What are your center locations & timings?",
                "What should I bring for assessment?",
                "Can we book an online consultation?"
            ]
        elif intent == "payment_support":
            return [
                "Check deducted payment status",
                "Connect with accounts coordinator",
                "What payment methods are supported?"
            ]
        elif intent == "service_enquiry":
            return [
                "How to schedule an assessment?",
                "What are the therapy session charges?",
                "Can parents attend therapy sessions?"
            ]
        else:
            return [
                "What therapies does Prayatna offer?",
                "How to book an assessment?",
                "What age groups do you support?"
            ]

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
