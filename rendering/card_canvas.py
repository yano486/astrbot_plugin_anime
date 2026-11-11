from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..core.diagnostics import get_plugin_logger


logger = get_plugin_logger()
PALETTES = {
    "dark": {"bg": "#101b21", "panel": "#192a32", "soft": "#1d323b", "ink": "#e5f0f1", "muted": "#a7bec4", "line": "#36515a", "accent": "#67b5c4"},
    "light": {"bg": "#e8f0f2", "panel": "#fbfdfd", "soft": "#f2f7f7", "ink": "#18343d", "muted": "#526e76", "line": "#b7ced2", "accent": "#2f7182"},
}


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False):
    suffix = "Bold" if bold else "Regular"
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        f"/system/fonts/NotoSansCJK-{suffix}.ttc",
        f"/usr/share/fonts/opentype/noto/NotoSansCJK-{suffix}.ttc",
        f"/usr/share/fonts/truetype/noto/NotoSansCJK-{suffix}.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("未找到中文字体，请安装 Noto CJK 或文泉驿字体后重试")


def lines(text: str, width: int, size: int, bold: bool = False) -> list[str]:
    face = font(size, bold)
    result = []
    for paragraph in str(text).split("\n"):
        line = ""
        for char in paragraph:
            if line and face.getlength(line + char) > width:
                result.append(line.rstrip())
                line = char.lstrip()
            else:
                line += char
        result.append(line.rstrip())
    return result or [""]


def text_height(text: str, width: int, size: int, bold: bool = False) -> int:
    return len(lines(text, width, size, bold)) * (size + 9)


class CardCanvas:
    def __init__(self, width: int, height: int, theme: str):
        if theme not in PALETTES:
            raise ValueError("card_theme must be dark or light")
        if height > 30000:
            raise ValueError("番表内容过多，请缩小推送范围后再生成图片")
        self.colors = PALETTES[theme]
        self.width = width
        self.image = Image.new("RGB", (width, max(height, 300)), self.colors["bg"])
        self.draw = ImageDraw.Draw(self.image)

    def text(self, x: int, y: int, text: str, size: int, color: str = "ink", bold: bool = False, width: int | None = None) -> int:
        wrapped = lines(text, width or self.width - x - 32, size, bold)
        for line in wrapped:
            self.draw.text((x, y), line, font=font(size, bold), fill=self.colors[color])
            y += size + 9
        return y

    def panel(self, box, fill="panel", radius=10):
        self.draw.rounded_rectangle(box, radius=radius, fill=self.colors[fill], outline=self.colors["line"], width=1)

    def cover(self, path: Path | None, box):
        x, y, width, height = box
        if path is not None:
            try:
                with Image.open(path) as original:
                    image = ImageOps.fit(original.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
                mask = Image.new("L", (width, height))
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=6, fill=255)
                self.image.paste(image, (x, y), mask)
                return
            except (OSError, ValueError) as exc:
                logger.warning("[anime] 封面读取失败，将显示占位：%s", exc)
        self.panel((x, y, x + width, y + height), "soft", 6)
        label = "暂无封面" if width >= 100 else "动画"
        self.text(x + 10, y + height // 2 - 12, label, 14, "muted", width=width - 20)

    def header(self, title: str, caption: str, count: int):
        self.text(36, 26, "A  动画订阅", 18, "accent", True)
        self.text(36, 66, title, 36, bold=True, width=960)
        self.text(36, 126, caption, 18, "muted", width=960)
        self.text(1060, 76, str(count), 38, "accent", True, width=105)
        self.text(1060, 130, "部动画", 16, "muted", width=105)
        self.draw.line((36, 178, self.width - 36, 178), fill=self.colors["line"])

    def footer(self, y: int):
        self.draw.line((36, y, self.width - 36, y), fill=self.colors["line"])
        self.text(36, y + 16, "按排期提醒 · 临时改期以官方信息为准", 16, "muted")

    def save(self, output: Path) -> Path:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(output, format="PNG", optimize=True)
        return output
