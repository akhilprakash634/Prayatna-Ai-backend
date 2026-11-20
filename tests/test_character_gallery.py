import importlib
import json
import os
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient

def _csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}

class CharacterGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="test_char_gallery_")
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

        importlib.reload(database)
        importlib.reload(models)
        importlib.reload(services.security)
        importlib.reload(migrations)
        importlib.reload(main)

        cls.main = main
        cls.database = database
        cls.models = models

        migrations.run_migrations()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _client(self) -> TestClient:
        return TestClient(self.main.app)

    def test_01_public_character_gallery_and_filters(self):
        client = self._client()
        res = client.get("/api/widget/characters")
        self.assertEqual(res.status_code, 200, res.text)
        chars = res.json()
        self.assertGreaterEqual(len(chars), 10)

        ids = [c["character_id"] for c in chars]
        self.assertIn("buddy-robot", ids)
        self.assertIn("happy-assistant", ids)
        self.assertIn("professional-bot", ids)
        self.assertIn("smart-assistant", ids)
        self.assertIn("care-companion", ids)
        self.assertIn("healthcare-buddy", ids)
        self.assertIn("learning-mate", ids)
        self.assertIn("study-companion", ids)
        self.assertIn("minimal-orb", ids)
        self.assertIn("floating-mascot", ids)

        # Category filter: Healthcare
        res_health = client.get("/api/widget/characters?category=healthcare")
        self.assertEqual(res_health.status_code, 200)
        health_chars = res_health.json()
        self.assertTrue(all(c["category"] == "healthcare" for c in health_chars))
        self.assertGreaterEqual(len(health_chars), 2)

        # Search filter: "robot"
        res_search = client.get("/api/widget/characters?search=robot")
        self.assertEqual(res_search.status_code, 200)
        search_chars = res_search.json()
        self.assertTrue(any("robot" in c["name"].lower() or "robot" in c["description"].lower() for c in search_chars))

    def test_02_client_admin_can_select_and_persist_character(self):
        client = self._client()
        login = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(login.status_code, 200, login.text)

        # Select "care-companion" from gallery with custom speed
        patch_res = client.patch(
            "/api/admin/chatbot",
            headers=_csrf_headers(client),
            json={
                "theme_config": {
                    "launcher_style": "animated",
                    "avatar_type": "lottie",
                    "avatar_animation_url": "/characters/care-companion.json",
                    "selected_character_id": "care-companion",
                    "selected_character_type": "lottie",
                    "selected_character_asset": "/characters/care-companion.json",
                    "animation_speed": 1.5,
                    "character_settings": {"mood": "calm", "show_border": True},
                }
            },
        )
        self.assertEqual(patch_res.status_code, 200, patch_res.text)
        updated_theme = patch_res.json()["theme_config"]
        self.assertEqual(updated_theme["selected_character_id"], "care-companion")
        self.assertEqual(updated_theme["animation_speed"], 1.5)
        self.assertEqual(updated_theme["selected_character_asset"], "/characters/care-companion.json")

        # Verify public config returns this selected character
        pub_res = client.get("/api/chat/config?bot=prayatna-bot")
        self.assertEqual(pub_res.status_code, 200)
        pub_theme = pub_res.json()["theme_config"]
        self.assertEqual(pub_theme["selected_character_id"], "care-companion")
        self.assertEqual(pub_theme["avatar_animation_url"], "/characters/care-companion.json")
        self.assertEqual(pub_theme["animation_speed"], 1.5)

    def test_03_super_admin_character_management_lifecycle(self):
        client = self._client()
        s_login = client.post(
            "/api/auth/super-admin/login",
            json={"email": "superadmin@testplatform.local", "password": "SuperSecret#2026"},
        )
        self.assertEqual(s_login.status_code, 200, s_login.text)

        # List all characters
        list_res = client.get("/api/super-admin/characters")
        self.assertEqual(list_res.status_code, 200)
        self.assertGreaterEqual(len(list_res.json()), 10)

        # Create new custom character
        create_res = client.post(
            "/api/super-admin/characters",
            headers=_csrf_headers(client),
            json={
                "character_id": "sparky-fox",
                "name": "Sparky Fox",
                "category": "friendly",
                "description": "An energetic animated fox guide.",
                "animation_url": "/characters/sparky-fox.json",
                "animation_type": "lottie",
                "supported_animations": ["continuous", "hover"],
                "default_size": 60,
                "is_active": True,
                "display_order": 99,
            },
        )
        self.assertEqual(create_res.status_code, 201, create_res.text)
        created_id = create_res.json()["character_id"]
        self.assertEqual(created_id, "sparky-fox")

        # Patch: toggle is_active to False
        patch_res = client.patch(
            f"/api/super-admin/characters/{created_id}",
            headers=_csrf_headers(client),
            json={"is_active": False, "description": "Updated description for Sparky Fox."},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertFalse(patch_res.json()["is_active"])

        # Inactive character should not appear in public active gallery
        pub_res = client.get("/api/widget/characters")
        pub_ids = [c["character_id"] for c in pub_res.json()]
        self.assertNotIn("sparky-fox", pub_ids)

        # Deleting assigned character should be blocked
        del_blocked = client.delete(
            "/api/super-admin/characters/care-companion",
            headers=_csrf_headers(client),
        )
        self.assertEqual(del_blocked.status_code, 400)
        self.assertIn("currently assigned", del_blocked.text)

        # Deleting unassigned character succeeds
        del_ok = client.delete(
            f"/api/super-admin/characters/{created_id}",
            headers=_csrf_headers(client),
        )
        self.assertEqual(del_ok.status_code, 200)

    def test_04_multi_tenant_character_isolation(self):
        client = self._client()
        s_login = client.post(
            "/api/auth/super-admin/login",
            json={"email": "superadmin@testplatform.local", "password": "SuperSecret#2026"},
        )
        self.assertEqual(s_login.status_code, 200)

        # Create Tenant Alpha
        res_a = client.post(
            "/api/super-admin/clients",
            headers=_csrf_headers(client),
            json={
                "organization_name": "Clinic Alpha",
                "organization_slug": "clinic-alpha",
                "admin_name": "Alpha Admin",
                "admin_email": "admin@alpha.example",
                "subscription_plan": "Basic",
                "account_status": "active",
            },
        )
        self.assertEqual(res_a.status_code, 201)
        bot_a = res_a.json()["organization"]["chatbot"]["chatbot_id"]

        # Impersonate Tenant Alpha and set "buddy-robot"
        imp_a = client.post(
            f"/api/super-admin/clients/{res_a.json()['organization']['id']}/impersonate",
            headers=_csrf_headers(client),
        )
        self.assertEqual(imp_a.status_code, 200)
        patch_a = client.patch(
            "/api/admin/chatbot",
            headers=_csrf_headers(client),
            json={
                "theme_config": {
                    "launcher_style": "animated",
                    "avatar_type": "lottie",
                    "avatar_animation_url": "/characters/buddy-robot.json",
                    "selected_character_id": "buddy-robot",
                    "selected_character_type": "lottie",
                    "selected_character_asset": "/characters/buddy-robot.json",
                }
            },
        )
        self.assertEqual(patch_a.status_code, 200)

        # Exit impersonation
        client.post("/api/super-admin/exit-impersonation", headers=_csrf_headers(client))

        # Create Tenant Beta
        res_b = client.post(
            "/api/super-admin/clients",
            headers=_csrf_headers(client),
            json={
                "organization_name": "School Beta",
                "organization_slug": "school-beta",
                "admin_name": "Beta Admin",
                "admin_email": "admin@beta.example",
                "subscription_plan": "Basic",
                "account_status": "active",
            },
        )
        self.assertEqual(res_b.status_code, 201)
        bot_b = res_b.json()["organization"]["chatbot"]["chatbot_id"]

        # Impersonate Tenant Beta and set "learning-mate"
        client.post(
            f"/api/super-admin/clients/{res_b.json()['organization']['id']}/impersonate",
            headers=_csrf_headers(client),
        )
        patch_b = client.patch(
            "/api/admin/chatbot",
            headers=_csrf_headers(client),
            json={
                "theme_config": {
                    "launcher_style": "animated",
                    "avatar_type": "lottie",
                    "avatar_animation_url": "/characters/learning-mate.json",
                    "selected_character_id": "learning-mate",
                    "selected_character_type": "lottie",
                    "selected_character_asset": "/characters/learning-mate.json",
                }
            },
        )
        self.assertEqual(patch_b.status_code, 200)

        # Check public chatbot configs for both tenants
        anon = self._client()
        cfg_a = anon.get(f"/api/chat/config?bot={bot_a}").json()["theme_config"]
        cfg_b = anon.get(f"/api/chat/config?bot={bot_b}").json()["theme_config"]

        self.assertEqual(cfg_a["selected_character_id"], "buddy-robot")
        self.assertEqual(cfg_a["avatar_animation_url"], "/characters/buddy-robot.json")

        self.assertEqual(cfg_b["selected_character_id"], "learning-mate")
        self.assertEqual(cfg_b["avatar_animation_url"], "/characters/learning-mate.json")


if __name__ == "__main__":
    unittest.main()
