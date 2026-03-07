from __future__ import annotations

import asyncio
import math
import os
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from pyrogram.enums import ChatType
from solgram.listener import listener
from solgram.utils import Message, pip_install
from solgram.enums import Client
from solgram.services import sqlite
from solgram import logs

pip_install("pillow")
pip_install("cairocffi")
pip_install("pangocairocffi")
pip_install("aiohttp")

import aiohttp
import cairocffi as cairo
import pangocairocffi as pangocairo
import pangocffi as pango
from PIL import Image

# Pango 单位转换常量（固定值 1024）
PANGO_SCALE = getattr(pango, "SCALE", None) or getattr(pango, "PANGO_SCALE", None) or 1024


def pango_units_from_double(d: float) -> int:
    """将 double 转换为 Pango 单位"""
    if hasattr(pango, "units_from_double"):
        return pango.units_from_double(d)
    return int(d * PANGO_SCALE)

# ============== 配置常量 (对齐 quote-api) ==============

PLUGIN_DIR = Path(__file__).parent
ASSETS_DIR = PLUGIN_DIR / "qn_assets"
EMOJI_CACHE_DIR = ASSETS_DIR / "emoji_cache"
AVATAR_CACHE_DIR = ASSETS_DIR / "avatar_cache"

# ==================== 颜色配置 ====================
BASE_BUBBLE_COLOR = "#292232"
TEXT_COLOR = "#FFFFFF"
LINK_COLOR = "#6AB7FF"
CODE_COLOR = "#5887a7"

# 用户名颜色 - 深色背景版 (按 user_id % 7 分配)
USERNAME_COLORS = [
    "#FF8E86",  # 红
    "#FFA357",  # 橙
    "#B18FFF",  # 紫
    "#4DD6BF",  # 青
    "#45E8D1",  # 青绿
    "#7AC9FF",  # 蓝
    "#FF7FD5",  # 粉
]

# ==================== 字体配置 ====================
FONT_FAMILY = "Noto Sans, Noto Sans CJK SC"  # 不含 Noto Color Emoji (避免数字被渲染为 emoji 字形, emoji 由 Twemoji 图片处理)
FONT_SIZE_USERNAME = 44         # 用户名字号 (quote-api: 22 * scale)
FONT_SIZE_TEXT = 48             # 正文字号 (quote-api: 24 * scale)

# 回复消息字体
FONT_SIZE_REPLY_NAME = 32       # 回复者名字 (quote-api: 16 * scale)
FONT_SIZE_REPLY_TEXT = 42       # 回复内容 (quote-api: 21 * scale)

# ==================== 布局配置 ====================
SCALE = 2.0
AVATAR_SIZE = 100               # 头像尺寸 (quote-api: 50 * scale)
AVATAR_TOP_OFFSET = 10          # 头像顶部偏移 (quote-api: 5 * scale)
BUBBLE_RADIUS = 50              # 气泡圆角 (quote-api: 25 * scale)
BUBBLE_PADDING = 28             # 气泡内边距 (quote-api: indent = 14 * scale)
BUBBLE_MIN_WIDTH = 200
BUBBLE_MAX_WIDTH = 1024         # 气泡最大宽度 (quote-api: width * scale = 512 * 2)
AVATAR_BUBBLE_GAP = 20          # 头像与气泡间距 (quote-api: 10 * scale)
CANVAS_PADDING = 20
QUOTE_MARGIN = 10
NAME_TEXT_GAP = 7               # 用户名与正文间距 (quote-api: indent * 0.25)

# 回复消息布局
REPLY_LINE_WIDTH = 6            # 回复竖线宽度 (quote-api: 3 * scale)
REPLY_INDENT = 10               # 回复区域左侧缩进

# 媒体布局
MEDIA_BORDER_RADIUS = 10        # 媒体图片圆角 (quote-api: 5 * scale)

# ==================== Emoji 配置 ====================
EMOJI_CDN_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72"
EMOJI_RENDER_SIZE = 36

# ==================== 输出配置 ====================
STICKER_MAX_SIZE = 512
OUTPUT_FORMAT = "WEBP"

MEDIA_MAX_SIZE = 300
DEFAULT_AVATAR_COLOR = (128, 128, 128, 255)

EMOJI_RANGES = [
    (0x1F600, 0x1F64F),
    (0x1F300, 0x1F5FF),
    (0x1F680, 0x1F6FF),
    (0x1F1E6, 0x1F1FF),
    (0x2702, 0x27B0),
    (0x1F900, 0x1F9FF),
    (0x1FA00, 0x1FA6F),
    (0x1FA70, 0x1FAFF),
    (0x2600, 0x26FF),
]
EMOJI_SINGLE = {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139}
SKIN_TONE_RANGE = (0x1F3FB, 0x1F3FF)
REGIONAL_INDICATOR_RANGE = (0x1F1E6, 0x1F1FF)
ZWJ = "\u200d"
VS16 = "\ufe0f"
KEYCAP_MARK = "\u20e3"
KEYCAP_BASES = set("0123456789#*")


# ==================== 工具函数 ====================


def ensure_dirs():
    EMOJI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)


ensure_dirs()

userid_list = sqlite.get("q_userid_list", []) or []


def get_custom_username(user_id):
    """从 sqlite 获取自定义用户名"""
    user_list = sqlite.get("q_userid_list") or []
    for user_data in user_list:
        if user_data.get("id") == user_id:
            return user_data.get("username")
    return None


def color_luminance(hex_color: str, lum: float) -> str:
    """调整颜色亮度，lum > 0 变亮，lum < 0 变暗"""
    hex_color = hex_color.lstrip("#")
    rgb = [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]
    result = []
    for c in rgb:
        c = int(c + (c * lum))
        c = max(0, min(255, c))
        result.append(f"{c:02x}")
    return "#" + "".join(result)


BUBBLE_COLOR_1 = color_luminance(BASE_BUBBLE_COLOR, 0.35)
BUBBLE_COLOR_2 = color_luminance(BASE_BUBBLE_COLOR, -0.15)


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """#292232 → (0.16, 0.13, 0.20)"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def get_username_color(user_id: int | None) -> str:
    """根据用户 ID 分配固定颜色"""
    if user_id is None:
        return USERNAME_COLORS[0]
    return USERNAME_COLORS[user_id % len(USERNAME_COLORS)]


def emoji_to_codepoint(emoji: str) -> str:
    """😀 → '1f600', 👨‍👩‍👧 → '1f468-200d-1f469-200d-1f467'"""
    return "-".join(f"{ord(c):x}" for c in emoji)


def escape_pango_markup(text: str) -> str:
    """转义 Pango Markup 特殊字符"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_utf16_index_map(text: str) -> list[int]:
    total_units = 0
    for ch in text:
        total_units += 2 if ord(ch) > 0xFFFF else 1
    index_map = [0] * (total_units + 1)
    cu_pos = 0
    py_index = 0
    for ch in text:
        cu_len = 2 if ord(ch) > 0xFFFF else 1
        for step in range(1, cu_len + 1):
            index_map[cu_pos + step] = py_index + 1
        cu_pos += cu_len
        py_index += 1
    return index_map


def build_utf8_index_map(text: str) -> list[int]:
    offsets = [0] * (len(text) + 1)
    total = 0
    for i, ch in enumerate(text):
        total += len(ch.encode("utf-8"))
        offsets[i + 1] = total
    return offsets


def pil_image_to_surface(image: Image.Image) -> cairo.ImageSurface:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    width, height = image.size
    buf = bytearray(image.tobytes("raw", "BGRA"))
    surface = cairo.ImageSurface.create_for_data(
        buf,
        cairo.FORMAT_ARGB32,
        width,
        height,
        width * 4,
    )
    surface._buffer = buf
    return surface


def surface_to_pil(surface: cairo.ImageSurface) -> Image.Image:
    width = surface.get_width()
    height = surface.get_height()
    data = surface.get_data()
    image = Image.frombuffer("RGBA", (width, height), data, "raw", "BGRA", 0, 1)
    return image.copy()


def get_default_avatar() -> Image.Image:
    return Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), DEFAULT_AVATAR_COLOR)


def _in_ranges(code: int, ranges) -> bool:
    for start, end in ranges:
        if start <= code <= end:
            return True
    return False


def _is_emoji_base(ch: str) -> bool:
    code = ord(ch)
    if code in EMOJI_SINGLE:
        return True
    return _in_ranges(code, EMOJI_RANGES)


def _is_skin_tone(ch: str) -> bool:
    code = ord(ch)
    return SKIN_TONE_RANGE[0] <= code <= SKIN_TONE_RANGE[1]


def _is_regional_indicator(ch: str) -> bool:
    code = ord(ch)
    return REGIONAL_INDICATOR_RANGE[0] <= code <= REGIONAL_INDICATOR_RANGE[1]


def _is_variation_selector(ch: str) -> bool:
    return ch == VS16


def _is_zwj(ch: str) -> bool:
    return ch == ZWJ


def detect_emojis(text: str) -> list[dict]:
    """检测文本中的 emoji 及其位置"""
    results = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in KEYCAP_BASES:
            if i + 1 < len(text) and text[i + 1] == KEYCAP_MARK:
                results.append({"emoji": text[i:i + 2], "start": i, "end": i + 2})
                i += 2
                continue
            if (
                i + 2 < len(text)
                and text[i + 1] == VS16
                and text[i + 2] == KEYCAP_MARK
            ):
                results.append({"emoji": text[i:i + 3], "start": i, "end": i + 3})
                i += 3
                continue
        if _is_regional_indicator(ch) and i + 1 < len(text) and _is_regional_indicator(text[i + 1]):
            results.append({"emoji": text[i:i + 2], "start": i, "end": i + 2})
            i += 2
            continue
        if _is_emoji_base(ch):
            start = i
            i += 1
            if i < len(text) and _is_variation_selector(text[i]):
                i += 1
            if i < len(text) and _is_skin_tone(text[i]):
                i += 1
            while i < len(text) and _is_zwj(text[i]):
                if i + 1 < len(text) and _is_emoji_base(text[i + 1]):
                    i += 1
                    i += 1
                    if i < len(text) and _is_variation_selector(text[i]):
                        i += 1
                    if i < len(text) and _is_skin_tone(text[i]):
                        i += 1
                else:
                    break
            results.append({"emoji": text[start:i], "start": start, "end": i})
            continue
        i += 1
    return results


def _entity_type_name(entity) -> str:
    raw = getattr(entity, "type", None)
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        return str(raw.value)
    if isinstance(raw, str):
        return raw
    raw_str = str(raw)
    if "." in raw_str:
        raw_str = raw_str.split(".")[-1]
    return raw_str.lower()


# ==================== Emoji 缓存 ====================


class EmojiCache:
    _memory_cache = OrderedDict()
    _memory_cache_max_size = 100

    @classmethod
    async def get(cls, emoji: str) -> Image.Image | None:
        if not emoji:
            return None
        codepoint = emoji_to_codepoint(emoji)
        if not codepoint:
            return None
        if codepoint in cls._memory_cache:
            img = cls._memory_cache.pop(codepoint)
            cls._memory_cache[codepoint] = img
            return img.copy()
        cache_path = cls._get_cache_path(codepoint)
        if cache_path.exists():
            try:
                img = Image.open(cache_path).convert("RGBA")
                cls._add_to_memory_cache(codepoint, img)
                return img.copy()
            except Exception as exc:
                logs.warning(f"Emoji 缓存读取失败: {exc}")
        data = await cls._download_from_cdn(codepoint)
        if data:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
            except Exception:
                pass
            try:
                img = Image.open(BytesIO(data)).convert("RGBA")
                cls._add_to_memory_cache(codepoint, img)
                return img.copy()
            except Exception as exc:
                logs.warning(f"Emoji 解码失败: {exc}")
        return None

    @classmethod
    async def _download_from_cdn(cls, codepoint: str) -> bytes | None:
        url = f"{EMOJI_CDN_BASE}/{codepoint}.png"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as exc:
            logs.warning(f"Emoji 下载失败: {exc}")
        return None

    @classmethod
    def _get_cache_path(cls, codepoint: str) -> Path:
        return EMOJI_CACHE_DIR / f"{codepoint}.png"

    @classmethod
    def _add_to_memory_cache(cls, key: str, image: Image.Image):
        if key in cls._memory_cache:
            cls._memory_cache.pop(key)
        cls._memory_cache[key] = image
        while len(cls._memory_cache) > cls._memory_cache_max_size:
            cls._memory_cache.popitem(last=False)

    @classmethod
    async def preload(cls, emojis: list[str]) -> dict[str, Image.Image]:
        unique = list(dict.fromkeys(emojis))
        if not unique:
            return {}
        results = await asyncio.gather(*[cls.get(e) for e in unique])
        return {emoji: img for emoji, img in zip(unique, results) if img}


# ==================== Entity 解析 ====================


ENTITY_MARKUP_MAP = {
    "bold": ("<b>", "</b>"),
    "italic": ("<i>", "</i>"),
    "code": ("<tt>", "</tt>"),
    "pre": ("<tt>", "</tt>"),
    "strikethrough": ("<s>", "</s>"),
    "underline": ("<u>", "</u>"),
    "text_link": (f'<span foreground="{LINK_COLOR}">', "</span>"),
    "mention": (f'<span foreground="{LINK_COLOR}">', "</span>"),
    "text_mention": (f'<span foreground="{LINK_COLOR}">', "</span>"),
    "url": (f'<span foreground="{LINK_COLOR}">', "</span>"),
    "email": (f'<span foreground="{LINK_COLOR}">', "</span>"),
}


def entities_to_pango_markup(
    text: str,
    entities: list | None,
    emoji_spans: list[dict] | None = None,
) -> str:
    """将 Telegram 消息文本和 entities 转换为 Pango Markup。

    使用 boundary-based 算法确保标签正确嵌套，避免重叠 entity 产生
    无效的 Pango 标签结构。
    """
    if not text:
        return ""

    # ---- 解析 entity 范围 (UTF-16 offset → Python str index) ----
    entity_ranges: list[tuple[int, int, str, str]] = []
    if entities:
        index_map = build_utf16_index_map(text)
        total_units = len(index_map) - 1
        for entity in entities:
            entity_type = _entity_type_name(entity)
            if entity_type not in ENTITY_MARKUP_MAP:
                continue
            try:
                offset = int(getattr(entity, "offset", 0))
                length = int(getattr(entity, "length", 0))
            except Exception:
                continue
            if length <= 0 or offset < 0 or offset + length > total_units:
                continue
            start = index_map[offset]
            end = index_map[offset + length]
            if start >= end:
                continue
            open_tag, close_tag = ENTITY_MARKUP_MAP[entity_type]
            entity_ranges.append((start, end, open_tag, close_tag))

    # ---- 构建 emoji 区间映射 ----
    emoji_intervals: list[tuple[int, int]] = []
    if emoji_spans:
        for span in emoji_spans:
            s = span.get("start")
            e = span.get("end")
            if isinstance(s, int) and isinstance(e, int) and s < e:
                emoji_intervals.append((s, e))

    # ---- 收集所有边界点 ----
    boundaries = {0, len(text)}
    for s, e, _, _ in entity_ranges:
        boundaries.add(s)
        boundaries.add(e)
    for s, e in emoji_intervals:
        boundaries.add(s)
        boundaries.add(e)
    boundaries = sorted(boundaries)

    # ---- 按段生成 markup (保证标签正确嵌套) ----
    result: list[str] = []
    current_open: list[int] = []  # 已打开的 entity 索引列表 (有序)

    for bi in range(len(boundaries) - 1):
        seg_start = boundaries[bi]
        seg_end = boundaries[bi + 1]

        # 计算当前段的 active entity 集合
        new_active: set[int] = set()
        for idx, (s, e, _, _) in enumerate(entity_ranges):
            if s <= seg_start and e >= seg_end:
                new_active.add(idx)

        # 如果 active 集合变化，关闭所有旧标签，打开所有新标签
        if set(current_open) != new_active:
            for idx in reversed(current_open):
                result.append(entity_ranges[idx][3])
            current_open = sorted(new_active)
            for idx in current_open:
                result.append(entity_ranges[idx][2])

        # 检查当前段是否在 emoji 区间内
        in_emoji = False
        for es, ee in emoji_intervals:
            if es <= seg_start and ee >= seg_end:
                in_emoji = True
                break

        seg_text = text[seg_start:seg_end]
        if in_emoji:
            result.append('<span alpha="0">')
            result.append(escape_pango_markup(seg_text))
            result.append("</span>")
        else:
            result.append(escape_pango_markup(seg_text))

    # 关闭剩余标签
    for idx in reversed(current_open):
        result.append(entity_ranges[idx][3])

    return "".join(result)


# ==================== Cairo / Pango 渲染 ====================


class QuoteRenderer:
    def __init__(self, scale: float = SCALE):
        self.scale = scale

    def _create_layout(self, ctx, markup: str, font_size: int, max_width: int, single_line: bool = False):
        layout = pangocairo.create_layout(ctx)
        max_width = max(1, int(max_width))
        width_units = pango_units_from_double(max_width)
        if hasattr(layout, "set_width"):
            layout.set_width(width_units)
        else:
            try:
                layout.width = width_units
            except Exception:
                logs.warning("Pango layout width setter unavailable.")
        if hasattr(layout, "set_wrap"):
            layout.set_wrap(pango.WrapMode.WORD_CHAR)
        else:
            try:
                layout.wrap = pango.WrapMode.WORD_CHAR
            except Exception:
                logs.warning("Pango layout wrap setter unavailable.")

        # 单行模式：限制行数 + 省略号截断
        if single_line:
            # Pango: set_height(-N) 表示最多 N 行
            if hasattr(layout, "set_height"):
                layout.set_height(-1)
            else:
                try:
                    layout.height = -1
                except Exception:
                    pass
            # 启用末尾省略号
            ellipsize_end = getattr(pango, "EllipsizeMode", None)
            if ellipsize_end:
                ellipsize_val = getattr(ellipsize_end, "END", None)
            else:
                ellipsize_val = None
            if ellipsize_val is not None:
                if hasattr(layout, "set_ellipsize"):
                    layout.set_ellipsize(ellipsize_val)
                else:
                    try:
                        layout.ellipsize = ellipsize_val
                    except Exception:
                        pass

        font_desc = pango.FontDescription()
        if hasattr(font_desc, "set_family"):
            font_desc.set_family(FONT_FAMILY)
        else:
            try:
                font_desc.family = FONT_FAMILY
            except Exception:
                logs.warning("Pango font family setter unavailable.")
        size_units = pango_units_from_double(font_size)
        if hasattr(font_desc, "set_size"):
            font_desc.set_size(size_units)
        else:
            try:
                font_desc.size = size_units
            except Exception:
                logs.warning("Pango font size setter unavailable.")
        if hasattr(layout, "set_font_description"):
            layout.set_font_description(font_desc)
        else:
            try:
                layout.font_description = font_desc
            except Exception:
                logs.warning("Pango layout font setter unavailable.")
        if hasattr(layout, "apply_markup"):
            layout.apply_markup(markup)
        elif hasattr(layout, "set_markup"):
            layout.set_markup(markup)
        else:
            try:
                layout.text = markup
            except Exception:
                logs.warning("Pango layout text/markup setter unavailable.")
        return layout

    def _get_layout_logical_rect(self, layout) -> tuple[float, float, float, float]:
        if hasattr(layout, "get_pixel_extents"):
            _, logical = layout.get_pixel_extents()
            return logical.x, logical.y, logical.width, logical.height
        if hasattr(layout, "get_extents"):
            _, logical = layout.get_extents()
            return (
                logical.x / PANGO_SCALE,
                logical.y / PANGO_SCALE,
                logical.width / PANGO_SCALE,
                logical.height / PANGO_SCALE,
            )
        if hasattr(layout, "get_pixel_size"):
            width, height = layout.get_pixel_size()
            return 0.0, 0.0, width, height
        if hasattr(layout, "get_size"):
            width, height = layout.get_size()
            return 0.0, 0.0, width / PANGO_SCALE, height / PANGO_SCALE
        return 0.0, 0.0, 1.0, 1.0

    def _rounded_rect_path(self, ctx, x, y, width, height, radius):
        radius = min(radius, width / 2, height / 2)
        ctx.new_path()
        ctx.arc(x + radius, y + radius, radius, math.pi, 1.5 * math.pi)
        ctx.arc(x + width - radius, y + radius, radius, 1.5 * math.pi, 2 * math.pi)
        ctx.arc(x + width - radius, y + height - radius, radius, 0, 0.5 * math.pi)
        ctx.arc(x + radius, y + height - radius, radius, 0.5 * math.pi, math.pi)
        ctx.close_path()

    def draw_gradient_bubble(
        self,
        width: int,
        height: int,
        radius: int,
        color1: str,
        color2: str,
    ) -> cairo.ImageSurface:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        gradient = cairo.LinearGradient(0, 0, width, height)
        gradient.add_color_stop_rgb(0, *hex_to_rgb(color1))
        gradient.add_color_stop_rgb(1, *hex_to_rgb(color2))
        ctx.set_source(gradient)
        self._rounded_rect_path(ctx, 0, 0, width, height, radius)
        ctx.fill()
        return surface

    def draw_circular_avatar(self, image: Image.Image, size: int) -> cairo.ImageSurface:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        ctx = cairo.Context(surface)
        ctx.arc(size / 2, size / 2, size / 2, 0, 2 * math.pi)
        ctx.clip()
        avatar_surface = pil_image_to_surface(image)
        ctx.set_source_surface(avatar_surface, 0, 0)
        ctx.paint()
        return surface

    def draw_reply_line(self, height: int, line_width: int, color: str) -> cairo.ImageSurface:
        """绘制回复消息左侧竖线"""
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, line_width + 4, height)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_source_rgb(*hex_to_rgb(color))
        ctx.set_line_width(line_width)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.move_to(line_width / 2 + 2, 2)
        ctx.line_to(line_width / 2 + 2, height - 2)
        ctx.stroke()
        return surface

    def round_image(self, image: Image.Image, radius: int) -> cairo.ImageSurface:
        """将图片裁切为圆角矩形"""
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        w, h = image.size
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        self._rounded_rect_path(ctx, 0, 0, w, h, radius)
        ctx.clip()
        img_surface = pil_image_to_surface(image)
        ctx.set_source_surface(img_surface, 0, 0)
        ctx.paint()
        return surface

    async def render_reply_preview(
        self,
        reply_name: str,
        reply_text: str,
        reply_user_id: int,
        reply_entities: list | None,
        max_width: int,
    ) -> tuple[cairo.ImageSurface, int, int]:
        """渲染回复消息预览 (竖线 + 名字 + 文本)

        布局对齐 quote-api:
        - replyName: bold, FONT_SIZE_REPLY_NAME, 彩色
        - replyText: 单行截断 (maxHeight = fontSize), FONT_SIZE_REPLY_TEXT
        - 竖线高度 = name_h + text_h * 0.4
        """
        name_color = get_username_color(reply_user_id)
        content_max_w = max_width - REPLY_LINE_WIDTH - REPLY_INDENT

        # 渲染名字 (粗体, 单行)
        name_markup = f"<b>{escape_pango_markup(reply_name)}</b>"
        name_surface, name_w, name_h = self.render_text(
            name_markup,
            FONT_SIZE_REPLY_NAME,
            content_max_w,
            color=name_color,
            single_line=True,
        )

        # 渲染文本 (单行，对齐 quote-api: maxHeight = fontSize)
        text_surface, text_w, text_h = await self.render_text_with_emoji(
            reply_text,
            reply_entities,
            FONT_SIZE_REPLY_TEXT,
            content_max_w,
            color=TEXT_COLOR,
            single_line=True,
        )

        # 计算布局 (对齐 quote-api)
        # render_text 返回的尺寸包含 padding=2 的边距
        # text_y: 名字下方紧贴，减去 padding 重叠区实现紧凑布局
        text_y = name_h - 4  # 重叠 padding 区域
        total_h = text_y + text_h

        # 竖线高度 (对齐 quote-api: replyName.height + replyText.height * 0.4)
        line_height = max(name_h + int(text_h * 0.4), 8)

        # 绘制竖线
        line_surface = self.draw_reply_line(line_height, REPLY_LINE_WIDTH, name_color)

        # 组合
        content_w = max(name_w, text_w)
        total_w = REPLY_LINE_WIDTH + REPLY_INDENT + content_w

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, total_w, total_h)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()

        # 绘制竖线
        ctx.set_source_surface(line_surface, 0, 0)
        ctx.paint()

        # 绘制名字
        ctx.set_source_surface(name_surface, REPLY_LINE_WIDTH + REPLY_INDENT, 0)
        ctx.paint()

        # 绘制文本
        ctx.set_source_surface(text_surface, REPLY_LINE_WIDTH + REPLY_INDENT, text_y)
        ctx.paint()

        return surface, total_w, total_h

    def measure_text(self, markup: str, font_size: int, max_width: int, single_line: bool = False) -> tuple[int, int]:
        temp_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        temp_ctx = cairo.Context(temp_surface)
        layout = self._create_layout(temp_ctx, markup, font_size, max_width, single_line=single_line)
        _, _, width, height = self._get_layout_logical_rect(layout)
        return max(int(math.ceil(width)), 1), max(int(math.ceil(height)), 1)

    def render_text(
        self,
        markup: str,
        font_size: int,
        max_width: int,
        color: str = TEXT_COLOR,
        single_line: bool = False,
    ) -> tuple[cairo.ImageSurface, int, int]:
        if not markup:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
            return surface, 1, 1
        temp_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        temp_ctx = cairo.Context(temp_surface)
        layout = self._create_layout(temp_ctx, markup, font_size, max_width, single_line=single_line)
        logical_x, logical_y, logical_w, logical_h = self._get_layout_logical_rect(layout)
        width = max(int(math.ceil(logical_w)), 1)
        height = max(int(math.ceil(logical_h)), 1)
        padding = 2

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width + padding * 2, height + padding * 2)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_source_rgb(*hex_to_rgb(color))

        x_offset = -logical_x + padding
        y_offset = -logical_y + padding

        layout = self._create_layout(ctx, markup, font_size, max_width, single_line=single_line)
        ctx.move_to(x_offset, y_offset)
        pangocairo.show_layout(ctx, layout)
        return surface, width + padding * 2, height + padding * 2

    async def render_text_with_emoji(
        self,
        text: str,
        entities: list | None,
        font_size: int,
        max_width: int,
        color: str = TEXT_COLOR,
        single_line: bool = False,
    ) -> tuple[cairo.ImageSurface, int, int]:
        if not text:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
            return surface, 1, 1

        emoji_positions = detect_emojis(text)
        emoji_images = {}
        if emoji_positions:
            unique_emojis = [pos["emoji"] for pos in emoji_positions]
            emoji_images = await EmojiCache.preload(unique_emojis)

        emoji_spans = [pos for pos in emoji_positions if pos["emoji"] in emoji_images]
        markup = entities_to_pango_markup(text, entities, emoji_spans=emoji_spans)
        if not emoji_spans:
            return self.render_text(markup, font_size, max_width, color=color, single_line=single_line)

        temp_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        temp_ctx = cairo.Context(temp_surface)
        layout = self._create_layout(temp_ctx, markup, font_size, max_width, single_line=single_line)
        logical_x, logical_y, logical_w, logical_h = self._get_layout_logical_rect(layout)
        width = max(int(math.ceil(logical_w)), 1)
        height = max(int(math.ceil(logical_h)), 1)
        padding = 2

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width + padding * 2, height + padding * 2)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_source_rgb(*hex_to_rgb(color))

        x_offset = -logical_x + padding
        y_offset = -logical_y + padding

        layout = self._create_layout(ctx, markup, font_size, max_width, single_line=single_line)
        ctx.move_to(x_offset, y_offset)
        pangocairo.show_layout(ctx, layout)

        utf8_offsets = build_utf8_index_map(text)
        for pos in emoji_spans:
            emoji = pos["emoji"]
            img = emoji_images.get(emoji)
            if img is None:
                continue
            start = pos["start"]
            if start >= len(utf8_offsets):
                continue
            byte_index = utf8_offsets[start]
            rect = layout.index_to_pos(byte_index)
            ex = x_offset + rect.x / PANGO_SCALE
            ey = y_offset + rect.y / PANGO_SCALE
            ew = rect.width / PANGO_SCALE
            eh = rect.height / PANGO_SCALE
            size = max(int(font_size * 1.05), int(eh))
            if size <= 0:
                size = EMOJI_RENDER_SIZE
            if ew > 0:
                ex += max((ew - size) / 2, 0)
            if eh > 0:
                ey += max((eh - size) / 2, 0)
            emoji_img = img.resize((size, size), Image.Resampling.LANCZOS)
            emoji_surface = pil_image_to_surface(emoji_img)
            ctx.set_source_surface(emoji_surface, ex, ey)
            ctx.paint()

        return surface, width + padding * 2, height + padding * 2

    def render_username(
        self,
        name: str,
        user_id: int,
        emoji_status_img: Image.Image | None = None,
    ) -> tuple[cairo.ImageSurface, int, int]:
        if not name:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
            return surface, 1, 1
        # quote-api 始终将用户名渲染为粗体, 单行
        name_markup = f"<b>{escape_pango_markup(name)}</b>"
        color = get_username_color(user_id)
        name_surface, name_w, name_h = self.render_text(
            name_markup,
            FONT_SIZE_USERNAME,
            BUBBLE_MAX_WIDTH - BUBBLE_PADDING * 2,
            color=color,
            single_line=True,
        )
        if not emoji_status_img:
            return name_surface, name_w, name_h

        emoji_size = max(int(name_h * 1.1), FONT_SIZE_USERNAME)
        emoji_img = emoji_status_img.resize((emoji_size, emoji_size), Image.Resampling.LANCZOS)
        total_w = name_w + NAME_TEXT_GAP + emoji_size
        total_h = max(name_h, emoji_size)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, total_w, total_h)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_source_surface(name_surface, 0, (total_h - name_h) / 2)
        ctx.paint()
        emoji_surface = pil_image_to_surface(emoji_img)
        ctx.set_source_surface(emoji_surface, name_w + NAME_TEXT_GAP, (total_h - emoji_size) / 2)
        ctx.paint()
        return surface, total_w, total_h

    async def render_quote(
        self,
        message_data: dict,
        show_avatar: bool = True,
        show_name: bool = True,
    ) -> cairo.ImageSurface:
        """渲染完整的引用消息。

        对齐 quote-api drawQuote() 的布局逻辑:
        - 贴纸: 不显示用户名, 气泡仅含回复, 半透明黑色
        - 图片+标题: 先渲染图片, 再渲染标题文字
        - 内容高度、宽度均由内容驱动
        - show_avatar=False: 不绘制头像 (同用户连续消息), 但保留头像空间以对齐气泡
        - show_name=False: 不绘制用户名 (同用户连续消息)
        """
        user_id = message_data.get("user_id", 0)
        username = message_data.get("username") or ""
        avatar_img = message_data.get("avatar") or get_default_avatar()
        emoji_status_img = message_data.get("emoji_status")
        text = message_data.get("text") or ""
        entities = message_data.get("entities")
        media = message_data.get("media")
        media_type = message_data.get("media_type")
        reply_message = message_data.get("reply_message")

        # 贴纸特殊处理：不显示用户名 (对齐 quote-api: if mediaType === 'sticker' name = undefined)
        if media_type == "sticker":
            username = ""

        # 同用户连续消息：不显示用户名
        if not show_name:
            username = ""

        name_surface, name_w, name_h = self.render_username(username, user_id, emoji_status_img)

        # 渲染回复消息预览
        reply_surface = None
        reply_w = 0
        reply_h = 0
        if reply_message:
            reply_surface, reply_w, reply_h = await self.render_reply_preview(
                reply_message.get("name", ""),
                reply_message.get("text", ""),
                reply_message.get("user_id", 0),
                reply_message.get("entities"),
                BUBBLE_MAX_WIDTH - BUBBLE_PADDING * 2,
            )

        # 渲染文本
        text_surface = None
        text_w = 0
        text_h = 0
        if text:
            max_text_width = BUBBLE_MAX_WIDTH - BUBBLE_PADDING * 2
            text_surface, text_w, text_h = await self.render_text_with_emoji(
                text,
                entities,
                FONT_SIZE_TEXT,
                max_text_width,
                color=TEXT_COLOR,
            )

        # 渲染媒体 (不再要求 text 为空才处理)
        media_surface = None
        media_w = 0
        media_h = 0
        if media is not None:
            media_img = media.copy()
            media_img.thumbnail((MEDIA_MAX_SIZE, MEDIA_MAX_SIZE), Image.Resampling.LANCZOS)
            media_w, media_h = media_img.size
            media_surface = self.round_image(media_img, MEDIA_BORDER_RADIUS)

        # ---- 计算内容宽度 ----
        content_width = max(name_w, text_w, media_w, reply_w, BUBBLE_MIN_WIDTH - BUBBLE_PADDING * 2)
        bubble_w = min(max(content_width + BUBBLE_PADDING * 2, BUBBLE_MIN_WIDTH), BUBBLE_MAX_WIDTH)

        # ---- 计算内容高度 (气泡内部) ----
        content_height = 0

        # 1. 用户名
        if name_w > 1:
            content_height += name_h

        # 2. 回复预览
        if reply_w > 0:
            if content_height > 0:
                content_height += NAME_TEXT_GAP
            content_height += reply_h

        # 3. 媒体 (非贴纸，放在气泡内)
        if media_w > 0 and media_type != "sticker":
            if content_height > 0:
                content_height += NAME_TEXT_GAP
            content_height += media_h

        # 4. 文本 (可能在媒体下方，如图片标题)
        if text_w > 0:
            if content_height > 0:
                content_height += NAME_TEXT_GAP
            content_height += text_h

        # ---- 贴纸特殊气泡处理 (对齐 quote-api) ----
        if media_type == "sticker":
            if reply_w > 0:
                bubble_h = reply_h + BUBBLE_PADDING * 2
            else:
                bubble_h = 0
        else:
            bubble_h = content_height + BUBBLE_PADDING * 2

        # ---- 计算画布尺寸 ----
        total_content_h = bubble_h
        if media_type == "sticker" and media_h > 0:
            total_content_h = max(bubble_h, 0) + media_h + (NAME_TEXT_GAP if bubble_h > 0 else 0)

        canvas_w = int(CANVAS_PADDING * 2 + AVATAR_SIZE + AVATAR_BUBBLE_GAP + bubble_w)
        if media_type == "sticker" and media_w > 0:
            canvas_w = max(canvas_w, int(CANVAS_PADDING * 2 + AVATAR_SIZE + AVATAR_BUBBLE_GAP + media_w))

        # bubble_x 始终保持一致 (即使不画头像，也保留头像空间以对齐)
        bubble_x = CANVAS_PADDING + AVATAR_SIZE + AVATAR_BUBBLE_GAP

        if show_avatar:
            # 上对齐 (对齐 quote-api: avatarPosY = 5*scale, blockPosY = 0)
            # 头像上边缘与气泡上边缘对齐 (头像有微小偏移 AVATAR_TOP_OFFSET)
            canvas_h = int(CANVAS_PADDING * 2 + max(AVATAR_SIZE + AVATAR_TOP_OFFSET, total_content_h))
            bubble_y = CANVAS_PADDING
            avatar_x = CANVAS_PADDING
            avatar_y = CANVAS_PADDING + AVATAR_TOP_OFFSET
        else:
            # 无头像时紧凑布局
            canvas_h = int(CANVAS_PADDING + total_content_h + CANVAS_PADDING // 2)
            bubble_y = CANVAS_PADDING // 2

        canvas = cairo.ImageSurface(cairo.FORMAT_ARGB32, canvas_w, canvas_h)
        ctx = cairo.Context(canvas)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()

        # ---- 绘制气泡 ----
        if media_type == "sticker":
            if reply_w > 0:
                # 贴纸有回复：半透明黑色圆角矩形 (对齐 quote-api: rgba(0,0,0,0.5))
                sticker_bubble = cairo.ImageSurface(
                    cairo.FORMAT_ARGB32, int(bubble_w), int(bubble_h)
                )
                sticker_ctx = cairo.Context(sticker_bubble)
                sticker_ctx.set_source_rgba(0, 0, 0, 1)
                self._rounded_rect_path(
                    sticker_ctx, 0, 0, int(bubble_w), int(bubble_h), BUBBLE_RADIUS
                )
                sticker_ctx.fill()
                ctx.set_source_surface(sticker_bubble, bubble_x, bubble_y)
                ctx.paint_with_alpha(0.5)
        else:
            bubble_surface = self.draw_gradient_bubble(
                int(bubble_w),
                int(bubble_h),
                BUBBLE_RADIUS,
                BUBBLE_COLOR_1,
                BUBBLE_COLOR_2,
            )
            ctx.set_source_surface(bubble_surface, bubble_x, bubble_y)
            ctx.paint()

        # ---- 绘制头像 (仅 show_avatar=True) ----
        if show_avatar:
            avatar_surface = self.draw_circular_avatar(avatar_img, AVATAR_SIZE)
            ctx.set_source_surface(avatar_surface, avatar_x, avatar_y)
            ctx.paint()

        # ---- 绘制内容 ----
        content_x = bubble_x + BUBBLE_PADDING
        content_y = bubble_y + BUBBLE_PADDING

        # 1. 用户名
        if name_w > 1:
            ctx.set_source_surface(name_surface, content_x, content_y)
            ctx.paint()
            content_y += name_h + NAME_TEXT_GAP

        # 2. 回复预览
        if reply_surface is not None:
            ctx.set_source_surface(reply_surface, content_x, content_y)
            ctx.paint()
            content_y += reply_h + NAME_TEXT_GAP

        # 3. 媒体 (非贴纸，在气泡内)
        if media_surface is not None and media_type != "sticker":
            ctx.set_source_surface(media_surface, content_x, content_y)
            ctx.paint()
            content_y += media_h + NAME_TEXT_GAP

        # 4. 文本
        if text_surface is not None:
            ctx.set_source_surface(text_surface, content_x, content_y)
            ctx.paint()

        # 5. 贴纸媒体 (在气泡外部下方)
        if media_surface is not None and media_type == "sticker":
            media_y = bubble_y + bubble_h + NAME_TEXT_GAP if bubble_h > 0 else bubble_y
            ctx.set_source_surface(media_surface, content_x, media_y)
            ctx.paint()

        return canvas


# ==================== 主生成器 ====================


async def get_avatar_image(user, client: Client) -> Image.Image | None:
    if not user or not getattr(user, "photo", None):
        return None
    cache_path = AVATAR_CACHE_DIR / f"{user.id}.png"
    if cache_path.exists():
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            try:
                cache_path.unlink()
            except Exception:
                pass
    try:
        file_path = await client.download_media(user.photo.big_file_id)
        avatar = Image.open(file_path).convert("RGBA")
        try:
            avatar.save(cache_path)
        except Exception:
            pass
        os.remove(file_path)
        return avatar
    except Exception as exc:
        logs.warning(f"下载头像失败: {exc}")
        return None


async def get_emoji_status_image(user, client: Client) -> Image.Image | None:
    status = getattr(user, "emoji_status", None)
    if not status or not getattr(status, "custom_emoji_id", None):
        return None
    try:
        sticker_set = await client.get_custom_emoji_stickers([status.custom_emoji_id])
        if not sticker_set:
            return None
        sticker = sticker_set[0]
        file_path = None
        if getattr(sticker, "thumbs", None):
            file_path = await client.download_media(sticker.thumbs[-1])
        else:
            file_path = await client.download_media(sticker)
        if not file_path:
            return None
        image = Image.open(file_path).convert("RGBA")
        os.remove(file_path)
        return image
    except Exception as exc:
        logs.warning(f"下载 emoji_status 失败: {exc}")
        return None


async def get_media_image(message, client: Client) -> Image.Image | None:
    try:
        if message.photo:
            media_file = await client.download_media(message.photo)
        elif message.sticker:
            sticker = message.sticker
            if getattr(sticker, "is_animated", False) or getattr(sticker, "is_video", False):
                if getattr(sticker, "thumbs", None):
                    media_file = await client.download_media(sticker.thumbs[-1])
                else:
                    return None
            else:
                media_file = await client.download_media(sticker)
        else:
            return None
        image = Image.open(media_file).convert("RGBA")
        os.remove(media_file)
        return image
    except Exception as exc:
        logs.warning(f"处理媒体内容时出错: {exc}")
        return None


def get_display_name(user, custom_name: str | None) -> str:
    if custom_name:
        return custom_name
    if not user:
        return "Unknown"
    first_name = getattr(user, "first_name", "") or ""
    last_name = getattr(user, "last_name", "") or ""
    full_name = " ".join(filter(None, [first_name, last_name])).strip()
    if not full_name:
        if getattr(user, "type", None) == ChatType.CHANNEL:
            full_name = getattr(user, "title", "") or ""
        else:
            full_name = getattr(user, "title", "") or ""
    return full_name or "Unknown"


def get_media_type_text(message) -> str:
    """获取媒体类型的显示文本"""
    if message.photo:
        return "图片"
    if message.sticker:
        return "贴纸"
    if message.video:
        return "视频"
    if message.animation:
        return "动图"
    if message.voice:
        return "语音"
    if message.audio:
        return "音频"
    if message.document:
        return "文件"
    if message.video_note:
        return "视频留言"
    if message.contact:
        return "联系人"
    if message.location:
        return "位置"
    if message.poll:
        return "投票"
    return "消息"


def get_media_type(message) -> str | None:
    """获取消息的媒体类型"""
    if message.photo:
        return "photo"
    if message.sticker:
        return "sticker"
    if message.video:
        return "video"
    if message.animation:
        return "animation"
    if message.voice:
        return "voice"
    if message.audio:
        return "audio"
    if message.document:
        return "document"
    return None


def extract_reply_data(reply_message) -> dict | None:
    """提取被回复消息的数据"""
    if not reply_message:
        return None

    user = reply_message.from_user or reply_message.sender_chat
    user_id = getattr(user, "id", 0) if user else 0
    name = get_display_name(user, None)

    # 获取文本内容
    if reply_message.text:
        text = reply_message.text
        entities = reply_message.entities
    elif reply_message.caption:
        text = reply_message.caption
        entities = reply_message.caption_entities
    else:
        # 媒体消息显示类型
        text = get_media_type_text(reply_message)
        entities = None

    # 截断文本为单行
    text = text.split("\n")[0][:100] if text else ""

    return {
        "name": name,
        "text": text,
        "user_id": user_id,
        "entities": entities,
    }


async def extract_message_data(
    message,
    client: Client,
    custom_text: str | None = None,
) -> dict:
    user = message.from_user or message.sender_chat
    user_id = getattr(user, "id", 0) if user else 0
    custom_username = get_custom_username(user_id)
    username = get_display_name(user, custom_username)

    avatar = await get_avatar_image(user, client)
    emoji_status = await get_emoji_status_image(user, client)

    # 提取回复消息数据
    reply_message = extract_reply_data(message.reply_to_message)

    # 获取媒体类型
    media_type = get_media_type(message)

    if custom_text:
        text = custom_text
        entities = None
        media = None
        media_type = None
    else:
        if message.sticker:
            # 贴纸：只有媒体，无文本
            media = await get_media_image(message, client)
            text = ""
            entities = None
        elif message.photo:
            # 图片：媒体 + 可能有标题 (caption)
            media = await get_media_image(message, client)
            text = message.caption or ""
            entities = message.caption_entities if message.caption else None
        else:
            text = message.text or message.caption or "暂未支持的类型"
            entities = message.entities if message.text else message.caption_entities
            media = None

    return {
        "user_id": user_id,
        "username": username,
        "avatar": avatar,
        "emoji_status": emoji_status,
        "text": text,
        "entities": entities,
        "media": media,
        "media_type": media_type,
        "reply_message": reply_message,
    }


def combine_canvases(
    canvases: list[cairo.ImageSurface],
    margin: int = QUOTE_MARGIN,
) -> Image.Image:
    """垂直合并多个 canvas。

    对齐 quote-api: 左对齐 (x=0), 垂直依次排列, 间距 = quoteMargin。
    """
    if not canvases:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    images = [surface_to_pil(c) for c in canvases]
    max_width = max(img.width for img in images)
    total_height = sum(img.height for img in images) + margin * (len(images) - 1)
    final = Image.new("RGBA", (max_width, total_height), (0, 0, 0, 0))
    y_offset = 0
    for img in images:
        # 左对齐 (对齐 quote-api: canvasCtx.drawImage(quoteImages[index], 0, imageY))
        final.paste(img, (0, y_offset), img)
        y_offset += img.height + margin
    return final


def resize_to_sticker(image: Image.Image) -> Image.Image:
    image = image.copy()
    image.thumbnail((STICKER_MAX_SIZE, STICKER_MAX_SIZE), Image.Resampling.LANCZOS)
    return image


def export_webp(image: Image.Image) -> BytesIO:
    output = BytesIO()
    output.name = "sticker.webp"
    image.save(output, OUTPUT_FORMAT)
    output.seek(0)
    return output


async def generate_quote_sticker(
    messages: list,
    client: Client,
    custom_text: str | None = None,
) -> BytesIO:
    """生成引用贴纸。

    同用户连续消息分组 (对齐 quote-bot):
    - 第一条消息: 显示头像 + 用户名
    - 后续消息: 不重复头像和用户名, 气泡位置与第一条对齐
    """
    renderer = QuoteRenderer()
    canvases = []
    prev_user_id = None

    for msg in messages:
        user = msg.from_user or msg.sender_chat
        user_id = getattr(user, "id", 0) if user else 0

        # 同用户连续消息分组: 头像和用户名仅在首条显示
        is_continuation = (user_id == prev_user_id and user_id != 0)
        show_avatar = not is_continuation
        show_name = not is_continuation

        message_data = await extract_message_data(msg, client, custom_text=custom_text)
        canvas = await renderer.render_quote(
            message_data,
            show_avatar=show_avatar,
            show_name=show_name,
        )
        canvases.append(canvas)
        prev_user_id = user_id

    if not canvases:
        raise ValueError("没有可用的消息用于渲染。")
    final = combine_canvases(canvases)
    final = resize_to_sticker(final)
    return export_webp(final)


# ==================== Plugin Commands ====================


@listener(
    outgoing=True,
    command="qn",
    description="将回复的消息转换为引用贴纸，支持 n 条合并",
    parameters="n",
)
async def quote_message(message: Message, client: Client):
    chat_id = message.chat.id
    try:
        args = message.arguments
        custom_text = None
        n = 1

        if args:
            try:
                n = int(args.split()[0])
                if n <= 0:
                    return await message.edit("n 必须是正整数。")
            except ValueError:
                custom_text = args.strip()
                n = 1

        if not message.reply_to_message:
            return await message.edit("请回复一条消息来创建引用贴纸。")

        await message.edit("正在生成贴纸...")

        messages_to_quote = []
        start_message_id = message.reply_to_message.id
        try:
            # 从回复消息向下 (新消息方向) 取 n 条消息
            # 构造候选 ID 列表, 预留空间跳过已删除消息
            candidate_ids = list(range(start_message_id, start_message_id + n * 3))
            fetched = await client.get_messages(chat_id, candidate_ids)
            for msg in fetched:
                if msg and not getattr(msg, "empty", False):
                    messages_to_quote.append(msg)
                if len(messages_to_quote) >= n:
                    break
        except Exception as exc:
            logs.info(f"获取消息时发生其他错误: {exc}")
            return await message.edit("获取消息失败。")

        if not messages_to_quote:
            return await message.edit("没有找到可以引用的消息。")
        output = await generate_quote_sticker(messages_to_quote, client, custom_text=custom_text)
        await message.reply_to_message.reply_sticker(output)
        await message.safe_delete()
    except Exception as exc:
        await message.edit(f"创建引用贴纸时发生错误: {exc}")


@listener(
    outgoing=True,
    command="qnset",
    description="设置引用消息中的自定义用户名",
    parameters="[add/del/list] [自定义用户名]",
)
async def quote_name_settings(message: Message):
    global userid_list

    args = message.arguments.split()
    if not args:
        await message.edit("用法：,qnset [add/del/list] [自定义用户名]")
        await asyncio.sleep(7)
        await message.safe_delete()
        return

    action = args[0].lower()

    if action == "list":
        if not userid_list:
            await message.edit("自定义用户名列表为空")
            await asyncio.sleep(7)
            await message.safe_delete()
            return

        text = "当前自定义用户名列表：\n"
        for user_data in userid_list:
            text += f"ID: {user_data['id']}, 用户名: {user_data['username']}\n"
        await message.edit(text)
        await asyncio.sleep(7)
        await message.safe_delete()
        return

    if action == "add":
        if len(args) < 2:
            await message.edit("添加用法：,qnset add [自定义用户名]")
            await asyncio.sleep(7)
            await message.safe_delete()
            return

        try:
            user_id = int(message.reply_to_message.from_user.id)
            custom_name = "".join(args[1:])

            for user_data in userid_list:
                if user_data["id"] == user_id:
                    user_data["username"] = custom_name
                    sqlite["q_userid_list"] = userid_list
                    await message.edit(f"已更新用户 {user_id} 的自定义名称为：{custom_name}")
                    await asyncio.sleep(7)
                    await message.safe_delete()
                    return

            userid_list.append({"id": user_id, "username": custom_name})
            sqlite["q_userid_list"] = userid_list
            await message.edit(f"已添加用户 {user_id} 的自定义名称：{custom_name}")
            await asyncio.sleep(7)
            await message.safe_delete()
            return

        except ValueError:
            await message.edit("用户ID必须是数字")
            await asyncio.sleep(7)
            await message.safe_delete()
            return

    if action == "del":
        try:
            user_id = int(message.reply_to_message.from_user.id)
            original_length = len(userid_list)
            userid_list = [x for x in userid_list if x["id"] != user_id]

            if len(userid_list) == original_length:
                await message.edit(f"未找到用户ID {user_id} 的记录")
                await asyncio.sleep(7)
                await message.safe_delete()

            sqlite["q_userid_list"] = userid_list
            await message.edit(f"已删除用户 {user_id} 的自定义名称")
            await asyncio.sleep(7)
            await message.safe_delete()
            return

        except ValueError:
            await message.edit("用户ID必须是数字")
            await asyncio.sleep(7)
            await message.safe_delete()
            return

    await message.edit("无效的操作，可用操作：add/del/list")
    await asyncio.sleep(7)
    await message.safe_delete()
