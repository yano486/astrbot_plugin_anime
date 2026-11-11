from __future__ import annotations

from string import Formatter
from typing import Any, Mapping


_COMMON = {
    "title", "item_type", "reminder_label", "beijing_time", "japan_time",
    "display_time", "source", "schedule_note", "weekday", "raw_time",
    "lead_minutes", "release_date", "release_timezone", "target", "count",
    "failed_sources", "subscriptions",
}

VARIABLE_DESCRIPTIONS = {
    "title": "动画名称",
    "item_type": "动画类型",
    "reminder_label": "提醒标题",
    "beijing_time": "北京时间",
    "japan_time": "日本时间",
    "display_time": "当前设置的显示时间",
    "source": "数据来源",
    "schedule_note": "排期说明",
    "weekday": "星期",
    "raw_time": "来源原始时间",
    "lead_minutes": "提前分钟数",
    "release_date": "上映日期",
    "release_timezone": "上映日期时区",
    "target": "推送目标",
    "count": "数量",
    "failed_sources": "失败来源",
    "subscriptions": "订阅列表",
    "subscription_hint": "订阅提示",
    "error": "错误信息",
}

TEMPLATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "push_not_subscribed": {"label": "推送目标未订阅", "description": "群聊或会话未开启订阅时的回复", "variables": ()},
    "push_no_anime": {"label": "推送未选动画", "description": "已开启订阅但没有选择动画时的回复", "variables": ()},
    "help_english": {"label": "\u82f1\u6587\u5e2e\u52a9", "description": "/anime help \u7684\u56de\u590d", "variables": ()},
    "help_chinese": {"label": "\u4e2d\u6587\u5e2e\u52a9", "description": "/anime\u5e2e\u52a9 \u7684\u56de\u590d", "variables": ()},
    "command_usage": {"label": "\u547d\u4ee4\u7528\u6cd5", "description": "\u65e0\u6cd5\u8bc6\u522b\u547d\u4ee4\u65f6\u7684\u56de\u590d", "variables": ()},
    "bind_success": {"label": "\u7ed1\u5b9a\u6210\u529f", "description": "\u7ed1\u5b9a\u5f53\u524d\u4f1a\u8bdd\u540e\u7684\u56de\u590d", "variables": ()},
    "bind_failure": {"label": "\u7ed1\u5b9a\u5931\u8d25", "description": "\u65e0\u6cd5\u8bc6\u522b\u7ed1\u5b9a\u76ee\u6807\u65f6\u7684\u56de\u590d", "variables": ()},
    "unbind_success": {"label": "\u89e3\u7ed1\u6210\u529f", "description": "\u89e3\u7ed1\u5f53\u524d\u4f1a\u8bdd\u540e\u7684\u56de\u590d", "variables": ()},
    "unbind_failure": {"label": "\u89e3\u7ed1\u5931\u8d25", "description": "\u65e0\u6cd5\u8bc6\u522b\u89e3\u7ed1\u76ee\u6807\u65f6\u7684\u56de\u590d", "variables": ()},
    "subscription_status": {"label": "\u8ba2\u9605\u72b6\u6001", "description": "\u5f00\u542f\u6216\u5173\u95ed\u81ea\u52a8\u63a8\u9001\u65f6\u7684\u56de\u590d", "variables": ("count", "subscription_hint")},
    "subscription_disabled": {"label": "\u5173\u95ed\u8ba2\u9605", "description": "\u5173\u95ed\u81ea\u52a8\u63a8\u9001\u540e\u7684\u56de\u590d", "variables": ()},
    "unknown_session": {"label": "\u65e0\u6cd5\u8bc6\u522b\u4f1a\u8bdd", "description": "\u65e0\u6cd5\u8bc6\u522b\u5f53\u524d\u7fa4\u804a\u6216\u4f1a\u8bdd\u65f6\u7684\u56de\u590d", "variables": ()},
    "no_movie_selection": {"label": "\u672a\u9009\u62e9\u5267\u573a\u7248", "description": "\u6ca1\u6709\u9009\u62e9\u5267\u573a\u7248\u6216 OVA \u65f6\u7684\u56de\u590d", "variables": ()},
    "no_subscription": {"label": "\u6ca1\u6709\u8ba2\u9605", "description": "\u6ca1\u6709\u627e\u5230\u8ba2\u9605\u65f6\u7684\u56de\u590d", "variables": ()},
    "list_empty": {"label": "\u8ba2\u9605\u5217\u8868\u4e3a\u7a7a", "description": "\u8ba2\u9605\u5217\u8868\u6ca1\u6709\u542f\u7528\u4f5c\u54c1\u65f6\u7684\u56de\u590d", "variables": ()},
    "list_result": {"label": "\u8ba2\u9605\u5217\u8868", "description": "\u5c55\u793a\u5f53\u524d\u4f1a\u8bdd\u8ba2\u9605\u65f6\u7684\u56de\u590d", "variables": ("subscriptions",)},
    "refresh_result": {"label": "\u5237\u65b0\u7ed3\u679c", "description": "\u7ba1\u7406\u5458\u5237\u65b0\u756a\u7ec4\u540e\u7684\u56de\u590d", "variables": ("count", "failed_sources")},
    "reminder_lead": {"label": "\u63d0\u524d\u63d0\u9192", "description": "TV/WEB \u52a8\u753b\u63d0\u524d\u63d0\u9192\u6587\u672c", "variables": tuple(sorted(_COMMON))},
    "reminder_on_time": {"label": "\u6309\u65f6\u64ad\u51fa", "description": "TV/WEB \u52a8\u753b\u6309\u65f6\u64ad\u51fa\u6587\u672c", "variables": tuple(sorted(_COMMON))},
    "movie_reminder": {"label": "\u5267\u573a\u7248/OVA\u63d0\u9192", "description": "\u5267\u573a\u7248\u548c OVA \u4e0a\u6620\u65e5\u671f\u63d0\u9192\u6587\u672c", "variables": tuple(sorted(_COMMON))},
    "test_message": {"label": "\u6d4b\u8bd5\u6d88\u606f", "description": "WebUI \u6587\u5b57\u63a8\u9001\u6d4b\u8bd5\u6587\u672c", "variables": ()},
    "image_error": {"label": "\u56fe\u7247\u751f\u6210\u5931\u8d25", "description": "\u56fe\u7247\u8868\u751f\u6210\u5931\u8d25\u65f6\u7684\u56de\u590d", "variables": ("error",)},
}

DEFAULT_MESSAGE_TEMPLATES = {
    "push_not_subscribed": "订阅群没有订阅，请先使用 /anime 订阅 开启。",
    "push_no_anime": "未添加动画推送，请在 WebUI 勾选动画并保存订阅。",
    "help_english": "Commands: /anime help, /anime push (today), /anime week (this week), /anime ova (selected movies/OVA), /anime sub (enable reminders).\nChinese suffixes are also supported: \u63a8\u9001\u3001\u672c\u5468\u3001\u5267\u573a\u7248\u3001\u8ba2\u9605\u3002\n/anime\u7ed1\u5b9a binds the current conversation, /anime\u89e3\u7ed1 removes it, /anime\u5217\u8868 shows subscriptions, and /anime\u5237\u65b0 refreshes the current season.",
    "help_chinese": "\u4e3b\u8981\u547d\u4ee4：/anime push（\u4eca\u65e5\u756a\u7ec4）、/anime week（\u672c\u5468\u756a\u7ec4）、/anime ova（\u5df2\u9009\u5267\u573a\u7248/OVA\u756a\u7ec4）、/anime sub（\u5f00\u542f\u81ea\u52a8\u63a8\u9001）。\n\u540e\u7f00\u4e5f\u652f\u6301\u4e2d\u6587：\u63a8\u9001、\u672c\u5468、\u5267\u573a\u7248、\u8ba2\u9605。\n/anime\u7ed1\u5b9a - \u7ed1\u5b9a\u5f53\u524d\u7fa4/\u4f1a\u8bdd\u4e3a WebUI \u63a8\u9001\u76ee\u6807\n/anime\u89e3\u7ed1 - \u89e3\u7ed1\u5f53\u524d\u76ee\u6807\n/anime\u5217\u8868 - \u67e5\u770b\u5f53\u524d\u76ee\u6807\u8ba2\u9605\n/anime\u5237\u65b0 - \u7ba1\u7406\u5458\u5237\u65b0\u5f53\u5b63\u52a8\u753b\n\u5728 AstrBot \u63d2\u4ef6\u8be6\u60c5\u9875\u6253\u5f00“\u52a8\u753b\u8ba2\u9605”\u8fdb\u884c\u7b5b\u9009\u548c\u52fe\u9009。",
    "command_usage": "\u547d\u4ee4：/anime help、/anime push、/anime week、/anime ova、/anime sub（\u4e2d\u6587\u540e\u7f00\u4e5f\u652f\u6301）",
    "bind_success": "\u5df2\u7ed1\u5b9a\u5f53\u524d\u4f1a\u8bdd。\u73b0\u5728\u53ef\u4ee5\u5728 WebUI \u4e2d\u9009\u62e9\u5b83\u4f5c\u4e3a\u52a8\u753b\u63d0\u9192\u76ee\u6807。",
    "bind_failure": "\u65e0\u6cd5\u8bc6\u522b\u5f53\u524d\u4f1a\u8bdd\u76ee\u6807，\u8bf7\u68c0\u67e5 AstrBot \u7248\u672c。",
    "unbind_success": "\u5f53\u524d\u4f1a\u8bdd\u5df2\u89e3\u7ed1，\u76f8\u5173\u52a8\u753b\u8ba2\u9605\u4e5f\u5df2\u79fb\u9664。",
    "unbind_failure": "\u65e0\u6cd5\u8bc6\u522b\u5f53\u524d\u4f1a\u8bdd\u76ee\u6807。",
    "subscription_status": "\u5df2\u5f00\u542f\u81ea\u52a8\u63a8\u9001\u5e76\u52a0\u5165\u767d\u540d\u5355，\u5171\u8ba2\u9605 {count} \u90e8\u52a8\u753b。{subscription_hint}\u5173\u95ed\u8bf7\u7528 /anime sub off \u6216 /anime \u8ba2\u9605 \u5173\u95ed。",
    "subscription_disabled": "\u5df2\u5173\u95ed\u81ea\u52a8\u63a8\u9001，\u5e76\u4ece\u767d\u540d\u5355\u79fb\u9664\u5f53\u524d\u4f1a\u8bdd。",
    "unknown_session": "\u65e0\u6cd5\u8bc6\u522b\u5f53\u524d\u7fa4\u804a/\u4f1a\u8bdd。",
    "no_movie_selection": "\u5f53\u524d\u4f1a\u8bdd\u5c1a\u672a\u5728 WebUI \u9009\u62e9\u5267\u573a\u7248/OVA；\u8bf7\u5728\u7247\u5355\u7b5b\u9009\u4e2d\u9009\u597d\u540e\u4fdd\u5b58\u8ba2\u9605。",
    "no_subscription": "\u5f53\u524d\u4f1a\u8bdd\u8fd8\u6ca1\u6709\u52a8\u753b\u8ba2\u9605。\u8bf7\u5148 /anime\u7ed1\u5b9a，\u518d\u5230 WebUI \u52fe\u9009\u4f5c\u54c1。",
    "list_empty": "\u6682\u65e0\u542f\u7528\u7684\u52a8\u753b\u8ba2\u9605。",
    "list_result": "\u5f53\u524d\u4f1a\u8bdd\u8ba2\u9605：\n{subscriptions}",
    "refresh_result": "\u756a\u7ec4\u5237\u65b0\u5b8c\u6210：{count} \u90e8\u4f5c\u54c1。{failed_sources}",
    "reminder_lead": "📺 \u52a8\u753b{reminder_label}\n{title}\n{beijing_time}\n{japan_time}\n\u6570\u636e\u6765\u6e90：{source}{schedule_note}",
    "reminder_on_time": "📺 \u52a8\u753b{reminder_label}\n{title}\n{beijing_time}\n{japan_time}\n\u6570\u636e\u6765\u6e90：{source}{schedule_note}",
    "movie_reminder": "🎬 {item_type} {reminder_label}\n{title}\n\u4e0a\u6620\u65e5\u671f：{release_timezone} {release_date}{schedule_note}\n\u6570\u636e\u6765\u6e90：{source}",
    "test_message": "🔔 \u52a8\u753b\u8ba2\u9605\u6d4b\u8bd5\u6d88\u606f：\u6b64\u4f1a\u8bdd\u53ef\u4ee5\u63a5\u6536\u63d2\u4ef6\u63a8\u9001。",
    "image_error": "\u56fe\u7247\u8868\u751f\u6210\u5931\u8d25：{error}",
}

# Older stores persisted the full defaults; match the whole template to preserve edits.
LEGACY_DEFAULT_MESSAGE_TEMPLATES = {
    "help_chinese": DEFAULT_MESSAGE_TEMPLATES["help_chinese"]
        .replace("\u4eca\u65e5\u756a\u7ec4", "\u4eca\u65e5\u64ad\u653e\u8868")
        .replace("\u672c\u5468\u756a\u7ec4", "\u672c\u5468\u64ad\u653e\u8868")
        .replace("OVA\u756a\u7ec4", "OVA\u4e0a\u6620\u8868"),
    "refresh_result": "\u52a8\u753b\u8868\u5237\u65b0\u5b8c\u6210：{count} \u90e8\u4f5c\u54c1。{failed_sources}",
}

_FORMATTER = Formatter()


def template_context(values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {key: "" if value is None else value for key, value in (values or {}).items()}


def _placeholder_names(template: str) -> set[str]:
    try:
        names = set()
        for _, field_name, _, _ in _FORMATTER.parse(template):
            if field_name:
                if any(char in field_name for char in ".[]"):
                    raise ValueError("invalid template field")
                names.add(field_name)
        return names
    except (ValueError, IndexError) as exc:
        raise ValueError("invalid template syntax") from exc


def validate_message_templates(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("message_templates must be an object")
    result: dict[str, str] = {}
    for key, template in value.items():
        if key not in TEMPLATE_DEFINITIONS:
            raise ValueError(f"unknown template key: {key}")
        if not isinstance(template, str) or len(template) > 4000:
            raise ValueError(f"template {key} must be a string of at most 4000 characters")
        names = _placeholder_names(template)
        allowed = set(TEMPLATE_DEFINITIONS[key]["variables"])
        unknown = names - allowed
        if unknown:
            raise ValueError(f"unknown variable in {key}: {sorted(unknown)[0]}")
        result[key] = template
    return result


def render_template(key: str, values: Mapping[str, Any] | None = None, overrides: Mapping[str, str] | None = None) -> str:
    if key not in DEFAULT_MESSAGE_TEMPLATES:
        raise ValueError(f"unknown template key: {key}")
    template = (overrides or {}).get(key, DEFAULT_MESSAGE_TEMPLATES[key])
    validate_message_templates({key: template})
    return template.format_map(template_context(values))


def template_definitions() -> list[dict[str, Any]]:
    return [
        {"key": key, "label": value["label"], "description": value["description"],
         "variables": list(value["variables"]),
         "variable_descriptions": {name: VARIABLE_DESCRIPTIONS.get(name, name) for name in value["variables"]},
         "default": DEFAULT_MESSAGE_TEMPLATES[key]}
        for key, value in TEMPLATE_DEFINITIONS.items()
    ]
