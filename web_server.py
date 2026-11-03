from __future__ import annotations

import base64
import binascii
import hmac
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from aiohttp import web


def is_authorized(header: str, password: str) -> bool:
    if not password or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    username, separator, candidate = decoded.partition(":")
    return bool(separator and username == "anime" and hmac.compare_digest(candidate.encode("utf-8"), password.encode("utf-8")))


def create_remote_web_app(plugin: Any, password: str) -> web.Application:
    if len(password) < 12:
        raise ValueError("remote WebUI password must contain at least 12 characters")

    @web.middleware
    async def authentication(request: web.Request, handler):
        if not is_authorized(request.headers.get("Authorization", ""), password):
            raise web.HTTPUnauthorized(headers={"WWW-Authenticate": 'Basic realm="Anime WebUI"'})
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            raise web.HTTPForbidden(text="cross-origin requests are not allowed")
        return await handler(request)

    app = web.Application(middlewares=[authentication], client_max_size=1024 * 1024)
    endpoint_names = (
        "status",
        "items",
        "targets",
        "targets/whitelist",
        "subscriptions",
        "movie-release",
        "test-push",
        "refresh",
    )

    def api_handler(endpoint: str):
        async def api(request: web.Request) -> web.Response:
            payload = None
            if request.method != "GET":
                try:
                    payload = await request.json()
                except (ValueError, web.HTTPException):
                    return web.json_response({"error": "request body must be valid JSON"}, status=400)
            status, value = await plugin.web_api.execute(endpoint, request.method, request.query, payload)
            return web.json_response(value, status=status)

        return api

    async def index(_: web.Request) -> web.FileResponse:
        root = Path(__file__).parent / "views" / "management"
        return web.FileResponse(root / "index.html")

    async def asset(request: web.Request) -> web.StreamResponse:
        root = (Path(__file__).parent / "views" / "management").resolve()
        path = (root / request.match_info["asset"]).resolve()
        if root not in path.parents or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    for endpoint in endpoint_names:
        methods = ("GET",) if endpoint in ("status", "items", "targets") else (("GET", "POST") if endpoint == "subscriptions" else ("POST",))
        for method in methods:
            app.router.add_route(method, f"/api/{endpoint}", api_handler(endpoint), name=f"api_{endpoint.replace('/', '_')}_{method.lower()}")
    app.router.add_get("/", index)
    app.router.add_get("/{asset:.*}", asset)
    return app
