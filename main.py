from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

from .models import Subscription, Target
from .scheduler import ReminderScheduler
from .services import RefreshService
from .store import JsonStore
from .web_api import AnimeWebAPI
from .push_tables import airings_between, render_airings_image
from .time_utils import BJ


@register("astrbot_plugin_anime", "Aut-sep", "日本动画季度订阅和排期提醒", "0.1.0")
class AnimePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
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
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        self.refresh_service = RefreshService(self.session, self.store)
        self.web_api.register()
        self.scheduler = ReminderScheduler(self.store, self._deliver)
        await self.scheduler.start()
        self._refresh_task = asyncio.create_task(self._refresh_periodically())
        if self.store.state.get("season") != self.current_season():
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

    async def _refresh_quietly(self) -> None:
        try:
            await self.refresh_service.refresh(self.current_season())
        except Exception as exc:
            logger.warning(f"[anime] 初始刷新失败: {exc}")

    async def _refresh_periodically(self) -> None:
        while True:
            await asyncio.sleep(6 * 60 * 60)
            try:
                await self.refresh_service.refresh(self.current_season())
            except Exception as exc:
                logger.warning(f"[anime] 定时刷新失败: {exc}")

    async def _deliver(self, target_id: str, text: str) -> bool:
        chain = MessageChain().message(text)
        result = await self.context.send_message(target_id, chain)
        if result is False:
            raise RuntimeError("AstrBot reported that the target message was not sent")
        return True

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
            "push": "push", "推送": "push",
            "week": "week", "本周": "week",
            "ova": "ova", "剧场版": "ova", "电影": "ova",
            "sub": "sub", "订阅": "sub",
        }
        return aliases.get(raw, raw), extra

    async def _send_airings_image(self, event: AstrMessageEvent, title: str, rows) -> Any:
        from uuid import uuid4

        path = self.data_dir / "push_tables" / f"{uuid4().hex}.png"
        try:
            await asyncio.to_thread(render_airings_image, title, rows, path)
        except Exception as exc:
            logger.error(f"[anime] 图表生成失败: {exc}")
            return event.plain_result(f"图片表生成失败：{exc}")
        return event.image_result(str(path))

    @filter.command("anime")
    async def anime_command(self, event: AstrMessageEvent, action: str = ""):
        action_name, extra = self._action_name(event, action)
        if action_name not in {"push", "week", "ova", "sub"}:
            yield event.plain_result("命令：/anime push、/anime week、/anime ova、/anime sub（中文后缀也支持）")
            return

        if action_name == "sub":
            target_id = getattr(event, "unified_msg_origin", None)
            if not target_id:
                yield event.plain_result("无法识别当前群聊/会话。")
                return
            if extra.casefold() in {"off", "stop", "关", "关闭"}:
                target = self.store.state.setdefault("targets", {}).get(target_id)
                if target is None:
                    yield event.plain_result("当前会话还没有订阅设置。")
                    return
                target["subscribed"] = False
                target["whitelisted"] = False
                self.store.save()
                yield event.plain_result("已关闭自动推送，并从白名单移除当前会话。")
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
            message = f"已开启自动推送并加入白名单，共订阅 {len(configured)} 部动画。"
            if not configured:
                message += "请在 WebUI 选择该群要提醒的作品和提前分钟数；选好之前不会发送提醒。"
            yield event.plain_result(message + "关闭请用 /anime sub off 或 /anime 订阅 关闭。")
            return

        all_items = [item for item in self.store.get_items() if item.region in ("jp", "mixed")]
        now = datetime.now(BJ)
        if action_name == "ova":
            rows, source_result = await self.refresh_service.upcoming_movies(now.date(), months=3)
            if source_result.status == "error" and not rows:
                yield event.plain_result(f"剧场版/OVA 数据暂不可用：{source_result.error}")
                return
            yield await self._send_airings_image(event, "近三个月剧场版与OVA", rows)
            return

        if action_name == "push":
            start = datetime.combine(now.date(), time.min, BJ)
            end = start + timedelta(days=1)
            title = "今日动画播放表"
        else:
            monday = now.date() - timedelta(days=now.isoweekday() - 1)
            start = datetime.combine(monday, time.min, BJ)
            end = start + timedelta(days=7)
            title = "本周动画播放表"
        rows = airings_between(all_items, start, end)
        yield await self._send_airings_image(event, title, rows)

    @filter.command("anime帮助")
    async def help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "主要命令：/anime push（今日播放表）、/anime week（本周播放表）、/anime ova（近三个月剧场版/OVA）、/anime sub（开启自动推送）。\n"
            "后缀也支持中文：推送、本周、剧场版、订阅。\n"
            "/anime绑定 - 绑定当前群/会话为 WebUI 推送目标\n"
            "/anime解绑 - 解绑当前目标\n"
            "/anime列表 - 查看当前目标订阅\n"
            "/anime刷新 - 管理员刷新当季动画\n"
            "在 AstrBot 插件详情页打开‘动画订阅’进行筛选和勾选。"
        )

    @filter.command("anime绑定")
    async def bind_target(self, event: AstrMessageEvent):
        target_id = getattr(event, "unified_msg_origin", None)
        if not target_id:
            yield event.plain_result("无法识别当前会话目标，请检查 AstrBot 版本。")
            return
        name = ""
        try:
            name = event.get_sender_name()
        except Exception:
            pass
        self.store.upsert_target(Target(target_id, name, getattr(event, "platform_name", ""), True, datetime.now().isoformat()))
        self.store.save()
        yield event.plain_result("已绑定当前会话。现在可以在 WebUI 中选择它作为动画提醒目标。")

    @filter.command("anime解绑")
    async def unbind_target(self, event: AstrMessageEvent):
        target_id = getattr(event, "unified_msg_origin", None)
        if not target_id:
            yield event.plain_result("无法识别当前会话目标。")
            return
        self.store.remove_target(target_id)
        self.store.save()
        yield event.plain_result("当前会话已解绑，相关动画订阅也已移除。")

    @filter.command("anime列表")
    async def list_subscriptions(self, event: AstrMessageEvent):
        target_id = getattr(event, "unified_msg_origin", "")
        titles = {item.key: item.title_cn or item.title for item in self.store.get_items()}
        subs = self.store.get_subscriptions(target_id)
        if not subs:
            yield event.plain_result("当前会话还没有动画订阅。请先 /anime绑定，再到 WebUI 勾选作品。")
            return
        lines = [f"- {titles.get(sub.anime_key, sub.anime_key)}：提前 {sub.lead_minutes} 分钟" for sub in subs if sub.enabled]
        yield event.plain_result("当前会话订阅：\n" + ("\n".join(lines) if lines else "暂无启用的动画订阅。"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("anime刷新")
    async def refresh(self, event: AstrMessageEvent):
        result = await self.refresh_service.refresh(self.current_season())
        failed = [name for name, status in result["sources"].items() if status["status"] == "error"]
        message = f"动画表刷新完成：{len(result['items'])} 部作品。"
        if failed:
            message += " 失败来源：" + ", ".join(failed)
        yield event.plain_result(message)

