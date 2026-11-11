from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import aiohttp
from aiohttp import web
from PIL import Image

from astrbot_plugin_anime.core.models import AnimeItem


class CoverCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cover_download_is_cached_and_shared_between_items(self):
        from astrbot_plugin_anime.services.covers import CoverCache

        data = BytesIO()
        Image.new("RGB", (200, 300), "#c34929").save(data, "PNG")
        hits = []

        async def handler(request):
            hits.append(request.path)
            return web.Response(body=data.getvalue(), content_type="image/png")

        app = web.Application()
        app.router.add_get("/cover", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with tempfile.TemporaryDirectory() as directory, self.subTest():
                async with aiohttp.ClientSession() as session:
                    cache = CoverCache(session, Path(directory))
                    items = [AnimeItem(key=key, title=key, cover_url=f"http://127.0.0.1:{port}/cover") for key in ("a", "b")]
                    first = await cache.prepare(items)
                    second = await cache.prepare(items)
                    self.assertEqual(hits, ["/cover"])
                    self.assertEqual(first, second)
                    self.assertEqual(first["a"], first["b"])
                    with Image.open(first["a"]) as image:
                        self.assertEqual(image.size, (200, 300))
        finally:
            await runner.cleanup()

    async def test_non_http_cover_is_not_read_from_disk(self):
        from astrbot_plugin_anime.services.covers import CoverCache

        with tempfile.TemporaryDirectory() as directory:
            async with aiohttp.ClientSession() as session:
                cache = CoverCache(session, Path(directory))
                self.assertEqual(await cache.prepare([AnimeItem(key="a", title="a", cover_url="file:///private.png")]), {})
