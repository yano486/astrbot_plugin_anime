from __future__ import annotations

import asyncio
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

import aiohttp
from PIL import Image, ImageOps

from ..core.diagnostics import get_plugin_logger


logger = get_plugin_logger()
RETENTION = 30 * 86400
MAX_BYTES = 4 * 1024 * 1024


class CoverCache:
    def __init__(self, session: aiohttp.ClientSession, directory: Path, proxy_url: str = ""):
        self.session = session
        self.directory = Path(directory)
        self.proxy_url = proxy_url
        self._lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(4)

    async def prepare(self, items) -> dict[str, Path]:
        # Serialise batches so overlapping reminder/table requests share each cached URL.
        async with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            for path in self.directory.iterdir():
                if re.fullmatch(r"[0-9a-f]{64}\.jpg", path.name) and not path.is_symlink() and path.stat().st_mtime < time.time() - RETENTION:
                    path.unlink()
            urls = {item.cover_url for item in items if item.cover_url}
            if not urls:
                return {}
            tasks = {url: asyncio.create_task(self._fetch(url)) for url in urls}
            try:
                _, pending = await asyncio.wait(tasks.values(), timeout=12)
                if pending:
                    logger.warning("[anime] 本次封面获取超过 12 秒，未完成的封面将显示占位")
            finally:
                for task in tasks.values():
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks.values(), return_exceptions=True)
            paths = {url: task.result() if not task.cancelled() else None for url, task in tasks.items()}
            return {item.key: paths[item.cover_url] for item in items if paths.get(item.cover_url) is not None}

    async def _fetch(self, url: str) -> Path | None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            logger.warning("[anime] 封面地址无效，将显示占位")
            return None
        path = self.directory / (sha256(url.encode()).hexdigest() + ".jpg")
        if path.is_file() and not path.is_symlink():
            return path
        async with self._slots:
            try:
                proxy = self.proxy_url if parsed.hostname == "bgm.tv" or parsed.hostname.endswith(".bgm.tv") else None
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=8), proxy=proxy) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise ValueError("cover exceeds 4 MiB")
                await asyncio.to_thread(self._save, bytes(data), path)
                return path
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, Image.DecompressionBombError) as exc:
                logger.warning("[anime] 封面获取失败，将显示占位：%s (%s)", parsed.hostname, type(exc).__name__)
                return None

    @staticmethod
    def _save(data: bytes, path: Path):
        with Image.open(BytesIO(data)) as original:
            if original.width * original.height > 20_000_000:
                raise ValueError("cover dimensions exceed limit")
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((960, 1440))
            temporary = path.with_name(path.stem + "." + uuid4().hex + ".tmp")
            try:
                image.save(temporary, format="JPEG", quality=90)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
