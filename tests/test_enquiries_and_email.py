import importlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient


def _csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


class EnquiriesAndEmailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="test_enq_email_")
        cls.test_db_path = os.path.join(cls.tmp_dir, "test_saas.db")
        cls.test_chroma_dir = os.path.join(cls.tmp_dir, "chroma")
        cls.test_secret_file = os.path.join(cls.tmp_dir, "jwt.key")

        os.environ["DATABASE_URL"] = f"sqlite:///{cls.test_db_path}"
        os.environ["CHROMA_PATH"] = cls.test_chroma_dir
        os.environ["JWT_SECRET_FILE"] = cls.test_secret_file
        os.environ["SUPER_ADMIN_EMAIL"] = "superadmin@testplatform.local"
        os.environ["SUPER_ADMIN_PASSWORD"] = "SuperSecret#2026"
        os.environ["PRAYATNA_ADMIN_EMAIL"] = "admin@prayatna.co.in"
        os.environ["PRAYATNA_ADMIN_PASSWORD"] = "PrayatnaSecret#2026"

        import database
        import models
        import migrations
        import main
        import services.rag
        import services.security
        import services.email_service

        importlib.reload(database)
        importlib.reload(models)
        importlib.reload(services.security)
        importlib.reload(services.email_service)
        importlib.reload(migrations)
        importlib.reload(main)

        cls.main = main
        cls.database = database
        cls.models = models

        migrations.run_migrations()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def setUp(self):
        self.patcher = patch("services.email_service.send_email", return_value=True)
        self.mock_send_email = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _login_admin(self, client: TestClient) -> None:
        res = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(res.status_code, 200)

    def test_create_enquiry_and_export_csv(self):
        """Verify public enquiry creation and subsequent CSV export by admin."""
        client = TestClient(self.main.app)

        # 1. Create enquiry from public widget
        payload = {
            "chatbot_id": "prayatna-bot",
            "parent_name": "Rohan Sharma",
            "email": "rohan.sharma@example.com",
            "phone": "+91 9876543210",
            "child_age": "5 years",
            "interested_service": "Speech Therapy",
            "category": "appointment",
            "description": "Looking for speech evaluation for 5yo child.",
            "preferred_contact": "phone",
        }
        res = client.post("/api/enquiries", json=payload)
        self.assertEqual(res.status_code, 201)
        enq = res.json()
        enquiry_id = enq["id"]
        self.assertEqual(enq["parent_name"], "Rohan Sharma")
        self.assertEqual(enq["status"], "New")

        # 2. Login as admin
        self._login_admin(client)

        # 3. Export CSV
        export_res = client.get("/api/enquiries/export")
        self.assertEqual(export_res.status_code, 200)
        self.assertTrue(export_res.headers.get("content-type", "").startswith("text/csv"))
        self.assertIn("enquiries_export_", export_res.headers.get("content-disposition", ""))

        csv_text = export_res.text
        self.assertIn("Enquiry ID,Captured At (UTC),Visitor Name", csv_text)
        self.assertIn("Rohan Sharma", csv_text)
        self.assertIn("+91 9876543210", csv_text)
        self.assertIn("rohan.sharma@example.com", csv_text)
        self.assertIn("Speech Therapy", csv_text)

    def test_send_enquiry_email(self):
        """Verify sending an email reply to an enquiry updates status and logs details."""
        client = TestClient(self.main.app)

        # 1. Create enquiry with valid email
        res = client.post(
            "/api/enquiries",
            json={
                "chatbot_id": "prayatna-bot",
                "parent_name": "Priya Patel",
                "email": "priya.patel@example.com",
                "phone": "+91 9988776655",
                "interested_service": "Occupational Therapy",
                "category": "service_enquiry",
                "description": "Requesting sensory gym consultation.",
                "preferred_contact": "email",
            },
        )
        self.assertEqual(res.status_code, 201)
        enquiry_id = res.json()["id"]

        # 2. Login as admin
        self._login_admin(client)

        # 3. Send email reply to visitor
        email_payload = {
            "subject": "Re: Occupational Therapy Consultation",
            "body": "Hello Priya, we have slots available this Thursday at 11 AM.",
            "cc_admin": False,
        }
        with patch("routes.enquiries.send_enquiry_reply_email", return_value=True):
            send_res = client.post(
                f"/api/enquiries/{enquiry_id}/send-email",
                json=email_payload,
                headers=_csrf_headers(client),
            )
        self.assertEqual(send_res.status_code, 200)
        send_data = send_res.json()
        self.assertTrue(send_data["success"])
        self.assertEqual(send_data["status"], "Contacted")
        self.assertEqual(send_data["sent_to"], "priya.patel@example.com")

        # 4. Verify enquiry status updated in DB
        detail_res = client.get(f"/api/enquiries/{enquiry_id}")
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertEqual(detail["status"], "Contacted")
        self.assertIn("Re: Occupational Therapy Consultation", detail["description"])

    def test_send_email_rejects_missing_email(self):
        """Verify attempting to send email to an enquiry with no valid email returns 400."""
        client = TestClient(self.main.app)

        # Create enquiry with no email / 'Not provided'
        res = client.post(
            "/api/enquiries",
            json={
                "chatbot_id": "prayatna-bot",
                "parent_name": "Anonymous User",
                "email": "not-an-email",
                "phone": "+91 9123456789",
                "interested_service": "General Enquiry",
                "description": "Phone call only.",
            },
        )
        self.assertEqual(res.status_code, 201)
        enquiry_id = res.json()["id"]

        self._login_admin(client)
        send_res = client.post(
            f"/api/enquiries/{enquiry_id}/send-email",
            json={"subject": "Hello", "body": "Testing"},
            headers=_csrf_headers(client),
        )
        self.assertEqual(send_res.status_code, 400)
        self.assertIn("does not have a valid email", send_res.json()["detail"])

    def test_email_service_configuration_and_test_dispatch(self):
        """Verify getting, saving, and testing business-wide email service settings."""
        client = TestClient(self.main.app)
        self._login_admin(client)

        # 1. Get initial email service config
        res = client.get("/api/admin/email-service")
        self.assertEqual(res.status_code, 200)
        cfg = res.json()
        self.assertIn("enabled", cfg)
        self.assertIn("company_email", cfg)

        # 2. Update email service config with company email & custom provider
        update_payload = {
            "enabled": True,
            "company_email": "leads@prayatna.co.in",
            "additional_emails": ["manager@prayatna.co.in"],
            "provider": "gmail",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "leads@prayatna.co.in",
            "smtp_password": "my-secret-app-password",
            "smtp_encryption": "tls",
            "from_name": "Prayatna Center Leads",
            "from_email": "leads@prayatna.co.in",
        }
        put_res = client.put(
            "/api/admin/email-service",
            json=update_payload,
            headers=_csrf_headers(client),
        )
        self.assertEqual(put_res.status_code, 200)
        saved = put_res.json()
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["company_email"], "leads@prayatna.co.in")
        self.assertEqual(saved["provider"], "gmail")
        self.assertTrue(saved["has_password"])
        self.assertEqual(saved["smtp_password"], "••••••••")

        # 3. Test sending a test email
        with patch("services.email_service.test_smtp_connection", return_value=(True, "Test email delivered successfully.", None)):
            test_res = client.post(
                "/api/admin/email-service/test",
                json={"target_email": "test-admin@prayatna.co.in"},
                headers=_csrf_headers(client),
            )
        self.assertEqual(test_res.status_code, 200)
        test_data = test_res.json()
        self.assertIn("success", test_data)
        self.assertIn("message", test_data)

    def test_strict_phone_validation_on_enquiry_create(self):
        """Verify strict phone number checks (>=10 digits, <=15 digits, non-repeating)."""
        client = TestClient(self.main.app)

        # 1. Invalid: too short (<10 digits)
        short_res = client.post(
            "/api/enquiries",
            json={
                "chatbot_id": "prayatna-bot",
                "parent_name": "Test User",
                "email": "test@example.com",
                "phone": "98765",
                "interested_service": "Speech Therapy",
                "description": "Short phone test",
            },
        )
        self.assertEqual(short_res.status_code, 422)

        # 2. Invalid: repeated single digits (e.g. 0000000000 or 1111111111)
        repeated_res = client.post(
            "/api/enquiries",
            json={
                "chatbot_id": "prayatna-bot",
                "parent_name": "Test User",
                "email": "test@example.com",
                "phone": "0000000000",
                "interested_service": "Speech Therapy",
                "description": "Repeated phone test",
            },
        )
        self.assertEqual(repeated_res.status_code, 422)

        # 3. Valid 10-digit mobile
        valid_res = client.post(
            "/api/enquiries",
            json={
                "chatbot_id": "prayatna-bot",
                "parent_name": "Anita Roy",
                "email": "anita@example.com",
                "phone": "+91 98450 12345",
                "interested_service": "Developmental Assessment",
                "description": "Valid phone test",
            },
        )
        self.assertEqual(valid_res.status_code, 201)
        self.assertEqual(valid_res.json()["phone"], "+91 98450 12345")

    def test_phone_extractor_and_prompt_contact_memory(self):
        """Verify extraction rejects dates/repeats, and prompts prevent re-asking for contact details."""
        from services.gemini import is_valid_phone_candidate, extract_lead_info, gemini_service

        # 1. Date should NOT be considered a phone candidate
        self.assertFalse(is_valid_phone_candidate("2026-11-27"))
        self.assertFalse(is_valid_phone_candidate("1111111111"))
        self.assertFalse(is_valid_phone_candidate("12345"))
        self.assertTrue(is_valid_phone_candidate("+91 9876543210"))
        self.assertTrue(is_valid_phone_candidate("9876543210"))

        # 2. Lead extraction from conversation text
        lead = extract_lead_info("Hello, my name is Rahul and my phone number is +91 9876543210")
        self.assertEqual(lead.get("phone"), "+91 9876543210")
        self.assertEqual(lead.get("parent_name"), "Rahul")

        # 3. Prompt building when contact info is captured vs not captured
        prompt_with_contact, _ = gemini_service._build_full_prompt(
            user_message="What are your operating hours?",
            retrieved_chunks=[],
            conversation_history=[],
            organization_name="Right Logistics",
            contact_info_captured={"parent_name": "Rahul", "phone": "+91 9876543210"},
        )
        self.assertIn("VISITOR CONTACT DETAILS ALREADY REGISTERED", prompt_with_contact)
        self.assertIn("NEVER ask the visitor for their phone number", prompt_with_contact)

        prompt_without_contact, _ = gemini_service._build_full_prompt(
            user_message="What are your operating hours?",
            retrieved_chunks=[],
            conversation_history=[],
            organization_name="Right Logistics",
            contact_info_captured=None,
        )
        self.assertNotIn("VISITOR CONTACT DETAILS ALREADY REGISTERED", prompt_without_contact)

    def test_smtp_sender_domain_alignment_and_lead_alert_dispatch(self):
        """Verify that when smtp_user and from_email have mismatched domains (e.g. Zoho relay rule),
        the sender email automatically normalizes to the authenticated user to prevent 550 relay errors,
        and dispatch_lead_alert delivers to company_email without dropping the lead."""
        from services.email_service import resolve_org_smtp_config, dispatch_lead_alert

        # 1. Config with mismatched from_email (e.g. company domain vs Zoho account)
        raw_cfg = {
            "provider": "zoho",
            "smtp_host": "smtp.zoho.in",
            "smtp_port": 465,
            "smtp_encryption": "ssl",
            "smtp_user": "sales@growyourbusiness.today",
            "smtp_password": "app-password-123",
            "from_name": "Right Logistics",
            "from_email": "prince@rightlogistics.in",
            "company_email": "prince@rightlogistics.in",
            "enabled": True,
        }
        resolved = resolve_org_smtp_config(raw_cfg)
        self.assertEqual(resolved["from_email"], "sales@growyourbusiness.today")
        self.assertEqual(resolved["from_name"], "Right Logistics")

        # 2. Test lead alert dispatch
        client = TestClient(self.main.app)
        db = self.database.SessionLocal()
        try:
            org = db.query(self.models.Organization).filter(self.models.Organization.slug == "prayatna").first()
            import json
            org.email_config_json = json.dumps(raw_cfg)
            db.commit()

            with patch("services.email_service.send_email", return_value=True) as mock_send:
                lead_data = {
                    "id": "lead-123",
                    "parent_name": "Amit Kumar",
                    "phone": "+91 9876543210",
                    "email": "amit@example.com",
                    "interested_service": "Air Freight",
                    "description": "Shipping rate request",
                }
                dispatch_lead_alert(db, org.id, lead_data, source_label="unit test")

                import time
                time.sleep(0.1)  # Allow daemon thread to run
                self.assertTrue(mock_send.called)
                args, kwargs = mock_send.call_args
                self.assertEqual(kwargs.get("to_email"), "prince@rightlogistics.in")
                self.assertEqual(kwargs.get("from_name"), "Right Logistics")
                self.assertEqual(kwargs.get("smtp_config")["from_email"], "sales@growyourbusiness.today")
        finally:
            db.close()


