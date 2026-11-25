import importlib
import json
import os
import shutil
import tempfile
import unittest
import uuid
from fastapi.testclient import TestClient

def _csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}

class WidgetPositionPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="test_widget_pos_")
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

    def setUp(self):
        # Reset prayatna-bot theme to standard defaults before each test
        client = TestClient(self.main.app)
        login_res = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        if login_res.status_code == 200:
            client.patch(
                "/api/admin/chatbot",
                json={
                    "theme_config": {
                        "position_preset": "bottom_right",
                        "vertical_position": "bottom",
                        "widget_position": "right",
                        "desktop_bottom_offset": 24,
                        "desktop_side_offset": 24,
                        "desktop_top_offset": 24,
                        "desktop_left_offset": 24,
                        "desktop_right_offset": 24,
                        "mobile_position_preset": "bottom_right",
                        "mobile_vertical_position": "bottom",
                        "mobile_position": "right",
                        "mobile_bottom_offset": 16,
                        "mobile_side_offset": 16,
                        "mobile_top_offset": 16,
                        "mobile_left_offset": 16,
                        "mobile_right_offset": 16,
                    }
                },
                headers=_csrf_headers(client),
            )

    def test_default_position_and_presets(self):
        """Verify default bottom_right position and setting elevated preset."""
        client = TestClient(self.main.app)

        # Login as client admin
        login_res = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(login_res.status_code, 200)

        # 1. Fetch current config - should have default bottom_right
        cfg_res = client.get("/api/admin/chatbot")
        self.assertEqual(cfg_res.status_code, 200)
        theme = cfg_res.json()["theme_config"]
        self.assertEqual(theme.get("position_preset"), "bottom_right")
        self.assertEqual(theme.get("widget_position"), "right")
        self.assertEqual(theme.get("vertical_position"), "bottom")
        self.assertEqual(theme.get("desktop_bottom_offset"), 24)

        # 2. Update to Bottom Right Elevated preset
        theme["position_preset"] = "bottom_right_elevated"
        theme["desktop_bottom_offset"] = 84
        theme["mobile_position_preset"] = "bottom_right_elevated"
        theme["mobile_bottom_offset"] = 76

        patch_res = client.patch(
            "/api/admin/chatbot",
            json={"theme_config": theme},
            headers=_csrf_headers(client),
        )
        self.assertEqual(patch_res.status_code, 200)
        updated = patch_res.json()["theme_config"]
        self.assertEqual(updated["position_preset"], "bottom_right_elevated")
        self.assertEqual(updated["desktop_bottom_offset"], 84)
        self.assertEqual(updated["mobile_bottom_offset"], 76)

        # 3. Check public widget config
        pub_res = client.get("/api/chat/config?bot=prayatna-bot")
        self.assertEqual(pub_res.status_code, 200)
        pub_theme = pub_res.json()["theme_config"]
        self.assertEqual(pub_theme["position_preset"], "bottom_right_elevated")
        self.assertEqual(pub_theme["desktop_bottom_offset"], 84)
        self.assertEqual(pub_theme["mobile_bottom_offset"], 76)

    def test_top_and_middle_and_left_positions(self):
        """Verify top_right, middle_right, and bottom_left presets and alignments."""
        client = TestClient(self.main.app)

        login_res = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(login_res.status_code, 200)

        # Test Top Right
        top_res = client.patch(
            "/api/admin/chatbot",
            json={
                "theme_config": {
                    "position_preset": "top_right",
                    "widget_position": "right",
                    "vertical_position": "top",
                    "desktop_top_offset": 32,
                    "desktop_right_offset": 28,
                }
            },
            headers=_csrf_headers(client),
        )
        self.assertEqual(top_res.status_code, 200)
        t_data = top_res.json()["theme_config"]
        self.assertEqual(t_data["position_preset"], "top_right")
        self.assertEqual(t_data["vertical_position"], "top")
        self.assertEqual(t_data["desktop_top_offset"], 32)
        self.assertEqual(t_data["desktop_right_offset"], 28)

        # Test Middle Right
        mid_res = client.patch(
            "/api/admin/chatbot",
            json={
                "theme_config": {
                    "position_preset": "middle_right",
                    "widget_position": "right",
                    "vertical_position": "middle",
                    "desktop_right_offset": 20,
                }
            },
            headers=_csrf_headers(client),
        )
        self.assertEqual(mid_res.status_code, 200)
        m_data = mid_res.json()["theme_config"]
        self.assertEqual(m_data["position_preset"], "middle_right")
        self.assertEqual(m_data["vertical_position"], "middle")

        # Test Bottom Left
        left_res = client.patch(
            "/api/admin/chatbot",
            json={
                "theme_config": {
                    "position_preset": "bottom_left",
                    "widget_position": "left",
                    "vertical_position": "bottom",
                    "desktop_bottom_offset": 30,
                    "desktop_left_offset": 30,
                }
            },
            headers=_csrf_headers(client),
        )
        self.assertEqual(left_res.status_code, 200)
        l_data = left_res.json()["theme_config"]
        self.assertEqual(l_data["position_preset"], "bottom_left")
        self.assertEqual(l_data["widget_position"], "left")
        self.assertEqual(l_data["desktop_left_offset"], 30)

    def test_custom_offsets_and_responsive_independence(self):
        """Verify custom offsets with independent desktop vs mobile settings."""
        client = TestClient(self.main.app)

        login_res = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(login_res.status_code, 200)

        # Set completely distinct desktop and mobile positions
        custom_payload = {
            "theme_config": {
                # Desktop: top-left with custom offsets
                "position_preset": "custom",
                "widget_position": "left",
                "vertical_position": "top",
                "desktop_top_offset": 45,
                "desktop_left_offset": 35,
                "desktop_bottom_offset": 20,
                "desktop_right_offset": 25,
                # Mobile: bottom-right elevated with custom offsets
                "mobile_position_preset": "custom",
                "mobile_position": "right",
                "mobile_vertical_position": "bottom",
                "mobile_bottom_offset": 75,
                "mobile_right_offset": 18,
                "mobile_top_offset": 12,
                "mobile_left_offset": 14,
            }
        }

        patch_res = client.patch(
            "/api/admin/chatbot",
            json=custom_payload,
            headers=_csrf_headers(client),
        )
        self.assertEqual(patch_res.status_code, 200)
        cfg = patch_res.json()["theme_config"]

        # Desktop assertions
        self.assertEqual(cfg["position_preset"], "custom")
        self.assertEqual(cfg["widget_position"], "left")
        self.assertEqual(cfg["vertical_position"], "top")
        self.assertEqual(cfg["desktop_top_offset"], 45)
        self.assertEqual(cfg["desktop_left_offset"], 35)

        # Mobile assertions
        self.assertEqual(cfg["mobile_position_preset"], "custom")
        self.assertEqual(cfg["mobile_position"], "right")
        self.assertEqual(cfg["mobile_vertical_position"], "bottom")
        self.assertEqual(cfg["mobile_bottom_offset"], 75)
        self.assertEqual(cfg["mobile_right_offset"], 18)

    def test_multi_tenant_placement_isolation(self):
        """Ensure two organizations can maintain completely independent placement configurations."""
        client = TestClient(self.main.app)

        # Super admin login to create two clients
        sa_res = client.post(
            "/api/auth/super-admin/login",
            json={"email": "superadmin@testplatform.local", "password": "SuperSecret#2026"},
        )
        self.assertEqual(sa_res.status_code, 200)

        tag = uuid.uuid4().hex[:6]
        c1_res = client.post(
            "/api/super-admin/clients",
            json={
                "organization_name": f"Org Alpha {tag}",
                "organization_slug": f"org-alpha-{tag}",
                "subscription_plan": "Enterprise",
                "admin_email": f"alpha_{tag}@test.local",
                "admin_name": "Alpha Admin",
                "admin_password": "AlphaPassword123#",
            },
            headers=_csrf_headers(client),
        )
        self.assertEqual(c1_res.status_code, 201)
        c1_id = c1_res.json()["organization"]["id"]
        bot_1 = c1_res.json()["organization"]["chatbot"]["chatbot_id"]

        c2_res = client.post(
            "/api/super-admin/clients",
            json={
                "organization_name": f"Org Beta {tag}",
                "organization_slug": f"org-beta-{tag}",
                "subscription_plan": "Professional",
                "admin_email": f"beta_{tag}@test.local",
                "admin_name": "Beta Admin",
                "admin_password": "BetaPassword123#",
            },
            headers=_csrf_headers(client),
        )
        self.assertEqual(c2_res.status_code, 201)
        c2_id = c2_res.json()["organization"]["id"]
        bot_2 = c2_res.json()["organization"]["chatbot"]["chatbot_id"]

        # Impersonate Org Alpha -> set to bottom_left (bottom=40, left=40)
        client.post(f"/api/super-admin/clients/{c1_id}/impersonate", headers=_csrf_headers(client))
        client.patch(
            "/api/admin/chatbot",
            json={"theme_config": {"position_preset": "bottom_left", "widget_position": "left", "vertical_position": "bottom", "desktop_bottom_offset": 40, "desktop_left_offset": 40}},
            headers=_csrf_headers(client),
        )
        client.post("/api/super-admin/exit-impersonation", headers=_csrf_headers(client))

        # Impersonate Org Beta -> set to top_right (top=50, right=50)
        client.post(f"/api/super-admin/clients/{c2_id}/impersonate", headers=_csrf_headers(client))
        client.patch(
            "/api/admin/chatbot",
            json={"theme_config": {"position_preset": "top_right", "widget_position": "right", "vertical_position": "top", "desktop_top_offset": 50, "desktop_right_offset": 50}},
            headers=_csrf_headers(client),
        )
        client.post("/api/super-admin/exit-impersonation", headers=_csrf_headers(client))

        # Verify public config for Org Alpha
        c1_bot = client.get(f"/api/chat/config?bot={bot_1}").json()
        self.assertEqual(c1_bot["theme_config"]["position_preset"], "bottom_left")
        self.assertEqual(c1_bot["theme_config"]["widget_position"], "left")
        self.assertEqual(c1_bot["theme_config"]["vertical_position"], "bottom")
        self.assertEqual(c1_bot["theme_config"]["desktop_bottom_offset"], 40)
        self.assertEqual(c1_bot["theme_config"]["desktop_left_offset"], 40)

        # Verify public config for Org Beta
        c2_bot = client.get(f"/api/chat/config?bot={bot_2}").json()
        self.assertEqual(c2_bot["theme_config"]["position_preset"], "top_right")
        self.assertEqual(c2_bot["theme_config"]["widget_position"], "right")
        self.assertEqual(c2_bot["theme_config"]["vertical_position"], "top")
        self.assertEqual(c2_bot["theme_config"]["desktop_top_offset"], 50)
        self.assertEqual(c2_bot["theme_config"]["desktop_right_offset"], 50)

    def test_smart_placement_config(self):
        """Verify smart_placement_enabled and smart_placement_mode defaults and patch updates."""
        client = TestClient(self.main.app)

        login_res = client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        self.assertEqual(login_res.status_code, 200)

        # 1. Fetch current config - verify defaults
        cfg_res = client.get("/api/admin/chatbot")
        self.assertEqual(cfg_res.status_code, 200)
        theme = cfg_res.json()["theme_config"]
        self.assertTrue(theme.get("smart_placement_enabled", True))
        self.assertEqual(theme.get("smart_placement_mode", "auto_stack"), "auto_stack")

        # 2. Update to auto_side and disabled
        update_res = client.patch(
            "/api/admin/chatbot",
            json={
                "theme_config": {
                    "smart_placement_enabled": False,
                    "smart_placement_mode": "auto_side",
                }
            },
            headers=_csrf_headers(client),
        )
        self.assertEqual(update_res.status_code, 200)
        up_theme = update_res.json()["theme_config"]
        self.assertFalse(up_theme["smart_placement_enabled"])
        self.assertEqual(up_theme["smart_placement_mode"], "auto_side")

        # 3. Verify public config endpoint
        pub_res = client.get("/api/chat/config?bot=prayatna-bot")
        self.assertEqual(pub_res.status_code, 200)
        pub_theme = pub_res.json()["theme_config"]
        self.assertFalse(pub_theme["smart_placement_enabled"])
        self.assertEqual(pub_theme["smart_placement_mode"], "auto_side")

