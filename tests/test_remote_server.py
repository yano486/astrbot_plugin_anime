from __future__ import annotations

import json
from aiohttp.test_utils import TestClient, TestServer
import unittest
from unittest import IsolatedAsyncioTestCase

from astrbot_plugin_anime.web.server import SESSION_MAX_AGE, _session_value, _valid_session, create_remote_web_app, validate_remote_password


class RemotePasswordTests(unittest.TestCase):
    def test_password_is_optional_or_a_pin_of_at_most_eight_digits(self):
        pin = "12" * 4
        self.assertEqual(validate_remote_password(""), "")
        self.assertEqual(validate_remote_password(pin), pin)
        self.assertEqual(validate_remote_password("123"), "123")
        for invalid in ("123456789", "1234abcd", " 1234", "１２３４"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_remote_password(invalid)

    def test_session_is_signed_and_expires_after_its_lifetime(self):
        secret = b"test-only-session-key"
        session = _session_value(secret, 1000)
        self.assertTrue(_valid_session(session, secret, now=1000 + SESSION_MAX_AGE))
        self.assertFalse(_valid_session(session, secret, now=1001 + SESSION_MAX_AGE))
        self.assertFalse(_valid_session(session + "x", secret, now=1000))


class RemoteWebAPI:
    async def execute(self, endpoint, method, query, payload):
        return 200, {"endpoint": endpoint}


class RemoteWebPlugin:
    web_api = RemoteWebAPI()


class RemoteWebServerTests(IsolatedAsyncioTestCase):

    async def test_empty_password_serves_webui_and_api_without_auth_prompt(self):
        client = TestClient(TestServer(create_remote_web_app(RemoteWebPlugin(), "")))
        await client.start_server()
        try:
            page = await client.get("/")
            self.assertEqual(page.status, 200)
            page_text = await page.text()
            self.assertIn("动画订阅", page_text)
            self.assertIn("controls.js", page_text)
            self.assertNotIn("login-panel", await page.text())
            controls = await client.get("/controls.js")
            self.assertEqual(controls.status, 200)
            self.assertIn("application/javascript", controls.headers["Content-Type"])
            response = await client.get("/api/status")
            self.assertEqual(response.status, 200)

            preferences = await client.get("/api/preferences")
            self.assertEqual(preferences.status, 200)
            added = await client.post("/api/targets/umo", json={"umo": "default:FriendMessage:123456789"})
            self.assertEqual(added.status, 200)
            self.assertNotIn("WWW-Authenticate", response.headers)
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        finally:
            await client.close()

    async def test_configured_password_uses_embedded_login_and_signed_session_cookie(self):
        pin = "12" * 4
        client = TestClient(TestServer(create_remote_web_app(RemoteWebPlugin(), pin)))
        await client.start_server()
        try:
            page = await client.get("/")
            self.assertEqual(page.status, 200)
            self.assertIn("login-card", await page.text())
            self.assertNotIn("WWW-Authenticate", page.headers)
            denied = await client.get("/api/status")
            self.assertEqual(denied.status, 401)
            self.assertNotIn("WWW-Authenticate", denied.headers)
            self.assertEqual(denied.headers["Cache-Control"], "no-store")
            protected_script = await client.get("/app.js", allow_redirects=False)
            self.assertEqual(protected_script.status, 302)
            self.assertEqual(protected_script.headers["Location"], "/")

            wrong = await client.post("/api/login", json={"password": "34" * 4})
            self.assertEqual(wrong.status, 401)
            success = await client.post("/api/login", json={"password": pin})
            self.assertEqual(success.status, 200)
            cookie = success.cookies.get("anime_session")
            self.assertIsNotNone(cookie)
            self.assertTrue(cookie["httponly"])
            self.assertEqual(cookie["samesite"], "Strict")

            protected = await client.get("/api/status")
            self.assertEqual(protected.status, 200)
            app_script = await client.get("/app.js")
            self.assertEqual(app_script.status, 200)
            authenticated_page = await client.get("/")
            self.assertNotIn("login-card", await authenticated_page.text())
            logged_out = await client.post("/api/logout", json={})
            self.assertEqual(logged_out.status, 200)
            self.assertEqual((await client.get("/api/status")).status, 401)
        finally:
            await client.close()

    async def test_login_rejects_cross_origin_requests(self):
        pin = "12" * 4
        client = TestClient(TestServer(create_remote_web_app(RemoteWebPlugin(), pin)))
        await client.start_server()
        try:
            response = await client.post(
                "/api/login",
                json={"password": pin},
                headers={"Origin": "http://attacker.example"},
            )
            self.assertEqual(response.status, 403)
            same_host_different_scheme = await client.post(
                "/api/login",
                json={"password": pin},
                headers={"Origin": f"https://{client.server.host}:{client.server.port}"},
            )
            self.assertEqual(same_host_different_scheme.status, 403)
        finally:
            await client.close()

    async def test_limited_password_is_not_echoed_and_login_page_is_localized(self):
        client = TestClient(TestServer(create_remote_web_app(RemoteWebPlugin(), "12" * 4)))
        await client.start_server()
        try:
            response = await client.get("/login.js")
            self.assertEqual(response.status, 200)
            self.assertIn("password", await response.text())
            self.assertEqual((await client.get("/api/status")).status, 401)
        finally:
            await client.close()

    async def test_repeated_wrong_password_attempts_are_rate_limited(self):
        client = TestClient(TestServer(create_remote_web_app(RemoteWebPlugin(), "12" * 4)))
        await client.start_server()
        try:
            responses = [
                await client.post("/api/login", json={"password": "34" * 4})
                for _ in range(6)
            ]
            self.assertEqual([response.status for response in responses[:5]], [401] * 5)
            self.assertEqual(responses[5].status, 429)
        finally:
            await client.close()


class ConfigDescriptionTests(unittest.TestCase):
    def test_remote_settings_have_short_titles_and_supporting_hints(self):
        from pathlib import Path

        schema = json.loads((Path(__file__).parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
        for key in ("remote_webui_enabled", "remote_webui_host", "remote_webui_port", "remote_webui_password", "bangumi_api_token"):
            with self.subTest(key=key):
                self.assertTrue(schema[key]["description"])
                self.assertTrue(schema[key]["hint"])
        self.assertEqual(schema["remote_webui_password"]["default"], "")
        self.assertTrue(schema["remote_webui_password"]["secret"])
        self.assertTrue(schema["bangumi_api_token"]["secret"])


if __name__ == "__main__":
    unittest.main()
