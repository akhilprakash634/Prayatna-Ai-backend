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


class WidgetCustomizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="widget_custom_")
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
        os.environ["DATA_DIR"] = cls.tmp_dir
        os.environ["PRAYATNA_ADMIN_EMAIL"] = "admin@prayatna.co.in"
        os.environ["PRAYATNA_ADMIN_PASSWORD"] = "PrayatnaSecret#2026"
        os.environ["SUPER_ADMIN_PASSWORD"] = "SuperSecret#2026"

        import database
        import models
        import services.security
        import services.rag

        importlib.reload(database)
        importlib.reload(models)
        importlib.reload(services.security)
        importlib.reload(services.rag)

        from migrations import run_migrations
        run_migrations()

        import main
        importlib.reload(main)
        cls.app = main.app
        cls.client = TestClient(cls.app)

        # Login as client admin for prayatna
        login_res = cls.client.post(
            "/api/auth/login",
            json={"email": "admin@prayatna.co.in", "password": "PrayatnaSecret#2026"},
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_default_widget_configuration_backward_compatibility(self):
        """Verify that default widget configuration matches existing appearance and has full backwards compatibility."""
        res = self.client.get("/api/admin/chatbot")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        tc = data.get("theme_config", {})

        # Default values check
        self.assertEqual(tc.get("launcher_style"), "default")
        self.assertEqual(tc.get("launcher_shape"), "circle")
        self.assertEqual(tc.get("launcher_size"), "medium")
        self.assertEqual(tc.get("widget_position"), "right")
        self.assertFalse(tc.get("greeting_enabled", False))
        self.assertEqual(tc.get("desktop_bottom_offset"), 24)
        self.assertEqual(tc.get("desktop_side_offset"), 24)

        # Public endpoint check
        pub = self.client.get("/api/chat/config?bot=prayatna-bot")
        self.assertEqual(pub.status_code, 200)
        pub_tc = pub.json().get("theme_config", {})
        self.assertEqual(pub_tc.get("launcher_style"), "default")
        self.assertEqual(pub_tc.get("launcher_shape"), "circle")

    def test_02_update_widget_appearance_settings(self):
        """Configure custom launcher style, shape, colors, and offsets."""
        payload = {
            "theme_config": {
                "launcher_style": "animated",
                "launcher_bg_color": "#0f766e",
                "launcher_icon_color": "#ffffff",
                "launcher_size": "large",
                "launcher_shape": "rounded_square",
                "avatar_type": "lottie",
                "avatar_animation_url": "/animations/friendly-robot.json",
                "character_size": "overflow",
                "animation_enabled": True,
                "animation_behavior": "greeting",
                "reduced_motion": "respect",
                "greeting_enabled": True,
                "greeting_text": "Need help with our services? We are here!",
                "greeting_bg_color": "#ffffff",
                "greeting_text_color": "#0f172a",
                "greeting_delay": 2,
                "greeting_auto_hide": 8,
                "desktop_bottom_offset": 32,
                "desktop_side_offset": 28,
                "widget_position": "left",
                "mobile_launcher_size": "small",
                "mobile_position": "left",
                "mobile_bottom_offset": 20,
                "mobile_side_offset": 16,
            }
        }
        res = self.client.patch("/api/admin/chatbot", json=payload, headers=_csrf_headers(self.client))
        self.assertEqual(res.status_code, 200)
        tc = res.json()["theme_config"]

        self.assertEqual(tc["launcher_style"], "animated")
        self.assertEqual(tc["launcher_bg_color"], "#0f766e")
        self.assertEqual(tc["launcher_size"], "large")
        self.assertEqual(tc["launcher_shape"], "rounded_square")
        self.assertEqual(tc["avatar_animation_url"], "/animations/friendly-robot.json")
        self.assertEqual(tc["character_size"], "overflow")
        self.assertEqual(tc["animation_behavior"], "greeting")
        self.assertTrue(tc["greeting_enabled"])
        self.assertEqual(tc["greeting_text"], "Need help with our services? We are here!")
        self.assertEqual(tc["desktop_bottom_offset"], 32)
        self.assertEqual(tc["widget_position"], "left")

        # Verify public config endpoint reflects the updated widget theme
        pub = self.client.get("/api/chat/config?bot=prayatna-bot")
        self.assertEqual(pub.status_code, 200)
        pub_tc = pub.json()["theme_config"]
        self.assertEqual(pub_tc["launcher_style"], "animated")
        self.assertEqual(pub_tc["launcher_bg_color"], "#0f766e")
        self.assertEqual(pub_tc["avatar_animation_url"], "/animations/friendly-robot.json")
        self.assertTrue(pub_tc["greeting_enabled"])
        self.assertEqual(pub_tc["widget_position"], "left")

    def test_03_get_curated_widget_presets(self):
        """Verify the presets endpoint returns built-in animated character presets."""
        res = self.client.get("/api/admin/widget/presets", headers=_csrf_headers(self.client))
        self.assertEqual(res.status_code, 200)
        presets = res.json()
        self.assertGreaterEqual(len(presets), 3)

        preset_ids = [p["id"] for p in presets]
        self.assertIn("friendly_robot", preset_ids)
        self.assertIn("ai_sparkle", preset_ids)
        self.assertIn("chatty_bubble", preset_ids)

    def test_04_upload_lottie_json_asset(self):
        """Upload valid Lottie JSON asset and verify persistent URL."""
        lottie_content = json.dumps({
            "v": "5.7.4",
            "fr": 30,
            "ip": 0,
            "op": 60,
            "w": 200,
            "h": 200,
            "nm": "Test Animation",
            "layers": []
        }).encode("utf-8")

        res = self.client.post(
            "/api/admin/widget/upload-asset",
            files={"file": ("mascot.json", lottie_content, "application/json")},
            headers=_csrf_headers(self.client),
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["asset_type"], "lottie")
        self.assertTrue(data["url"].startswith("/api/widget/assets/"))
        self.assertTrue(data["url"].endswith("mascot.json"))

        # Verify static asset is accessible via GET
        asset_res = self.client.get(data["url"])
        self.assertEqual(asset_res.status_code, 200)
        self.assertEqual(json.loads(asset_res.text)["nm"], "Test Animation")

    def test_05_upload_gif_asset(self):
        """Upload valid GIF asset and verify header validation and storage."""
        # GIF89a header
        gif_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"

        res = self.client.post(
            "/api/admin/widget/upload-asset",
            files={"file": ("character.gif", gif_bytes, "image/gif")},
            headers=_csrf_headers(self.client),
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["asset_type"], "gif")
        self.assertTrue(data["url"].startswith("/api/widget/assets/"))

        # Verify file is served
        asset_res = self.client.get(data["url"])
        self.assertEqual(asset_res.status_code, 200)
        self.assertTrue(asset_res.content.startswith(b"GIF89a"))

    def test_06_reject_invalid_or_malformed_assets(self):
        """Reject invalid file extensions and malformed Lottie JSON."""
        # 1. Unsupported extension (.exe)
        res_exe = self.client.post(
            "/api/admin/widget/upload-asset",
            files={"file": ("malware.exe", b"binarycontent", "application/octet-stream")},
            headers=_csrf_headers(self.client),
        )
        self.assertEqual(res_exe.status_code, 400)
        self.assertIn("Unsupported file format", res_exe.text)

        # 2. Malformed JSON
        res_json = self.client.post(
            "/api/admin/widget/upload-asset",
            files={"file": ("broken.json", b"not valid json {", "application/json")},
            headers=_csrf_headers(self.client),
        )
        self.assertEqual(res_json.status_code, 400)
        self.assertIn("Invalid Lottie JSON", res_json.text)

        # 3. Malformed GIF header
        res_gif = self.client.post(
            "/api/admin/widget/upload-asset",
            files={"file": ("fake.gif", b"NOTAGIFIMAGEHEADER", "image/gif")},
            headers=_csrf_headers(self.client),
        )
        self.assertEqual(res_gif.status_code, 400)
        self.assertIn("Invalid GIF file format", res_gif.text)

    def test_07_restore_default_icon_when_character_removed(self):
        """Switch back from animated character to default chat icon."""
        payload = {
            "theme_config": {
                "launcher_style": "default",
                "avatar_type": "default",
                "avatar_animation_url": None,
                "avatar_url": None,
                "avatar_preset": None,
            }
        }
        res = self.client.patch("/api/admin/chatbot", json=payload, headers=_csrf_headers(self.client))
        self.assertEqual(res.status_code, 200)
        tc = res.json()["theme_config"]
        self.assertEqual(tc["launcher_style"], "default")
        self.assertEqual(tc["avatar_type"], "default")
        self.assertIsNone(tc["avatar_animation_url"])


if __name__ == "__main__":
    unittest.main()
