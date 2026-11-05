from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

from .core.models import Target
from .core.diagnostics import configure_plugin_logging, get_plugin_logger
from .services.scheduler import ReminderScheduler
from .services.refresh import RefreshService
from .core.store import JsonStore
from .web.api import AnimeWebAPI
from .rendering.push_tables import Airing, airings_between, cleanup_generated_tables, render_airings_image, render_weekly_image, render_notification_card, upcoming_movies
from .rendering.templates import render_template, template_context
from .core.time_utils import BJ, JST


plugin_logger = get_plugin_logger()


PLUGIN_VERSION = "0.3.0"


@register("astrbot_plugin_anime", "486", "日本动画季度订阅和排期提醒", PLUGIN_VERSION)
class AnimePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self.remote_webui_enabled = False
        self.remote_webui_password_enabled = False
        self.remote_webui_url = ""
        self._remote_runner = None
        data_dir = Path(StarTools.get_data_dir())
        self.data_dir = data_dir
        self.store = JsonStore(data_dir / "anime_state.json")
        self.session: aiohttp.ClientSession | None = None
        self.refresh_service: RefreshService | None = None
        self.scheduler: ReminderScheduler | None = None
        self.web_api = AnimeWebAPI(self)
        self._initial_refresh: asyncio.Task | None = None
        self._refresh_task: asyncio.Task | None = None

    @staticmethod
    def current_season(now: datetime | None = None) -> str:
        now = now or datetime.now(BJ)
        month = ((now.month - 1) // 3) * 3 + 1
        return f"{now.year}-{month:02d}"

    async def initialize(self) -> None:
        log_path = configure_plugin_logging(self.data_dir, astrbot_logger=logger)
        plugin_logger.info("[anime] 插件启动，日志文件：%s", log_path)
        self._cleanup_generated_tables()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        try:
            self.refresh_service = RefreshService(
                self.session,
                self.store,
                bangumi_token=str(self.config.get("bangumi_api_token", "")),
                bangumi_proxy=str(self.config.get("bangumi_proxy", "")),
            )
            if self.refresh_service.bangumi.proxy_url:
                plugin_logger.info("[anime] Bangumi 代理已启用：%s", self.refresh_service.bangumi.proxy_url)
        except ValueError as exc:
            plugin_logger.error("[anime] Bangumi 代理配置无效，将使用直连：%s", exc)
            self.refresh_service = RefreshService(
                self.session,
                self.store,
                bangumi_token=str(self.config.get("bangumi_api_token", "")),
            )
        self.web_api.register()
        await self._start_remote_webui()
        self.scheduler = ReminderScheduler(self.store, self._deliver)
        await self.scheduler.start()
        self._refresh_task = asyncio.create_task(self._refresh_periodically())
        if self._season_catalog_needs_refresh() or self._movie_catalog_needs_refresh():
            self._initial_refresh = asyncio.create_task(self._refresh_quietly())

    async def terminate(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        tasks = [task for task in (self._initial_refresh, self._refresh_task) if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.session and not self.session.closed:
            await self.session.close()
        if self._remote_runner:
            await self._remote_runner.cleanup()
            self._remote_runner = None
            self.remote_webui_enabled = False
            self.remote_webui_password_enabled = False

    async def _start_remote_webui(self) -> None:
        if not bool(self.config.get("remote_webui_enabled", True)):
            return
        configured_password = self.config.get("remote_webui_password", "")
        password = "" if configured_password is None else str(configured_password)
        from .web.server import create_remote_web_app, validate_remote_password

        try:
            password = validate_remote_password(password)
        except ValueError as exc:
            logger.error(f"[anime] 远程 WebUI 未启动：{exc}；请清空密码或设置 1-8 位数字。")
            return
        if not password:
            logger.warning("[anime] 远程 WebUI 未设置密码，将允许访问端口的局域网设备直接管理。请勿暴露到公网。")
        host = str(self.config.get("remote_webui_host", "0.0.0.0")).strip() or "0.0.0.0"
        try:
            port = int(self.config.get("remote_webui_port", 1876))
        except (TypeError, ValueError):
            logger.error("[anime] 远程 WebUI 端口无效。")
            return
        if not 1 <= port <= 65535:
            logger.error("[anime] 远程 WebUI 端口必须在 1-65535 之间。")
            return
        from aiohttp import web

        runner = web.AppRunner(create_remote_web_app(self, password), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        try:
            await site.start()
        except OSError as exc:
            await runner.cleanup()
            logger.error(f"[anime] 远程 WebUI 启动失败（{host}:{port}）：{exc}")
            return
        self._remote_runner = runner
        self.remote_webui_enabled = True
        self.remote_webui_password_enabled = bool(password)
        self.remote_webui_url = (
            f"监听 {host}:{port}；请用设备局域网 IP 访问 http://<设备局域网IP>:{port}"
            if host == "0.0.0.0"
            else f"http://{host}:{port}"
        )
        logger.info(f"[anime] 远程 WebUI 已启动：{self.remote_webui_url}")

    async def _refresh_quietly(self) -> None:
        try:
            if self._season_catalog_needs_refresh():
                await self.refresh_service.refresh(self.current_season())
            if self._movie_catalog_needs_refresh():
                await self.refresh_service.refresh_movies(datetime.now(BJ).date())
        except Exception as exc:
            logger.warning(f"[anime] 初始刷新失败: {exc}")

    async def _refresh_periodically(self) -> None:
        while True:
            await asyncio.sleep(6 * 60 * 60)
            try:
                await self.refresh_service.refresh(self.current_season())
                if self._movie_catalog_needs_refresh():
                    await self.refresh_service.refresh_movies(datetime.now(BJ).date())
            except Exception as exc:
                logger.warning(f"[anime] 定时刷新失败: {exc}")

    def _movie_catalog_needs_refresh(self) -> bool:
        today = datetime.now(BJ).date()
        last_year = today.year + (1 if today.month == 12 else 0)
        expected_scope = f"{today.year}-{last_year}"
        if self.store.state.get("movie_catalog_scope") != expected_scope:
            return True
        updated = self.store.state.get("movie_catalog_updated_at", "")
        try:
            refreshed_at = datetime.fromisoformat(updated)
        except (TypeError, ValueError):
            return True
        if refreshed_at.tzinfo is None:
            refreshed_at = refreshed_at.replace(tzinfo=BJ)
        return (datetime.now(BJ) - refreshed_at.astimezone(BJ)).total_seconds() >= 24 * 60 * 60

    def _season_catalog_needs_refresh(self) -> bool:
        if self.store.state.get("season") != self.current_season():
            return True
        expected_sources = {"bangumi", "bgmlist", "yuc"}
        if set(self.store.state.get("source_status", {})) != expected_sources:
            return True
        preferences = self.store.get_preferences()
        if self.store.state.get("schedule_source_mode", "earliest") != preferences.get("schedule_source", "earliest"):
            return True
        retired_sources = {"acgsecrets", "youranimes"}
        return any(
            retired_sources.intersection(item.sources)
            or len(item.schedules) > 1
            or item.data_status == "conflict"
            for item in self.store.get_items()
        )

    async def _deliver(self, target_id: str, text: str) -> bool:
        chain = MessageChain().message(text)
        result = await self.context.send_message(target_id, chain)
        if result is False:
            raise RuntimeError("AstrBot reported that the target message was not sent")
        return True

    async def _deliver_card(self, target_id: str, item, mode: str) -> bool:
        from uuid import uuid4

        self._cleanup_generated_tables()
        path = self.data_dir / "push_tables" / f"{uuid4().hex}.png"
        preferences = self.store.get_preferences()
        try:
            await asyncio.to_thread(
                render_notification_card,
                item,
                mode,
                path,
                preferences["display_timezone"],
            )
            chain = MessageChain().file_image(str(path))
            result = await self.context.send_message(target_id, chain)
            if result is False:
                raise RuntimeError("AstrBot reported that the target card was not sent")
            return True
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _action_name(event: AstrMessageEvent, action: str) -> tuple[str, str]:
        tokens = str(action or "").strip().split(maxsplit=1)
        message = str(getattr(event, "message_str", "")).strip().lstrip("/")
        full = message.split(maxsplit=2)
        if len(full) >= 2 and full[0].casefold() == "anime":
            tokens = full[1:]
        if tokens and tokens[0].lstrip("/").casefold() == "anime":
            tokens = tokens[1:]
        elif tokens and tokens[0].lstrip("/").casefold().startswith("anime") and len(tokens[0]) > 5:
            tokens[0] = tokens[0].lstrip("/")[5:]
        if not tokens:
            message = str(getattr(event, "message_str", "")).strip().lstrip("/")
            parts = message.split(maxsplit=2)
            tokens = parts[1:] if parts and parts[0].lower().startswith("anime") else []
        if not tokens:
            return "", ""
        raw = tokens[0].casefold()
        extra = tokens[1] if len(tokens) > 1 else ""
        aliases = {
            "help": "help", "帮助": "help",
            "push": "push", "推送": "push",
            "week": "week", "本周": "week",
            "ova": "ova", "剧场版": "ova", "电影": "ova",
            "sub": "sub", "订阅": "sub",
        }
        return aliases.get(raw, raw), extra

    def _reply(self, key: str, values: dict[str, Any] | None = None) -> str:
        preferences = self.store.get_preferences()
        return render_template(key, template_context(values), preferences.get("message_templates", {}))

    async def _send_airings_image(self, event: AstrMessageEvent, title: str, rows) -> Any:
        from uuid import uuid4

        self._cleanup_generated_tables()
        path = self.data_dir / "push_tables" / f"{uuid4().hex}.png"
        try:
            preferences = self.store.get_preferences()
            renderer = render_weekly_image if title == "本周动画播放表" else render_airings_image
            await asyncio.to_thread(renderer, title, rows, path, preferences["display_timezone"])
        except Exception as exc:
            logger.error(f"[anime] 图表生成失败: {exc}")
            return event.plain_result(self._reply("image_error", {"error": str(exc)}))
        return event.image_result(str(path))

    def _cleanup_generated_tables(self) -> None:
        try:
            removed = cleanup_generated_tables(self.data_dir / "push_tables")
        except OSError as exc:
            plugin_logger.warning("[anime] 清理过期推送图片失败：%s", exc)
            return
        if removed:
            plugin_logger.info("[anime] 已清理 %s 张过期推送图片", removed)

    @filter.command("anime")
    async def anime_command(self, event: AstrMessageEvent, action: str = ""):
        """Anime schedule tables, subscriptions, help, and reminder management."""
        action_name, extra = self._action_name(event, action)
        if action_name == "help":
            yield event.plain_result(self._reply("help_english"))
            return
        if action_name not in {"push", "week", "ova", "sub"}:
            yield event.plain_result(self._reply("command_usage"))
            return

        if action_name == "sub":
            target_id = getattr(event, "unified_msg_origin", None)
            if not target_id:
                yield event.plain_result(self._reply("unknown_session"))
                return
            if extra.casefold() in {"off", "stop", "关", "关闭"}:
                target = self.store.state.setdefault("targets", {}).get(target_id)
                if target is None:
                    yield event.plain_result(self._reply("no_subscription"))
                    return
                target["subscribed"] = False
                target["whitelisted"] = False
                self.store.save()
                yield event.plain_result(self._reply("subscription_disabled"))
                return

            target = self.store.state.setdefault("targets", {}).get(target_id)
            if target is None:
                display_name = ""
                try:
                    display_name = event.get_sender_name()
                except Exception:
                    pass
                self.store.upsert_target(Target(target_id, display_name, getattr(event, "platform_name", ""), True, datetime.now().isoformat()))
                target = self.store.state["targets"][target_id]
            configured = [sub for sub in self.store.get_subscriptions(target_id) if sub.enabled]
            target["whitelisted"] = True
            target["subscribed"] = True
            target["enabled"] = True
            self.store.save()
            hint = ""
            if not configured:
                hint = "请在 WebUI 选择该群要提醒的作品和提前分钟数；选好之前不会发送提醒。"
            yield event.plain_result(self._reply("subscription_status", {"count": len(configured), "subscription_hint": hint}))
            return

        preferences = self.store.get_preferences()
        display_timezone = preferences["display_timezone"]
        display_zone = JST if display_timezone == "Asia/Tokyo" else BJ
        now = datetime.now(BJ).astimezone(display_zone)
        if action_name == "ova":
            target_id = getattr(event, "unified_msg_origin", None)
            if not target_id:
                yield event.plain_result(self._reply("unknown_session"))
                return
            movie_items = {item.key: item for item in self.store.get_movie_items()}
            selected_keys = {
                sub.anime_key for sub in self.store.get_subscriptions(target_id)
                if sub.enabled and sub.anime_key in movie_items
            }
            if not selected_keys:
                yield event.plain_result(self._reply("no_movie_selection"))
                return
            selected_items = []
            selected_by_key = {}
            for key in selected_keys:
                item = movie_items[key]
                override = self.store.get_movie_release_override(key)
                if override:
                    try:
                        parsed = datetime.fromisoformat(override)
                        parsed = parsed.replace(tzinfo=BJ) if parsed.tzinfo is None else parsed.astimezone(BJ)
                        item = replace(item, release_date=parsed.date().isoformat())
                    except ValueError:
                        pass
                selected_items.append(item)
                selected_by_key[key] = item
            rows = upcoming_movies(selected_items, now.date())
            adjusted = []
            for row in rows:
                adjusted.append(Airing(selected_by_key[row.item.key], None, row.at))
            yield await self._send_airings_image(event, "已选剧场版与OVA上映表", adjusted)
            return

        all_items = [item for item in self.store.get_items() if item.region in ("jp", "mixed")]

        if action_name == "push":
            start = datetime.combine(now.date(), time.min, display_zone)
            end = start + timedelta(days=1)
            title = "今日动画播放表"
        else:
            monday = now.date() - timedelta(days=now.isoweekday() - 1)
            start = datetime.combine(monday, time.min, display_zone)
            end = start + timedelta(days=7)
            title = "本周动画播放表"
        rows = airings_between(all_items, start, end)
        yield await self._send_airings_image(event, title, rows)

    @filter.command("anime帮助")
    async def help(self, event: AstrMessageEvent):
        """Show the Chinese command help message."""
        yield event.plain_result(self._reply("help_chinese"))

    @filter.command("anime绑定")
    async def bind_target(self, event: AstrMessageEvent):
        """Bind the current conversation as a WebUI push target."""
        target_id = getattr(event, "unified_msg_origin", None)
        if not target_id:
            yield event.plain_result(self._reply("bind_failure"))
            return
        name = ""
        try:
            name = event.get_sender_name()
        except Exception:
            pass
        self.store.upsert_target(Target(target_id, name, getattr(event, "platform_name", ""), True, datetime.now().isoformat()))
        self.store.save()
        yield event.plain_result(self._reply("bind_success"))

    @filter.command("anime解绑")
    async def unbind_target(self, event: AstrMessageEvent):
        """Unbind the current conversation and remove its subscriptions."""
        target_id = getattr(event, "unified_msg_origin", None)
        if not target_id:
            yield event.plain_result(self._reply("unbind_failure"))
            return
        self.store.remove_target(target_id)
        self.store.save()
        yield event.plain_result(self._reply("unbind_success"))

    @filter.command("anime列表")
    async def list_subscriptions(self, event: AstrMessageEvent):
        """List enabled subscriptions for the current conversation."""
        target_id = getattr(event, "unified_msg_origin", "")
        titles = {item.key: item.title_cn or item.title for item in self.store.get_items()}
        subs = self.store.get_subscriptions(target_id)
        if not subs:
            yield event.plain_result(self._reply("no_subscription"))
            return
        lines = [f"- {titles.get(sub.anime_key, sub.anime_key)}：提前 {sub.lead_minutes} 分钟" for sub in subs if sub.enabled]
        if not lines:
            yield event.plain_result(self._reply("list_empty"))
            return
        yield event.plain_result(self._reply("list_result", {"subscriptions": "\n".join(lines)}))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("anime刷新")
    async def refresh(self, event: AstrMessageEvent):
        """Refresh the current season catalog; administrator only."""
        result = await self.refresh_service.refresh(self.current_season())
        failed = [name for name, status in result["sources"].items() if status["status"] == "error"]
        failed_text = " 失败来源：" + ", ".join(failed) if failed else ""
        yield event.plain_result(self._reply("refresh_result", {"count": len(result["items"]), "failed_sources": failed_text}))

