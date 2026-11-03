from __future__ import annotations

import base64
from aiohttp.test_utils import TestClient, TestServer
import unittest
from unittest import IsolatedAsyncioTestCase

from astrbot_plugin_anime.web_server import is_authorized


def basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


class RemoteWebAuthTests(unittest.TestCase):
    def test_remote_management_requires_configured_basic_auth_password(self):
        self.assertFalse(is_authorized("", ""))
        self.assertFalse(is_authorized(basic_header("anime", "wrong-value"), "right-value"))
        self.assertTrue(is_authorized(basic_header("anime", "right-value"), "right-value"))
        self.assertFalse(is_authorized(basic_header("other", "right-value"), "right-value"))
        self.assertTrue(is_authorized(basic_header("anime", "口令"), "口令"))


class RemoteWebServerTests(IsolatedAsyncioTestCase):
    async def test_remote_server_protects_api_and_serves_the_management_page(self):
        from astrbot_plugin_anime.web_server import create_remote_web_app

        class API:
            async def execute(self, endpoint, method, query, payload):
                return 200, {"endpoint": endpoint}

        class Plugin:
            web_api = API()

        client = TestClient(TestServer(create_remote_web_app(Plugin(), "a-long-test-password")))
        await client.start_server()
        try:
            denied = await client.get("/api/status")
            self.assertEqual(denied.status, 401)
            auth = basic_header("anime", "a-long-test-password").split(" ", 1)[1]
            page = await client.get("/", headers={"Authorization": "Basic " + auth})
            self.assertEqual(page.status, 200)
            self.assertIn("动画订阅", await page.text())
            response = await client.get("/api/status", headers={"Authorization": "Basic " + auth})
            self.assertEqual(await response.json(), {"endpoint": "status"})
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
