from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web


SESSION_COOKIE = "anime_session"
SESSION_MAX_AGE = 8 * 60 * 60
LOGIN_WINDOW = 60
LOGIN_LIMIT = 5
_PIN_PATTERN = re.compile(r"[0-9]{1,8}\Z")
AUTHENTICATED = web.RequestKey("authenticated", bool)


def validate_remote_password(password: Any) -> str:
    if password is None or password == "":
        return ""
    if not isinstance(password, str) or not _PIN_PATTERN.fullmatch(password):
        raise ValueError("remote WebUI password must be empty or contain 1-8 digits")
    return password


def _session_value(secret: bytes, issued_at: int) -> str:
    timestamp = str(issued_at)
    signature = hmac.new(secret, timestamp.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def _valid_session(value: str, secret: bytes, now: int | None = None) -> bool:
    try:
        timestamp_text, signature = value.split(".", 1)
        issued_at = int(timestamp_text)
    except (ValueError, AttributeError):
        return False
    current = int(time.time()) if now is None else now
    if issued_at > current or current - issued_at > SESSION_MAX_AGE:
        return False
    expected = _session_value(secret, issued_at).split(".", 1)[1]
    return hmac.compare_digest(signature, expected)


def create_remote_web_app(plugin: Any, password: str) -> web.Application:
    password = validate_remote_password(password)
    session_secret = secrets.token_bytes(32)
    login_attempts: dict[str, list[float]] = {}

    @web.middleware
    async def security(request: web.Request, handler):
        origin = request.headers.get("Origin")
        if origin:
            try:
                parsed_origin = urlsplit(origin)
            except ValueError:
                raise web.HTTPForbidden(text="cross-origin requests are not allowed") from None
            if (
                parsed_origin.scheme.casefold() != request.scheme.casefold()
                or parsed_origin.netloc.casefold() != request.host.casefold()
            ):
                raise web.HTTPForbidden(text="cross-origin requests are not allowed")
        if request.headers.get("Sec-Fetch-Site", "").casefold() == "cross-site":
            raise web.HTTPForbidden(text="cross-origin requests are not allowed")

        authenticated = not password or _valid_session(
            request.cookies.get(SESSION_COOKIE, ""), session_secret
        )
        request[AUTHENTICATED] = authenticated
        public_paths = {"/", "/login.css", "/login.js", "/api/login"}
        if not authenticated and request.path not in public_paths:
            if request.path.startswith("/api/"):
                response = web.json_response({"error": "请先输入登录密码"}, status=401)
                response.headers["Cache-Control"] = "no-store"
                return response
            raise web.HTTPFound("/")
        response = await handler(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' http: https: data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        return response

    app = web.Application(middlewares=[security], client_max_size=1024 * 1024)
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
            try:
                payload = await request.json() if request.method != "GET" else None
            except (ValueError, web.HTTPException):
                return web.json_response({"error": "request body must be valid JSON"}, status=400)
            status, value = await plugin.web_api.execute(endpoint, request.method, request.query, payload)
            return web.json_response(value, status=status)

        return api

    async def index(request: web.Request) -> web.FileResponse:
        root = Path(__file__).parent / "views" / "management"
        filename = "index.html" if request[AUTHENTICATED] else "login.html"
        response = web.FileResponse(root / filename)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        return response

    async def asset(request: web.Request) -> web.StreamResponse:
        root = (Path(__file__).parent / "views" / "management").resolve()
        path = (root / request.match_info["asset"]).resolve()
        if root not in path.parents or not path.is_file():
            raise web.HTTPNotFound()
        response = web.FileResponse(path)
        if path.suffix == ".css":
            response.headers["Content-Type"] = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            response.headers["Content-Type"] = "application/javascript; charset=utf-8"
        return response

    async def login(request: web.Request) -> web.Response:
        if not password:
            return web.json_response({"authenticated": True})
        now = time.monotonic()
        client_id = request.remote or "unknown"
        recent = [stamp for stamp in login_attempts.get(client_id, []) if now - stamp < LOGIN_WINDOW]
        if len(recent) >= LOGIN_LIMIT:
            return web.json_response({"error": "尝试次数过多，请一分钟后再试"}, status=429)
        try:
            payload = await request.json()
        except (ValueError, web.HTTPException):
            payload = {}
        candidate = payload.get("password") if isinstance(payload, dict) else None
        if not isinstance(candidate, str) or not hmac.compare_digest(candidate, password):
            recent.append(now)
            if len(login_attempts) >= 4096 and client_id not in login_attempts:
                oldest = min(login_attempts, key=lambda key: login_attempts[key][-1])
                login_attempts.pop(oldest, None)
            login_attempts[client_id] = recent
            return web.json_response({"error": "密码不正确"}, status=401)

        login_attempts.pop(client_id, None)
        response = web.json_response({"authenticated": True})
        response.set_cookie(
            SESSION_COOKIE,
            _session_value(session_secret, int(time.time())),
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="Strict",
            path="/",
            secure=request.secure,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def logout(_: web.Request) -> web.Response:
        response = web.json_response({"logged_out": True})
        response.del_cookie(SESSION_COOKIE, path="/")
        return response

    for endpoint in endpoint_names:
        methods = ("GET",) if endpoint in ("status", "items", "targets") else (("GET", "POST") if endpoint == "subscriptions" else ("POST",))
        for method in methods:
            app.router.add_route(method, f"/api/{endpoint}", api_handler(endpoint), name=f"api_{endpoint.replace('/', '_')}_{method.lower()}")
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/", index)
    app.router.add_get("/{asset:.*}", asset)
    return app
