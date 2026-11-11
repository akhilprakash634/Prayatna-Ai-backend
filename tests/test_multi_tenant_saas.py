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


class MultiTenantSaaSAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="saas_acceptance_")
        cls.test_db_path = os.path.join(cls.tmp_dir, "prayatna.db")
        cls.test_chroma_dir = os.path.join(cls.tmp_dir, "chroma")
        cls.test_secret_file = os.path.join(cls.tmp_dir, ".jwt_secret")

        shutil.copy2(BACKEND_DIR / "data" / "prayatna.db", cls.test_db_path)
        shutil.copytree(
            BACKEND_DIR / "data" / "chroma",
            cls.test_chroma_dir,
            ignore=shutil.ignore_patterns("prayatna"),
        )

        # Reset the copied SQLite snapshot to pre-SaaS state while keeping all real Prayatna rows
        conn = sqlite3.connect(cls.test_db_path)
        try:
            for tbl in (
                "audit_logs",
                "account_setup_tokens",
                "usage_logs",
                "subscriptions",
                "chatbot_settings",
                "users",
                "organizations",
            ):
                conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            for tbl in ("conversations", "messages", "enquiries", "knowledge_documents"):
                cols = {row[1] for row in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
                if "organization_id" in cols:
                    conn.execute(f"UPDATE {tbl} SET organization_id = NULL")
                if tbl == "conversations" and "chatbot_id" in cols:
                    conn.execute("UPDATE conversations SET chatbot_id = NULL")
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
        os.environ["PUBLIC_CHAT_RATE_LIMIT"] = "25"

        import database
        import models
        import services.rag
        import services.security
        import migrations
        import main

        importlib.reload(database)
        importlib.reload(models)
        services.rag.rag_service.set_base_path(cls.test_chroma_dir)
        importlib.reload(services.security)
        importlib.reload(migrations)
        importlib.reload(main)

        cls.main = main
        cls.database = database
        cls.models = models
        cls.rag_service = services.rag.rag_service
        cls.security = services.security

        # Verify migration idempotency right away
        cls.mig_1 = migrations.run_migrations()
        cls.mig_2 = migrations.run_migrations()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _new_client(self) -> TestClient:
        return TestClient(self.main.app)

    def test_full_multi_tenant_saas_acceptance_workflow(self):
        self.security.public_chat_rate_limiter.reset()

        # ------------------------------------------------------------------
        # 1. Verify Legacy Prayatna Data Migration & Idempotency
        # ------------------------------------------------------------------
        db = self.database.SessionLocal()
        try:
            prayatna = db.query(self.models.Organization).filter_by(slug="prayatna").first()
            self.assertIsNotNone(prayatna)
            conv_count = db.query(self.models.Conversation).filter_by(organization_id=prayatna.id).count()
            msg_count = db.query(self.models.Message).filter_by(organization_id=prayatna.id).count()
            enq_count = db.query(self.models.Enquiry).filter_by(organization_id=prayatna.id).count()
            doc_count = db.query(self.models.KnowledgeDocument).filter_by(organization_id=prayatna.id).count()

            self.assertGreaterEqual(conv_count, 6)
            self.assertGreaterEqual(msg_count, 20)
            self.assertGreaterEqual(enq_count, 1)
            self.assertGreaterEqual(doc_count, 8)
            self.assertEqual(self.mig_1["migrated_vectors"], 16)
            self.assertEqual(self.mig_2["migrated_vectors"], 16)
        finally:
            db.close()

        stats = self.rag_service.get_stats(org_slug="prayatna", collection_name="org_prayatna")
        self.assertEqual(stats["total_chunks"], 16)

        # ------------------------------------------------------------------
        # 2. Verify Unauthenticated & Tampered JWT / CSRF Protections
        # ------------------------------------------------------------------
        anon = self._new_client()
        self.assertEqual(anon.get("/api/conversations").status_code, 401)
        self.assertEqual(anon.get("/api/enquiries").status_code, 401)
        self.assertEqual(anon.get("/api/knowledge/documents").status_code, 401)
        self.assertEqual(anon.get("/api/super-admin/dashboard").status_code, 401)

        # Reject JWT with alg=none
        none_hdr = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        none_pay = base64.urlsafe_b64encode(json.dumps({"sub": "fake", "exp": 9999999999}).encode()).rstrip(b"=").decode()
        self.assertEqual(
            anon.get("/api/auth/me", headers={"Authorization": f"Bearer {none_hdr}.{none_pay}."}).status_code,
            401,
        )

        # ------------------------------------------------------------------
        # 3. Super Admin Login & Creating Second Organization (ABC Clinic)
        # ------------------------------------------------------------------
        super_client = self._new_client()
        sa_login = super_client.post(
            "/api/auth/super-admin/login",
            json={"email": "superadmin@testplatform.local", "password": "SuperSecret#2026"},
        )
        self.assertEqual(sa_login.status_code, 200, sa_login.text)
        self.assertIn("sa_session", super_client.cookies)
        self.assertIn("csrf_token", super_client.cookies)

        # Mutating call without X-CSRF-Token must fail with 403
        no_csrf = super_client.post(
            "/api/super-admin/clients",
            json={
                "organization_name": "Should Fail",
                "organization_slug": "should-fail",
                "admin_name": "No Csrf",
                "admin_email": "nocsrf@example.com",
                "subscription_plan": "Basic",
                "account_status": "active",
            },
        )
        self.assertEqual(no_csrf.status_code, 403)

        # Create ABC Clinic with invited status (onboarding via one-time setup token)
        create_abc = super_client.post(
            "/api/super-admin/clients",
            headers=_csrf_headers(super_client),
            json={
                "organization_name": "ABC Clinic",
                "organization_slug": "abc-clinic",
                "admin_name": "Dr. Meera Nair",
                "admin_email": "admin@abcclinic.com",
                "phone": "+91 90000 11111",
                "website": "https://abcclinic.example",
                "industry": "Healthcare / Dental",
                "subscription_plan": "Basic",
                "account_status": "active",
            },
        )
        self.assertEqual(create_abc.status_code, 201, create_abc.text)
        abc_payload = create_abc.json()
        abc_org_id = abc_payload["organization"]["id"]
        abc_bot_id = abc_payload["organization"]["chatbot"]["chatbot_id"]
        setup_link = abc_payload["setup_link"]
        setup_token = setup_link.split("token=")[1]
        self.assertTrue(os.path.isdir(os.path.join(self.test_chroma_dir, "abc-clinic")))

        # Complete ABC admin onboarding via single-use setup token
        setup_res = anon.post(
            "/api/auth/setup-account",
            json={"token": setup_token, "new_password": "AbcInitial#2026"},
        )
        self.assertEqual(setup_res.status_code, 200, setup_res.text)
        # Replaying setup token must fail
        replay_res = anon.post(
            "/api/auth/setup-account",
            json={"token": setup_token, "new_password": "Another#2026"},
        )
        self.assertEqual(replay_res.status_code, 400)

        # ------------------------------------------------------------------
        # 4. Separate Organization Logins (Prayatna & ABC Clinic)
        # ------------------------------------------------------------------
        prayatna_client = self._new_client()
        p_login = prayatna_client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(p_login.status_code, 200, p_login.text)
        self.assertEqual(p_login.json()["organization"]["slug"], "prayatna")

        # Client admin must NOT access super-admin routes
        self.assertEqual(prayatna_client.get("/api/super-admin/dashboard").status_code, 403)

        abc_client = self._new_client()
        a_login = abc_client.post(
            "/api/auth/login",
            json={"email": "admin@abcclinic.com", "password": "AbcInitial#2026"},
        )
        self.assertEqual(a_login.status_code, 200, a_login.text)
        self.assertEqual(a_login.json()["organization"]["slug"], "abc-clinic")

        p_convs = prayatna_client.get("/api/conversations").json()
        p_enqs = prayatna_client.get("/api/enquiries").json()
        p_docs = prayatna_client.get("/api/knowledge/documents").json()
        self.assertGreaterEqual(len(p_convs), 6)
        self.assertGreaterEqual(len(p_enqs), 1)
        self.assertGreaterEqual(len(p_docs), 8)

        # ABC starts completely clean
        self.assertEqual(abc_client.get("/api/conversations").json(), [])
        self.assertEqual(abc_client.get("/api/enquiries").json(), [])
        self.assertEqual(abc_client.get("/api/knowledge/documents").json(), [])

        # ------------------------------------------------------------------
        # 5. Isolated Knowledge Upload & RAG Isolation
        # ------------------------------------------------------------------
        abc_doc_bytes = (
            b"ABC Dental & Ortho Exclusive Protocol XYZ-9918. "
            b"ABC Clinic specializes in clear aligners and painless root canals in Kochi. "
            b"Clinic timing is 8 AM to 8 PM daily."
        )
        abc_upload = abc_client.post(
            "/api/knowledge/upload",
            headers=_csrf_headers(abc_client),
            files={"file": ("abc_protocol.txt", abc_doc_bytes, "text/plain")},
        )
        self.assertEqual(abc_upload.status_code, 200, abc_upload.text)
        abc_doc_id = abc_upload.json()["id"]

        # ABC RAG test finds ABC content, NEVER Prayatna content
        abc_rag = abc_client.post(
            "/api/knowledge/test",
            headers=_csrf_headers(abc_client),
            json={"query": "Prayatna Sensory Integration gyms speech therapy"},
        )
        self.assertEqual(abc_rag.status_code, 200)
        abc_contents = " ".join(r["content"] for r in abc_rag.json()["results"])
        self.assertNotIn("Prayatna", abc_contents)

        # Prayatna RAG test finds Prayatna content, NEVER ABC secret
        p_rag = prayatna_client.post(
            "/api/knowledge/test",
            headers=_csrf_headers(prayatna_client),
            json={"query": "ABC Dental Ortho Exclusive Protocol XYZ-9918"},
        )
        self.assertEqual(p_rag.status_code, 200)
        p_contents = " ".join(r["content"] for r in p_rag.json()["results"])
        self.assertNotIn("XYZ-9918", p_contents)
        self.assertNotIn("clear aligners", p_contents)

        # ------------------------------------------------------------------
        # 6. Public Chat, Branding, Lead Capture & Cross-Tenant 403 Checks
        # ------------------------------------------------------------------
        upd_bot = abc_client.patch(
            "/api/admin/chatbot",
            headers=_csrf_headers(abc_client),
            json={
                "bot_name": "ABC Care Concierge",
                "assistant_name": "Maya",
                "primary_color": "#2563eb",
            },
        )
        self.assertEqual(upd_bot.status_code, 200, upd_bot.text)

        abc_pub_cfg = anon.get(f"/api/chat/config?bot={abc_bot_id}").json()
        p_pub_cfg = anon.get("/api/chat/config").json()
        self.assertEqual(abc_pub_cfg["bot_name"], "ABC Care Concierge")
        self.assertEqual(abc_pub_cfg["primary_color"], "#2563eb")
        self.assertEqual(p_pub_cfg["organization_slug"], "prayatna")

        # Public chat + automatic lead capture for ABC Clinic
        abc_chat = anon.post(
            "/api/chat",
            json={
                "chatbot_id": abc_bot_id,
                "message": "My name is Vikram, phone +91 9988776655, want clear aligners info.",
                "language": "English",
            },
        )
        self.assertEqual(abc_chat.status_code, 200, abc_chat.text)
        abc_conv_id = abc_chat.json()["conversation_id"]
        self.assertIsNotNone(abc_chat.json()["enquiry_captured"])

        # Visible to ABC, invisible to Prayatna
        abc_enqs_after = abc_client.get("/api/enquiries").json()
        self.assertEqual(len(abc_enqs_after), 1)
        abc_enq_id = abc_enqs_after[0]["id"]
        self.assertTrue(all(e["id"] != abc_enq_id for e in prayatna_client.get("/api/enquiries").json()))

        # Cross-tenant HTTP 403 checks (ABC tries Prayatna resources & vice versa)
        p_conv_id = p_convs[0]["id"]
        p_enq_id = p_enqs[0]["id"]
        p_doc_id = p_docs[0]["id"]

        self.assertEqual(abc_client.get(f"/api/conversations/{p_conv_id}").status_code, 403)
        self.assertEqual(abc_client.get(f"/api/conversations/{p_conv_id}/messages").status_code, 403)
        self.assertEqual(abc_client.get(f"/api/enquiries/{p_enq_id}").status_code, 403)
        self.assertEqual(
            abc_client.patch(
                f"/api/enquiries/{p_enq_id}",
                headers=_csrf_headers(abc_client),
                json={"status": "Resolved"},
            ).status_code,
            403,
        )
        self.assertEqual(
            abc_client.delete(
                f"/api/knowledge/documents/{p_doc_id}",
                headers=_csrf_headers(abc_client),
            ).status_code,
            403,
        )
        self.assertEqual(
            anon.post(
                "/api/chat",
                json={"chatbot_id": abc_bot_id, "conversation_id": p_conv_id, "message": "Hijack attempt"},
            ).status_code,
            403,
        )

        # Prayatna admin cannot read ABC resources either
        self.assertEqual(prayatna_client.get(f"/api/conversations/{abc_conv_id}").status_code, 403)
        self.assertEqual(prayatna_client.get(f"/api/enquiries/{abc_enq_id}").status_code, 403)
        self.assertEqual(
            prayatna_client.delete(
                f"/api/knowledge/documents/{abc_doc_id}",
                headers=_csrf_headers(prayatna_client),
            ).status_code,
            403,
        )

        # ------------------------------------------------------------------
        # 7. Organization Suspension & Reactivation
        # ------------------------------------------------------------------
        suspend_res = super_client.post(
            f"/api/super-admin/clients/{abc_org_id}/suspend",
            headers=_csrf_headers(super_client),
        )
        self.assertEqual(suspend_res.status_code, 200)
        self.assertEqual(suspend_res.json()["status"], "suspended")

        # Chatbot stops accepting chats & config reports unavailable
        self.assertEqual(
            anon.post(
                "/api/chat",
                json={"chatbot_id": abc_bot_id, "message": "Are you open?"},
            ).status_code,
            403,
        )
        self.assertFalse(anon.get(f"/api/chat/config?bot={abc_bot_id}").json()["is_available"])

        # ABC Admin login and dashboard endpoints are blocked
        self.assertEqual(
            self._new_client()
            .post("/api/auth/login", json={"email": "admin@abcclinic.com", "password": "AbcInitial#2026"})
            .status_code,
            403,
        )
        self.assertEqual(abc_client.get("/api/conversations").status_code, 403)

        # Reactivate restores access and preserves existing records
        activate_res = super_client.post(
            f"/api/super-admin/clients/{abc_org_id}/activate",
            headers=_csrf_headers(super_client),
        )
        self.assertEqual(activate_res.status_code, 200)
        self.assertEqual(activate_res.json()["status"], "active")
        self.assertTrue(anon.get(f"/api/chat/config?bot={abc_bot_id}").json()["is_available"])
        self.assertEqual(len(abc_client.get("/api/conversations").json()), 1)

        # ------------------------------------------------------------------
        # 8. Super Admin Platform Stats & Audited Impersonation
        # ------------------------------------------------------------------
        sa_stats = super_client.get("/api/super-admin/dashboard").json()
        self.assertGreaterEqual(sa_stats["total_organizations"], 2)
        self.assertGreaterEqual(sa_stats["total_ai_requests"], 1)

        imp_res = super_client.post(
            f"/api/super-admin/clients/{abc_org_id}/impersonate",
            headers=_csrf_headers(super_client),
        )
        self.assertEqual(imp_res.status_code, 200, imp_res.text)
        self.assertTrue(imp_res.json()["is_impersonating"])

        # While impersonating ABC, Super Admin sees ABC conversations but cannot call super-admin endpoints
        imp_convs = super_client.get("/api/conversations").json()
        self.assertEqual(len(imp_convs), 1)
        self.assertEqual(imp_convs[0]["id"], abc_conv_id)
        self.assertEqual(super_client.get("/api/super-admin/clients").status_code, 403)

        # Exit impersonation cleanly restores Super Admin access
        exit_res = super_client.post(
            "/api/super-admin/exit-impersonation",
            headers=_csrf_headers(super_client),
        )
        self.assertEqual(exit_res.status_code, 200)
        self.assertFalse(exit_res.json()["is_impersonating"])
        self.assertEqual(super_client.get("/api/super-admin/clients").status_code, 200)

        audit_actions = [a["action"] for a in super_client.get(f"/api/super-admin/audit-logs?organization_id={abc_org_id}").json()]
        self.assertIn("impersonate_start", audit_actions)
        self.assertIn("impersonate_end", audit_actions)

        # ------------------------------------------------------------------
        # 9. Subscription Quota Limit & Credential Reset + Token Revocation
        # ------------------------------------------------------------------
        sub_tight = super_client.patch(
            f"/api/super-admin/clients/{abc_org_id}/subscription",
            headers=_csrf_headers(super_client),
            json={"plan_name": "Basic", "conversation_limit": 1, "ai_usage_limit": 100},
        )
        self.assertEqual(sub_tight.status_code, 200)
        # New conversation must be blocked with 429
        self.assertEqual(
            anon.post("/api/chat", json={"chatbot_id": abc_bot_id, "message": "Second conv blocked"}).status_code,
            429,
        )

        # Reset credentials -> bumps token_version -> existing abc_client cookie invalidated!
        reset_res = super_client.post(
            f"/api/super-admin/clients/{abc_org_id}/reset-credentials",
            headers=_csrf_headers(super_client),
            json={"new_password": "AbcRotated#2026"},
        )
        self.assertEqual(reset_res.status_code, 200)
        self.assertEqual(abc_client.get("/api/conversations").status_code, 401)

        # ------------------------------------------------------------------
        # 10. Safe Organization Deletion & Public Rate Limit Check
        # ------------------------------------------------------------------
        # Without force=true, delete fails with 409 because ABC has data
        self.assertEqual(
            super_client.request(
                "DELETE",
                f"/api/super-admin/clients/{abc_org_id}",
                headers=_csrf_headers(super_client),
                json={"confirm_slug": "abc-clinic", "force": False},
            ).status_code,
            409,
        )
        # With matching confirm_slug and force=true, deletes org + Chroma folder
        del_res = super_client.request(
            "DELETE",
            f"/api/super-admin/clients/{abc_org_id}",
            headers=_csrf_headers(super_client),
            json={"confirm_slug": "abc-clinic", "force": True},
        )
        self.assertEqual(del_res.status_code, 200, del_res.text)
        self.assertFalse(os.path.exists(os.path.join(self.test_chroma_dir, "abc-clinic")))

        # Prayatna records remain completely intact after ABC deletion
        self.assertGreaterEqual(len(prayatna_client.get("/api/conversations").json()), 6)
        self.assertGreaterEqual(len(prayatna_client.get("/api/knowledge/documents").json()), 8)

        # Public rate limiting triggers 429 after burst
        self.security.public_chat_rate_limiter.reset()
        statuses = [
            anon.post("/api/chat", json={"message": "Rate limit ping"}).status_code
            for _ in range(27)
        ]
        self.assertIn(429, statuses)

    def test_spa_scraper_ssrf_and_manual_text_knowledge(self):
        from unittest.mock import MagicMock, patch
        from bs4 import BeautifulSoup
        from services.scraper import WebsiteScraper, _extract_internal_links, _looks_like_spa_shell, clean_html_content, SpaScrapeError

        # 1. Nav/Footer link extraction happens before clean_html_content mutates soup
        html_with_nav = (
            "<html><head><title>Test Org</title></head><body>"
            "<nav><a href='/about'>About</a><a href='https://evil.example/phish'>External</a></nav>"
            "<main><p>" + ("Word " * 40) + "</p></main>"
            "<footer><a href='/contact'>Contact</a></footer>"
            "</body></html>"
        )
        soup = BeautifulSoup(html_with_nav, "html.parser")
        links = _extract_internal_links(soup, "https://example.org/", "https://example.org/")
        cleaned = clean_html_content(soup)
        self.assertIn("https://example.org/about", links)
        self.assertIn("https://example.org/contact", links)
        self.assertNotIn("https://evil.example/phish", links)
        self.assertGreater(len(cleaned), 100)

        # 2. SPA detection triggers fallback & /api/knowledge/scrape surfaces 422 on SpaScrapeError
        spa_html = "<html><head><title>AIOTA</title></head><body><noscript>You need to enable JavaScript to run this app.</noscript><div id='root'></div></body></html>"
        self.assertTrue(_looks_like_spa_shell(spa_html, 5))

        # 3. SSRF redirect protection blocks redirect to AWS metadata / loopback
        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        scraper = WebsiteScraper(max_pages=5, delay=0)
        with patch("services.scraper.is_safe_url", side_effect=lambda u: "example.org" in u), \
             patch("services.scraper.requests.get", return_value=redirect_resp):
            safe_res = scraper._safe_get("https://example.org/", "https://example.org/")
            self.assertIsNone(safe_res)

        # 4. End-to-end /api/knowledge/text + XSS source_url validation + 422 on SPA fallback error
        prayatna_client = self._new_client()
        p_login = prayatna_client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(p_login.status_code, 200)

        bad_url_res = prayatna_client.post(
            "/api/knowledge/text",
            headers=_csrf_headers(prayatna_client),
            json={
                "title": "Unsafe Link",
                "content": "Valid text content long enough for testing knowledge endpoints.",
                "source_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(bad_url_res.status_code, 422)

        ok_text_res = prayatna_client.post(
            "/api/knowledge/text",
            headers=_csrf_headers(prayatna_client),
            json={
                "title": "Clinic Holiday Schedule 2026",
                "content": "Special unique keyword ZEBRA-HORIZON-42: Clinic remains open Monday to Saturday 9 AM to 6 PM.",
                "source_url": "https://prayatna.co.in/hours",
            },
        )
        self.assertEqual(ok_text_res.status_code, 200, ok_text_res.text)
        doc_data = ok_text_res.json()
        self.assertEqual(doc_data["source_type"], "text")
        self.assertEqual(doc_data["chunk_count"], 1)

        rag_hit = prayatna_client.post(
            "/api/knowledge/test",
            headers=_csrf_headers(prayatna_client),
            json={"query": "ZEBRA-HORIZON-42"},
        )
        self.assertEqual(rag_hit.status_code, 200)
        self.assertIn("ZEBRA-HORIZON-42", " ".join(r["content"] for r in rag_hit.json()["results"]))

        # Clean up test manual text doc
        del_doc = prayatna_client.delete(
            f"/api/knowledge/documents/{doc_data['id']}",
            headers=_csrf_headers(prayatna_client),
        )
        self.assertEqual(del_doc.status_code, 200)

        # Mock SpaScrapeError cleanly through API -> HTTP 422
        with patch("routes.knowledge.is_safe_url", return_value=True), \
             patch("routes.knowledge.WebsiteScraper.scrape", side_effect=SpaScrapeError("JS SPA test")):
            spa_api_res = prayatna_client.post(
                "/api/knowledge/scrape",
                headers=_csrf_headers(prayatna_client),
                json={"url": "https://example-spa.org/"},
            )
            self.assertEqual(spa_api_res.status_code, 422)
            self.assertIn("upload a PDF/DOCX/TXT or paste text", spa_api_res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
