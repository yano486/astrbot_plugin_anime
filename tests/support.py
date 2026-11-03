"""Small test-only AstrBot doubles; production imports remain strict."""

import importlib.util
import logging
from pathlib import Path
import sys
import types


def install_astrbot_stubs():
    if "astrbot.api.star" in sys.modules or importlib.util.find_spec("astrbot"):
        return

    astrbot = types.ModuleType("astrbot")
    astrbot.__path__ = []
    api = types.ModuleType("astrbot.api")
    api.__path__ = []
    api.logger = logging.getLogger("anime.tests")
    api.AstrBotConfig = dict
    event = types.ModuleType("astrbot.api.event")
    star = types.ModuleType("astrbot.api.star")

    def decorator(*args, **kwargs):
        return lambda value: value

    event.filter = types.SimpleNamespace(
        command=decorator,
        permission_type=decorator,
        PermissionType=types.SimpleNamespace(ADMIN="admin"),
    )
    event.AstrMessageEvent = object

    class MessageChain:
        def message(self, text):
            self.text = text
            return self

        def file_image(self, path):
            self.image_path = path
            return self

    class Star:
        def __init__(self, context):
            self.context = context

    event.MessageChain = MessageChain
    star.Star = Star
    star.Context = object
    star.StarTools = types.SimpleNamespace(get_data_dir=lambda: Path("test-data"))
    star.register = decorator
    sys.modules.update({
        "astrbot": astrbot,
        "astrbot.api": api,
        "astrbot.api.event": event,
        "astrbot.api.star": star,
    })
