import importlib
import os
import shutil
import tempfile
import unittest
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
