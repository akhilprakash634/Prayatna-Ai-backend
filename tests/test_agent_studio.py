import base64
import importlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


class AgentStudioRequirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="agent_studio_req_")
        cls.test_db_path = os.path.join(cls.tmp_dir, "prayatna.db")
        cls.test_chroma_dir = os.path.join(cls.tmp_dir, "chroma")
        cls.test_secret_file = os.path.join(cls.tmp_dir, ".jwt_secret")

        shutil.copy2(BACKEND_DIR / "data" / "prayatna.db", cls.test_db_path)
        shutil.copytree(
            BACKEND_DIR / "data" / "chroma",
            cls.test_chroma_dir,
            ignore=shutil.ignore_patterns("prayatna"),
        )

        conn = sqlite3.connect(cls.test_db_path)
        try:
            for tbl in (
                "audit_logs",
                "account_setup_tokens",
                "usage_logs",
                "subscriptions",
                "chatbot_settings",
                "agent_settings",
                "conversation_flows",
                "users",
                "organizations",
            ):
                conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            conn.commit()
        finally:
            conn.close()

        os.environ["DATABASE_URL"] = f"sqlite:///{cls.test_db_path}"
        os.environ["CHROMA_PATH"] = cls.test_chroma_dir
        os.environ["JWT_SECRET_FILE"] = cls.test_secret_file
        os.environ["SUPER_ADMIN_EMAIL"] = "superadmin@testplatform.local"
        os.environ["SUPER_ADMIN_PASSWORD"] = "SuperSecret#2026"
        os.environ["PRAYATNA_ADMIN_EMAIL"] = "admin@prayatna.co.in"
        os.environ["PRAYATNA_ADMIN_PASSWORD"] = "PrayatnaSecret#2026"
        os.environ["PUBLIC_CHAT_RATE_LIMIT"] = "100"

        import database
        import models
        import services.gemini
        import services.rag
        import services.security
        import migrations
        import main

        importlib.reload(database)
        importlib.reload(models)
        services.rag.rag_service.set_base_path(cls.test_chroma_dir)
        importlib.reload(services.gemini)
        importlib.reload(services.security)
        importlib.reload(migrations)
        importlib.reload(main)

        cls.main = main
        cls.database = database
        cls.models = models
        cls.rag_service = services.rag.rag_service
        cls.gemini_service = services.gemini.gemini_service

        migrations.run_migrations()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _login_client(self, email="admin@prayatna.co.in", password="PrayatnaSecret#2026") -> TestClient:
        client = TestClient(self.main.app)
        res = client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200, f"Login failed: {res.text}")
        return client

    def _login_super_admin(self) -> TestClient:
        client = TestClient(self.main.app)
        res = client.post("/api/auth/super-admin/login", json={"email": "superadmin@testplatform.local", "password": "SuperSecret#2026"})
        self.assertEqual(res.status_code, 200, f"SuperAdmin Login failed: {res.text}")
        return client

    # TEST 1: Configure agent as Friendly with Short responses
    def test_01_friendly_short_responses(self):
        client = self._login_client()
        update_payload = {
            "agent_name": "Sarah Friendly",
            "personality": ["Friendly", "Empathetic"],
            "tone": "Friendly",
            "attitude": "Helpful",
            "response_length": "short",
            "communication_style": "conversational",
        }
        res = client.put("/api/agent/settings", json=update_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["tone"], "Friendly")
        self.assertEqual(data["response_length"], "short")

        # Test prompt engine output
        prompt, _ = self.gemini_service._build_agent_studio_prompt(
            agent_config=data,
            user_message="Hello, what therapies do you provide?",
            retrieved_chunks=[],
            conversation_history=[],
        )
        self.assertIn("Tone: Friendly", prompt)
        self.assertIn("1 to 2 sentences (approx 20 to 45 words maximum)", prompt)

    # TEST 2: Configure agent as Professional with Detailed responses
    def test_02_professional_detailed_responses(self):
        client = self._login_client()
        update_payload = {
            "agent_name": "Dr. Eleanor",
            "personality": ["Professional", "Formal"],
            "tone": "Professional",
            "attitude": "Confident",
            "response_length": "detailed",
            "communication_style": "explanatory",
        }
        res = client.put("/api/agent/settings", json=update_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["tone"], "Professional")
        self.assertEqual(data["response_length"], "detailed")

        # Test prompt engine output
        prompt, _ = self.gemini_service._build_agent_studio_prompt(
            agent_config=data,
            user_message="Explain your occupational therapy sensory gym equipment.",
            retrieved_chunks=[],
            conversation_history=[],
        )
        self.assertIn("Tone: Professional", prompt)
        self.assertIn("3 to 6 sentences (approx 80 to 150 words)", prompt)

    # TEST 3: Change welcome message
    def test_03_change_welcome_message(self):
        client = self._login_client()
        new_welcome = "Welcome to Prayatna Pediatric Hub! Sarah is ready to guide you."
        update_payload = {
            "welcome_config": {
                "welcome_message": new_welcome,
                "agent_intro": "I'm Sarah, your pediatric guide.",
                "greeting_style": "Friendly",
                "initial_behaviour": "welcome_and_suggestions",
                "suggested_questions": [
                    {"id": "q1", "text": "Book an assessment slot", "enabled": True}
                ],
            }
        }
        res = client.put("/api/agent/settings", json=update_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)

        # Activate to reflect in production
        act_res = client.post("/api/agent/activate", headers=_csrf_headers(client))
        self.assertEqual(act_res.status_code, 200)

        # Verify public config returns new welcome message
        pub_res = client.get("/api/chat/config?bot=prayatna-bot")
        self.assertEqual(pub_res.status_code, 200)
        self.assertEqual(pub_res.json()["welcome_message"], new_welcome)
        self.assertIn("Book an assessment slot", pub_res.json()["theme_config"]["starter_prompts"])

    # TEST 4: Configure Malayalam as preferred language
    def test_04_malayalam_preferred_language(self):
        client = self._login_client()
        update_payload = {
            "language_preference": "Malayalam",
        }
        res = client.put("/api/agent/settings", json=update_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["language_preference"], "Malayalam")

        prompt, _ = self.gemini_service._build_agent_studio_prompt(
            agent_config=data,
            user_message="What is the center timing?",
            retrieved_chunks=[],
            conversation_history=[],
        )
        self.assertIn("MANDATORY RESPONSE LANGUAGE: MALAYALAM", prompt)

    # TEST 5: Disable follow-up questions
    def test_05_disable_follow_up_questions(self):
        client = self._login_client()
        update_payload = {
            "behaviour_config": {
                "ask_followup_questions": False,
                "suggest_services": True,
                "proactive_guidance": False,
                "collect_customer_info": True,
                "offer_human_assistance": False,
                "ask_clarification": False,
                "avoid_repetition": True,
                "recommend_services": False,
                "confirm_before_enquiry": False,
                "escalate_issues": False,
                "fallback_action": "acknowledge",
            }
        }
        res = client.put("/api/agent/settings", json=update_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["behaviour_config"]["ask_followup_questions"])

        prompt, _ = self.gemini_service._build_agent_studio_prompt(
            agent_config=data,
            user_message="Do you provide speech therapy?",
            retrieved_chunks=[],
            conversation_history=[],
        )
        self.assertIn("Do NOT ask unsolicited follow-up questions", prompt)

    # TEST 6: Enable customer information collection
    def test_06_enable_customer_info_collection(self):
        client = self._login_client()
        update_payload = {
            "behaviour_config": {
                "ask_followup_questions": True,
                "collect_customer_info": True,
                "suggest_services": True,
                "proactive_guidance": True,
                "offer_human_assistance": True,
                "ask_clarification": True,
                "avoid_repetition": True,
                "recommend_services": True,
                "confirm_before_enquiry": True,
                "escalate_issues": True,
                "fallback_action": "acknowledge",
            }
        }
        res = client.put("/api/agent/settings", json=update_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)
        client.post("/api/agent/activate", headers=_csrf_headers(client))

        # Test live chat endpoint creates lead enquiry
        test_client = TestClient(self.main.app)
        chat_res = test_client.post(
            "/api/chat",
            json={
                "chatbot_id": "prayatna-bot",
                "message": "My name is John Doe, phone: +91 9876543210, I want to book an assessment for my 5 year old child.",
            },
        )
        self.assertEqual(chat_res.status_code, 200)
        chat_data = chat_res.json()
        self.assertIsNotNone(chat_data.get("enquiry_captured"))
        self.assertEqual(chat_data["enquiry_captured"]["parent_name"], "John Doe")
        self.assertEqual(chat_data["enquiry_captured"]["phone"], "+91 9876543210")

    # TEST 7: Test appointment enquiry
    def test_07_appointment_enquiry_workflow(self):
        test_client = TestClient(self.main.app)
        chat_res = test_client.post(
            "/api/chat",
            json={
                "chatbot_id": "prayatna-bot",
                "message": "I would like to schedule an appointment with a developmental pediatrician.",
            },
        )
        self.assertEqual(chat_res.status_code, 200)
        chat_data = chat_res.json()
        self.assertEqual(chat_data["intent"], "appointment_enquiry")
        self.assertTrue(chat_data["requires_followup"])

    # TEST 8: Test payment troubleshooting
    def test_08_payment_troubleshooting_workflow(self):
        test_client = TestClient(self.main.app)
        chat_res = test_client.post(
            "/api/chat",
            json={
                "chatbot_id": "prayatna-bot",
                "message": "Money was deducted from my account but transaction failed. Need refund or receipt.",
            },
        )
        self.assertEqual(chat_res.status_code, 200)
        chat_data = chat_res.json()
        self.assertEqual(chat_data["intent"], "payment_support")
        self.assertTrue(chat_data["requires_followup"])

    # TEST 9: Test RAG knowledge retrieval
    def test_09_rag_retrieves_organization_knowledge(self):
        chunks = self.rag_service.query("occupational therapy sensory gym", top_k=3, org_slug="prayatna", collection_name="org_prayatna")
        self.assertGreaterEqual(len(chunks), 1)
        first_chunk = chunks[0]
        self.assertIn("content", first_chunk)
        self.assertIn("sensory", first_chunk["content"].lower())

    # TEST 10: Test multiple organizations with independent Agent Studio settings
    def test_10_multiple_organizations_isolation(self):
        super_client = self._login_super_admin()
        # Create second organization
        create_org_res = super_client.post(
            "/api/super-admin/clients",
            json={
                "organization_name": "Zenith Speech Academy",
                "organization_slug": "zenith-speech",
                "admin_name": "Zenith Admin",
                "admin_email": "admin@zenith.local",
                "subscription_plan": "Enterprise",
            },
            headers=_csrf_headers(super_client),
        )
        self.assertEqual(create_org_res.status_code, 201)
        zenith_org_id = create_org_res.json()["organization"]["id"]

        # Impersonate Zenith
        super_client.post(f"/api/super-admin/clients/{zenith_org_id}/impersonate", headers=_csrf_headers(super_client))

        # Configure Zenith Agent
        zenith_settings = {
            "agent_name": "Max Zenith",
            "agent_role": "Senior Speech Consultant",
            "tone": "Persuasive",
            "response_length": "detailed",
        }
        up_res = super_client.put("/api/agent/settings", json=zenith_settings, headers=_csrf_headers(super_client))
        self.assertEqual(up_res.status_code, 200)
        self.assertEqual(up_res.json()["agent_name"], "Max Zenith")

        # Verify Prayatna agent remains Sarah
        prayatna_client = self._login_client()
        p_data = prayatna_client.get("/api/agent/settings").json()
        self.assertEqual(p_data["agent_name"], "Dr. Eleanor")  # from test 2

    # TEST 11: Test draft preview without modifying production or creating real leads
    def test_11_preview_draft_without_production_side_effects(self):
        client = self._login_client()
        db = self.database.SessionLocal()
        conv_count_before = db.query(self.models.Conversation).count()
        enq_count_before = db.query(self.models.Enquiry).count()
        db.close()

        preview_payload = {
            "message": "My name is Jane Doe, phone: +91 9998887776, looking for speech therapy.",
            "conversation_history": [],
            "draft_settings": {
                "agent_name": "Temporary Draft Agent",
                "tone": "Warm",
                "response_length": "short",
            },
        }
        res = client.post("/api/agent/preview", json=preview_payload, headers=_csrf_headers(client))
        self.assertEqual(res.status_code, 200)
        self.assertIn("message", res.json())

        db2 = self.database.SessionLocal()
        conv_count_after = db2.query(self.models.Conversation).count()
        enq_count_after = db2.query(self.models.Enquiry).count()
        db2.close()

        self.assertEqual(conv_count_before, conv_count_after)
        self.assertEqual(enq_count_before, enq_count_after)

    # TEST 12: Test backward compatibility (fallback to default system prompt when agent studio unconfigured/inactive)
    def test_12_backward_compatibility_unconfigured_organization(self):
        # When agent_config is None, _build_full_prompt returns the default system prompt
        legacy_prompt, org_label = self.gemini_service._build_full_prompt(
            user_message="Tell me about your services",
            retrieved_chunks=[],
            conversation_history=[],
            organization_name="Prayatna Centre for Child Development",
            organization_slug="prayatna",
            agent_config=None,  # Unconfigured / legacy
        )
        self.assertIn("Prayatna Centre for Child Development", legacy_prompt)
        self.assertIn("ORGANIZATIONAL KNOWLEDGE RETRIEVED", legacy_prompt)
        self.assertNotIn("=== LAYER 4: AGENT IDENTITY & CHARACTER ===", legacy_prompt)


if __name__ == "__main__":
    unittest.main()
