from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import math
import os
import re
import socket
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat
from pydantic import BaseModel, Field

import deps
import database as db
from image_tool_providers import get_image_tool_provider_registry
from provider_queue import run_provider_call

logger = logging.getLogger("image-tools")


class WatermarkRequest(BaseModel):
    image_urls: list[str] = Field(default_factory=list)
    text: str = ""
    position: str = "top_left"
    font_style: str = "rounded"
    font_id: str = ""
    font_url: str = ""
    font_size: int | None = Field(default=None, ge=8, le=256)
    color: str = "#ffffff"
    opacity: float = Field(default=1.0, ge=0, le=100)
    stroke_color: str = "#000000"
    stroke_width: int | None = Field(default=None, ge=0, le=32)
    margin: int | None = Field(default=None, ge=0, le=2048)
    output_mode: str = "separate"
    grid_columns: int = Field(default=3, ge=1, le=3)
    grid_gap: int = Field(default=0, ge=0, le=80)
    grid_cell_size: int = Field(default=1024, ge=256, le=2048)
    grid_background: str = "#ffffff"


class SplitGridRequest(BaseModel):
    image_url: str = ""
    rows: int = Field(default=3, ge=1, le=3)
    columns: int = Field(default=3, ge=1, le=3)


class GenerateNineRequest(BaseModel):
    theme: str = ""
    visual_style: str = ""
    provider: str = "jimeng"
    model: str = "seedream-4.5"
    aspect_ratio: str = "1:1"
    width: int = 1024
    height: int = 1024
    batch_size: int = Field(default=12, ge=1, le=12)
    count: int | None = Field(default=None, ge=1, le=12)
    style_anchor_url: str = ""
    style_lock: str = "strict"
    style_lock_options: list[str] = Field(default_factory=list)
    variation_policy: str = "subject_only"


class GenerateRolesRequest(BaseModel):
    theme: str = ""
    visual_style: str = ""
    roles: list[str] = Field(default_factory=list)
    provider: str = "jimeng"
    model: str = "seedream-4.5"
    aspect_ratio: str = "1:1"
    width: int = 1024
    height: int = 1024
    style_anchor_url: str = ""
    style_lock: str = "strict"
    style_lock_options: list[str] = Field(default_factory=list)
    variation_policy: str = "subject_only"


class DeriveRequest(BaseModel):
    reference_urls: list[str] = Field(default_factory=list)
    mode: str = "微调"
    instruction: str = ""
    provider: str = "jimeng"
    model: str = "seedream-4.5"
    aspect_ratio: str = "1:1"
    width: int = 1024
    height: int = 1024


class ReversePromptsRequest(BaseModel):
    image_urls: list[str] = Field(default_factory=list)
    model: str = "gemini-2.5-flash"


class ReverseStylePromptRequest(BaseModel):
    image_url: str = ""
    model: str = "gemini-2.5-flash"


class PromptPolishRequest(BaseModel):
    theme: str = ""
    visual_style: str = ""
    model: str = "gemini-2.5-flash"


class RoleSuggestionRequest(BaseModel):
    topic: str = ""
    theme: str = ""
    subject_type: str = "object"
    model: str = "gemini-2.5-flash"
    count: int = Field(default=9, ge=1, le=9)


class ImageToolTaskRequest(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


IMAGE_ASPECT_RATIO_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}

MAX_IMAGE_TOOL_INPUT_BYTES = int(os.environ.get("IMAGE_TOOLS_MAX_INPUT_BYTES", str(12 * 1024 * 1024)))
MAX_IMAGE_TOOL_PIXELS = int(os.environ.get("IMAGE_TOOLS_MAX_PIXELS", str(24_000_000)))
MAX_WATERMARK_INPUT_PIXELS = int(os.environ.get("IMAGE_TOOLS_WATERMARK_MAX_PIXELS", str(12_000_000)))
MAX_WATERMARK_FONT_BYTES = int(os.environ.get("IMAGE_TOOLS_WATERMARK_FONT_MAX_BYTES", str(32 * 1024 * 1024)))
IMAGE_TOOLS_LOCAL_CONCURRENCY = max(1, int(os.environ.get("IMAGE_TOOLS_LOCAL_CONCURRENCY", "2") or "2"))
IMAGE_TOOLS_LOCAL_QUEUE_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("IMAGE_TOOLS_LOCAL_QUEUE_TIMEOUT_SECONDS", "30") or "30"),
)
IMAGE_TOOLS_AI_GENERATION_CONCURRENCY = max(
    1,
    int(os.environ.get("IMAGE_TOOLS_AI_GENERATION_CONCURRENCY", "2") or "2"),
)
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
REMOTE_IMAGE_TOOLS_ENABLED = os.environ.get("IMAGE_TOOLS_ALLOW_REMOTE_URLS", "false").lower() in ("true", "1", "yes")
DERIVE_MODE_PROMPTS = {
    "element_replace": "元素替换：保留原图构图、镜头、主体比例、光照和整体风格，只替换用户指定的元素。不要改动未提及部分。",
    "fine_tune": "画面微调：以原图为基础做轻量优化，保持主体、构图、姿势和画幅不变，只调整用户指定的细节。",
    "texture_replace": "质感替换：保留原图主体、构图和镜头，将画面材质、光影或视觉质感替换为用户指定风格。",
    "creative_fusion": "创意融图：融合参考图中的主体、场景或风格元素，生成一张完整、统一、商业可用的游戏素材图。",
}

NINE_IMAGE_VARIATIONS = [
    "主体组合 1：核心主题对象居中，元素清晰完整，适合作为九宫格主视觉。",
    "主体组合 2：更换同主题素材组合，保持相同背景、色调、线条和主体比例。",
    "主体组合 3：加入一个同主题小道具，构图密度与其他图片保持一致。",
    "主体组合 4：主体堆叠方向略有变化，但镜头角度和留白比例保持一致。",
    "主体组合 5：换一组同主题元素，禁止改变背景颜色和整体光照。",
    "主体组合 6：增加少量细节元素，线条粗细、描边方式和色彩饱和度不变。",
    "主体组合 7：主体位置保持居中，换成同系列素材，不做深色或强反差版本。",
    "主体组合 8：主体轮廓与系列一致，背景必须保持同一种干净浅色。",
    "主体组合 9：与主视觉呼应，作为九宫格收束图，仍保持同一模板感。",
    "主体组合 10：同主题备用素材，构图和色彩严格贴近风格样板。",
    "主体组合 11：同主题备用素材，只有内容变化，不改变画面模板。",
    "主体组合 12：同主题备用素材，保持统一朋友圈九图系列感。",
]

NINE_IMAGE_STYLE_LOCK_OPTIONS = {
    "background": "统一背景：所有图片使用同一种白底或浅米底，不允许更换为深色、渐变、场景背景或复杂纹理。",
    "palette": "统一色调：所有图片使用同一套明亮柔和配色，饱和度、明暗和冷暖关系保持一致。",
    "line": "统一线条：所有图片线条粗细、黑色描边、圆润程度和阴影方式保持一致。",
    "camera": "统一视角：所有图片保持同一俯视/正视角度，同一镜头距离，不切换透视。",
    "scale": "统一主体尺寸：主体占画面比例、留白、居中方式和元素密度保持一致。",
}

WATERMARK_OUTPUT_MODES = {"separate", "grid", "both"}
WATERMARK_POSITIONS = {"auto", "top_left", "top_right", "bottom_left", "bottom_right", "center"}
WATERMARK_FONT_STYLES = {"rounded", "bold", "system"}
JIANYING_FONT_KEYWORDS = (
    "DunDun",
    "SourceHanSansCN-Heavy",
    "DaZiBao",
    "黄油",
    "HeiTang",
    "YouQi",
    "Pinocchio",
    "SmileySans",
)
_local_image_semaphores: dict[int, asyncio.Semaphore] = {}
_provider_registry = get_image_tool_provider_registry()
_image_tool_task_runners: dict[str, asyncio.Task] = {}


def _local_image_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    semaphore = _local_image_semaphores.get(loop_id)
    if semaphore is None:
        semaphore = asyncio.Semaphore(IMAGE_TOOLS_LOCAL_CONCURRENCY)
        _local_image_semaphores[loop_id] = semaphore
    return semaphore


@asynccontextmanager
async def _local_image_slot():
    semaphore = _local_image_semaphore()
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=IMAGE_TOOLS_LOCAL_QUEUE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise HTTPException(429, "图片处理请求较多，请稍后重试。") from exc
    try:
        yield
    finally:
        semaphore.release()


def _normalize_urls(urls: list[str], *, max_count: int, label: str) -> list[str]:
    normalized = [url for url in dict.fromkeys(urls or []) if str(url or "").strip()]
    if not normalized:
        raise HTTPException(400, f"请至少上传 1 张{label}。")
    if len(normalized) > max_count:
        raise HTTPException(400, f"单次最多支持 {max_count} 张{label}。")
    return normalized


def prepare_watermark_request(req: WatermarkRequest) -> WatermarkRequest:
    image_urls = _normalize_urls(req.image_urls, max_count=9, label="图片")
    if not (req.text or "").strip():
        raise HTTPException(400, "请填写水印文字。")
    output_mode = req.output_mode if req.output_mode in WATERMARK_OUTPUT_MODES else "separate"
    if output_mode in {"grid", "both"} and len(image_urls) != 9:
        raise HTTPException(400, "九宫格需要 9 张图片，请补齐后再生成。")
    position = req.position if req.position in WATERMARK_POSITIONS else "auto"
    font_style = req.font_style if req.font_style in WATERMARK_FONT_STYLES else "rounded"
    return req.model_copy(update={
        "image_urls": image_urls,
        "output_mode": output_mode,
        "position": position,
        "font_style": font_style,
        "grid_columns": 3,
    })


def prepare_split_grid_request(req: SplitGridRequest) -> SplitGridRequest:
    image_urls = _normalize_urls([req.image_url], max_count=1, label="待切图片")
    return req.model_copy(update={"image_url": image_urls[0], "rows": 3, "columns": 3})


def prepare_generate_nine_request(req: GenerateNineRequest) -> GenerateNineRequest:
    theme = (req.theme or "").strip()
    if not theme:
        raise HTTPException(400, "请填写九图生成主题。")
    provider = req.provider if req.provider in {"jimeng", "gemini_image"} else "jimeng"
    model = (req.model or "").strip()
    if not model:
        model = "gemini-3.1-flash-image-preview" if provider == "gemini_image" else "seedream-4.5"
    requested_count = req.batch_size
    if req.count is not None and req.batch_size == 12:
        requested_count = req.count
    style_lock = req.style_lock if req.style_lock in {"strict", "soft", "off"} else "strict"
    variation_policy = req.variation_policy if req.variation_policy in {"subject_only", "creative"} else "subject_only"
    style_lock_options = [
        item for item in dict.fromkeys(req.style_lock_options or [])
        if item in NINE_IMAGE_STYLE_LOCK_OPTIONS
    ]
    style_anchor_url = (req.style_anchor_url or "").strip()
    if style_lock == "off":
        style_anchor_url = ""
        style_lock_options = []
    elif style_anchor_url:
        style_anchor_url = _normalize_urls([style_anchor_url], max_count=1, label="风格样板图")[0]
    return req.model_copy(update={
        "theme": theme,
        "visual_style": (req.visual_style or "").strip(),
        "provider": provider,
        "model": model,
        "aspect_ratio": req.aspect_ratio or "1:1",
        "batch_size": min(12, max(1, requested_count)),
        "count": min(12, max(1, requested_count)),
        "style_anchor_url": style_anchor_url,
        "style_lock": style_lock,
        "style_lock_options": style_lock_options,
        "variation_policy": variation_policy,
    })


def prepare_generate_roles_request(req: GenerateRolesRequest) -> GenerateRolesRequest:
    theme = (req.theme or "").strip()
    if not theme:
        raise HTTPException(400, "请填写同风格角色九图主题。")
    roles = [str(item or "").strip() for item in req.roles or [] if str(item or "").strip()]
    if len(roles) != 9:
        raise HTTPException(400, "同风格角色九图需要填写 9 个角色或物品名。")
    provider = req.provider if req.provider in {"jimeng", "gemini_image"} else "jimeng"
    model = (req.model or "").strip()
    if not model:
        model = "gemini-3.1-flash-image-preview" if provider == "gemini_image" else "seedream-4.5"
    style_lock = req.style_lock if req.style_lock in {"strict", "soft", "off"} else "strict"
    variation_policy = req.variation_policy if req.variation_policy in {"subject_only", "creative"} else "subject_only"
    style_lock_options = [
        item for item in dict.fromkeys(req.style_lock_options or [])
        if item in NINE_IMAGE_STYLE_LOCK_OPTIONS
    ]
    style_anchor_url = (req.style_anchor_url or "").strip()
    if style_lock == "off":
        style_anchor_url = ""
        style_lock_options = []
    elif style_anchor_url:
        style_anchor_url = _normalize_urls([style_anchor_url], max_count=1, label="风格样板图")[0]
    return req.model_copy(update={
        "theme": theme,
        "visual_style": (req.visual_style or "").strip(),
        "roles": roles,
        "provider": provider,
        "model": model,
        "aspect_ratio": req.aspect_ratio or "1:1",
        "style_anchor_url": style_anchor_url,
        "style_lock": style_lock,
        "style_lock_options": style_lock_options,
        "variation_policy": variation_policy,
    })


def prepare_derive_request(req: DeriveRequest) -> DeriveRequest:
    mode = req.mode if req.mode in DERIVE_MODE_PROMPTS else "fine_tune"
    provider = req.provider if req.provider in {"jimeng", "gemini_image"} else "jimeng"
    model = (req.model or "").strip()
    if not model:
        model = "gemini-3.1-flash-image-preview" if provider == "gemini_image" else "seedream-4.5"
    max_refs = 4 if mode == "creative_fusion" else 1
    reference_urls = _normalize_urls(req.reference_urls, max_count=max_refs, label="参考图")
    return req.model_copy(update={
        "reference_urls": reference_urls,
        "mode": mode,
        "provider": provider,
        "model": model,
        "aspect_ratio": req.aspect_ratio or "1:1",
    })


def prepare_reverse_request(req: ReversePromptsRequest) -> ReversePromptsRequest:
    image_urls = _normalize_urls(req.image_urls, max_count=9, label="图片")
    return req.model_copy(update={"image_urls": image_urls, "model": req.model or "gemini-2.5-flash"})


def _is_private_host(hostname: str) -> bool:
    host = (hostname or "").strip().strip("[]").lower()
    if not host or host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "图片地址不可访问，请先上传图片。")
    if _is_private_host(parsed.hostname):
        raise HTTPException(400, "不支持读取内网或本机图片地址，请先上传图片。")


def _normalize_local_file_url(url: str) -> str:
    raw = str(url or "").strip()
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        raw = parsed.path or ""
    if not raw.startswith("/api/files/"):
        return ""
    filename = raw[len("/api/files/"):].split("?", 1)[0].split("#", 1)[0]
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise HTTPException(400, "文件地址不合法，请重新上传。")
    return f"/api/files/{filename}"


def _normalize_local_image_url(url: str) -> str:
    try:
        return _normalize_local_file_url(url)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, "图片地址不合法，请重新上传图片。") from exc


def _validate_image_bytes(data: bytes, suffix: str) -> str:
    if not data:
        raise HTTPException(400, "图片文件为空，请重新上传。")
    if len(data) > MAX_IMAGE_TOOL_INPUT_BYTES:
        raise HTTPException(413, f"图片不能超过 {MAX_IMAGE_TOOL_INPUT_BYTES // 1024 // 1024} MiB。")
    normalized_suffix = (suffix or "").split("?", 1)[0].lower()
    if normalized_suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(400, "仅支持 PNG、JPG、JPEG、WEBP 图片。")
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if width < 1 or height < 1:
                raise HTTPException(400, "图片尺寸无效，请重新上传。")
            if width * height > MAX_IMAGE_TOOL_PIXELS:
                raise HTTPException(413, "图片分辨率过大，请压缩后再上传。")
            image.verify()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "图片文件无法解析，请重新上传。") from exc
    return normalized_suffix


def _validate_font_bytes(data: bytes, suffix: str) -> str:
    if not data:
        raise HTTPException(400, "字体文件为空，请重新上传。")
    if len(data) > MAX_WATERMARK_FONT_BYTES:
        raise HTTPException(413, f"字体文件不能超过 {MAX_WATERMARK_FONT_BYTES // 1024 // 1024} MiB。")
    normalized_suffix = (suffix or "").split("?", 1)[0].lower()
    if normalized_suffix not in ALLOWED_FONT_SUFFIXES:
        raise HTTPException(400, "仅支持 TTF、OTF、TTC 字体文件。")

    for index in range(4 if normalized_suffix == ".ttc" else 1):
        try:
            ImageFont.truetype(BytesIO(data), size=24, index=index)
            return normalized_suffix
        except OSError:
            continue
    raise HTTPException(400, "字体文件无法解析，请换一个字体文件。")


def _font_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8", "ignore")).hexdigest()[:16]


def _font_display_name(path: Path) -> str:
    name = path.stem
    for prefix in ("HelloFont ID ", "Hellofont ID ", "MF"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.replace("_Noncommercial-Regular", "").replace("-Regular", "").replace(".Regular", "")


def _font_source_label(path: Path) -> str:
    text = str(path)
    if "JianyingPro" in text or "CapCut" in text:
        return "剪映缓存"
    if "watermark_font_" in path.name:
        return "上传字体"
    return "系统字体"


def _font_preview_image(font, text: str) -> Image.Image:
    preview_text = (text or "").strip() or "火锅消除小游戏"
    width, height = 560, 132
    image = Image.new("RGB", (width, height), (244, 241, 228))
    draw = ImageDraw.Draw(image)
    stroke_width = 5
    bbox = draw.textbbox((0, 0), preview_text, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = max(14, (width - text_w) // 2 - bbox[0])
    y = max(10, (height - text_h) // 2 - bbox[1])
    draw.text(
        (x, y),
        preview_text,
        font=font,
        fill=(255, 255, 255),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0),
    )
    return image


def _font_supports_preview_text(font, text: str) -> bool:
    preview_text = (text or "").strip()
    cjk_chars = list(dict.fromkeys(
        char
        for char in preview_text
        if "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
    ))
    if not cjk_chars:
        return True

    glyphs = []
    for char in cjk_chars[:8]:
        try:
            mask = font.getmask(char)
            if mask.getbbox():
                glyphs.append(bytes(mask))
        except Exception:
            return False

    if len(glyphs) < min(2, len(cjk_chars)):
        return False
    return len(set(glyphs)) >= min(2, len(glyphs))


def _save_font_preview(path: Path, text: str) -> dict | None:
    try:
        font = ImageFont.truetype(path, size=54)
    except OSError:
        return None
    if not _font_supports_preview_text(font, text):
        return None
    preview_key = hashlib.sha256(f"{path}:{text}".encode("utf-8", "ignore")).hexdigest()[:16]
    filename = f"font_preview_{preview_key}.png"
    fpath = deps.get_files_dir() / filename
    if not fpath.exists():
        preview = _font_preview_image(font, text)
        try:
            preview.save(fpath, format="PNG")
        finally:
            preview.close()
    return {"url": f"/api/files/{filename}", "filename": filename}


def _save_font_preview_from_bytes(data: bytes, text: str) -> dict | None:
    font = _font_from_bytes(data, 54)
    preview_key = hashlib.sha256(data[:4096] + text.encode("utf-8", "ignore")).hexdigest()[:16]
    filename = f"font_preview_{preview_key}.png"
    fpath = deps.get_files_dir() / filename
    if not fpath.exists():
        preview = _font_preview_image(font, text)
        try:
            preview.save(fpath, format="PNG")
        finally:
            preview.close()
    return {"url": f"/api/files/{filename}", "filename": filename}


def _watermark_font_options(preview_text: str = "火锅消除小游戏") -> list[dict]:
    options = []
    seen: set[str] = set()
    for raw_path in _jianying_font_candidates():
        path = Path(raw_path)
        font_id = _font_id(path)
        if font_id in seen:
            continue
        seen.add(font_id)
        preview = _save_font_preview(path, preview_text)
        if not preview:
            continue
        options.append({
            "id": font_id,
            "name": _font_display_name(path),
            "source": _font_source_label(path),
            "preview_url": preview["url"],
        })
    return options


def list_watermark_fonts(preview_text: str = "火锅消除小游戏") -> dict:
    return {"fonts": _watermark_font_options(preview_text)}


def _font_path_by_id(font_id: str) -> Path | None:
    normalized = (font_id or "").strip()
    if not normalized:
        return None
    for raw_path in _jianying_font_candidates():
        path = Path(raw_path)
        if _font_id(path) == normalized:
            return path
    return None


async def save_watermark_font_upload(file) -> dict:
    source_name = file.filename or "font.ttf"
    suffix = Path(source_name).suffix.lower()
    data = await file.read(MAX_WATERMARK_FONT_BYTES + 1)
    await file.seek(0)
    normalized_suffix = await asyncio.to_thread(_validate_font_bytes, data, suffix)
    fname = f"watermark_font_{uuid.uuid4().hex[:12]}{normalized_suffix}"
    fpath = deps.get_files_dir() / fname
    await asyncio.to_thread(fpath.write_bytes, data)
    deps.notify_media_file_saved(fpath)
    preview = _save_font_preview_from_bytes(data, "火锅消除小游戏")
    return {
        "url": f"/api/files/{fname}",
        "filename": fname,
        "name": source_name,
        "preview_url": preview["url"] if preview else "",
    }


async def _font_bytes_from_id(font_id: str) -> bytes | None:
    path = _font_path_by_id(font_id)
    if not path:
        return None
    data = await asyncio.to_thread(path.read_bytes)
    await asyncio.to_thread(_validate_font_bytes, data, path.suffix.lower())
    return data


async def _read_font_bytes(url: str) -> tuple[bytes, str]:
    local_url = _normalize_local_file_url(url)
    if not local_url:
        raise HTTPException(400, "字体地址不可访问，请先上传字体文件。")
    local = deps.get_local_file_path_from_url(local_url)
    if not local:
        raise HTTPException(400, "字体地址不可访问，请先上传字体文件。")
    data = await asyncio.to_thread(local.read_bytes)
    return data, await asyncio.to_thread(_validate_font_bytes, data, local.suffix.lower())


async def _read_remote_image_bytes(url: str) -> tuple[bytes, str]:
    if not REMOTE_IMAGE_TOOLS_ENABLED:
        raise HTTPException(400, "暂不支持远程图片地址，请先上传图片。")
    _validate_remote_url(url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        async with client.stream("GET", url) as resp:
            if 300 <= resp.status_code < 400:
                raise HTTPException(400, "远程图片重定向暂不支持，请先上传图片。")
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
                raise HTTPException(400, "远程地址不是支持的图片格式。")
            data = bytearray()
            async for chunk in resp.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_IMAGE_TOOL_INPUT_BYTES:
                    raise HTTPException(413, f"图片不能超过 {MAX_IMAGE_TOOL_INPUT_BYTES // 1024 // 1024} MiB。")
    suffix = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(content_type, Path(urlparse(url).path).suffix.lower() or ".png")
    raw = bytes(data)
    return raw, _validate_image_bytes(raw, suffix)


async def _read_image_bytes(url: str) -> tuple[bytes, str]:
    local_url = _normalize_local_image_url(url)
    if local_url:
        local = deps.get_local_file_path_from_url(local_url)
        if not local:
            raise HTTPException(400, f"图片地址不可访问：{url}")
        data = await asyncio.to_thread(local.read_bytes)
        return data, await asyncio.to_thread(_validate_image_bytes, data, local.suffix.lower())
    if url.startswith(("http://", "https://")):
        return await _read_remote_image_bytes(url)
    raise HTTPException(400, f"图片地址不可访问：{url}")


async def _read_gemini_reference_bytes(url: str) -> bytes:
    if url.startswith("data:image"):
        try:
            _, payload = url.split(",", 1)
            return base64.b64decode(payload)
        except Exception as exc:
            raise HTTPException(400, "参考图数据无效，请重新上传图片。") from exc
    data, _ = await _read_image_bytes(url)
    return data


def _rgba(color: str, opacity: float) -> tuple[int, int, int, int]:
    try:
        rgb = ImageColor.getrgb(color or "#ffffff")
    except ValueError:
        rgb = (255, 255, 255)
    alpha = opacity / 100 if opacity > 1 else opacity
    alpha = max(0.0, min(1.0, alpha))
    return rgb[:3] + (int(alpha * 255),)


def _solid_rgb(color: str) -> tuple[int, int, int]:
    try:
        rgb = ImageColor.getrgb(color or "#ffffff")
    except ValueError:
        rgb = (255, 255, 255)
    return rgb[:3]


def _contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in text or ""
    )


def _jianying_font_roots() -> list[Path]:
    env_value = (os.environ.get("IMAGE_TOOLS_JIANYING_FONT_DIRS", "") or "").strip()
    roots = [Path(item).expanduser() for item in env_value.split(os.pathsep) if item.strip()]
    roots.append(Path.home() / "Movies/JianyingPro/User Data/Cache/AITextTemplate/Resource")
    return roots


def _font_keyword_rank(path: Path) -> tuple[int, str]:
    text = str(path)
    for index, keyword in enumerate(JIANYING_FONT_KEYWORDS):
        if keyword.lower() in text.lower():
            return index, path.name.lower()
    return len(JIANYING_FONT_KEYWORDS), path.name.lower()


@lru_cache(maxsize=1)
def _jianying_font_candidates() -> tuple[str, ...]:
    paths: list[Path] = []
    for root in _jianying_font_roots():
        if not root.exists() or not root.is_dir():
            continue
        try:
            iterator = root.rglob("*")
            for path in iterator:
                if not path.is_file():
                    continue
                if path.name.startswith("._") or "__MACOSX" in path.parts:
                    continue
                if path.suffix.lower() in ALLOWED_FONT_SUFFIXES:
                    paths.append(path)
        except OSError:
            continue
    paths.sort(key=_font_keyword_rank)
    return tuple(str(path) for path in paths[:24])


def _font_candidates(style: str, text: str) -> list[tuple[str, int]]:
    custom = (os.environ.get("IMAGE_TOOLS_WATERMARK_FONT_PATH", "") or "").strip()
    candidates: list[tuple[str, int]] = []
    if custom:
        candidates.append((custom, 0))

    if style == "rounded":
        candidates.extend((path, 0) for path in _jianying_font_candidates())
        candidates.extend([
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
            ("/System/Library/Fonts/STHeiti Medium.ttc", 1),
            ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
            ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 0),
            ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
        ])
    elif style == "bold":
        candidates.extend([
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
            ("/System/Library/Fonts/STHeiti Medium.ttc", 1),
            ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
            ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 0),
            ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
        ])

    if not _contains_cjk(text):
        candidates.extend([
            ("/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc", 1),
            ("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 0),
            ("/System/Library/Fonts/SFNSRounded.ttf", 0),
            ("/System/Library/Fonts/SFCompactRounded.ttf", 0),
        ])

    candidates.extend([
        ("/System/Library/Fonts/PingFang.ttc", 0),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
        ("/System/Library/Fonts/STHeiti Medium.ttc", 1),
        ("/System/Library/Fonts/STHeiti Light.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ])
    return candidates


def _font_from_bytes(data: bytes, size: int):
    for index in range(4):
        try:
            return ImageFont.truetype(BytesIO(data), size=size, index=index)
        except OSError:
            continue
    raise HTTPException(400, "字体文件无法解析，请换一个字体文件。")


def _font(size: int, *, style: str = "rounded", text: str = "", font_bytes: bytes | None = None):
    if font_bytes:
        return _font_from_bytes(font_bytes, size)
    for path, index in _font_candidates(style, text):
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def _save_png(image: Image.Image, prefix: str) -> dict:
    fname = f"{prefix}_{uuid.uuid4().hex[:12]}.png"
    fpath = deps.get_files_dir() / fname
    image.save(fpath, format="PNG")
    deps.notify_media_file_saved(fpath)
    return {"url": f"/api/files/{fname}", "filename": fname}


def _split_grid_images(image_bytes: bytes, req: SplitGridRequest) -> dict:
    with Image.open(BytesIO(image_bytes)) as src:
        image = ImageOps.exif_transpose(src).convert("RGB")
    try:
        width, height = image.size
        if width * height > MAX_WATERMARK_INPUT_PIXELS:
            raise HTTPException(413, "切图图片分辨率过大，请压缩到 1200 万像素以内再处理。")

        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        cropped = image.crop((left, top, left + side, top + side))
        try:
            cell_w = side // req.columns
            cell_h = side // req.rows
            results = []
            for row in range(req.rows):
                for column in range(req.columns):
                    right = side if column == req.columns - 1 else (column + 1) * cell_w
                    bottom = side if row == req.rows - 1 else (row + 1) * cell_h
                    tile = cropped.crop((column * cell_w, row * cell_h, right, bottom))
                    try:
                        saved = _save_png(tile, "grid_slice")
                    finally:
                        tile.close()
                    results.append({
                        "source_url": req.image_url,
                        "row": row + 1,
                        "column": column + 1,
                        **saved,
                    })
            return {"images": results, "rows": req.rows, "columns": req.columns}
        finally:
            cropped.close()
    finally:
        image.close()


async def split_grid_batch(req: SplitGridRequest) -> dict:
    data, _ = await _read_image_bytes(req.image_url)
    async with _local_image_slot():
        return await asyncio.to_thread(_split_grid_images, data, req)


def _watermark_positions(width: int, height: int, text_w: int, text_h: int, margin: int) -> dict[str, tuple[float, float]]:
    return {
        "top_left": (margin, margin),
        "top_right": (width - text_w - margin, margin),
        "bottom_left": (margin, height - text_h - margin),
        "bottom_right": (width - text_w - margin, height - text_h - margin),
        "center": ((width - text_w) / 2, (height - text_h) / 2),
    }


def _visual_noise_score(image: Image.Image, x: float, y: float, text_w: int, text_h: int, margin: int) -> float:
    width, height = image.size
    padding = max(4, margin // 3)
    left = max(0, int(x) - padding)
    top = max(0, int(y) - padding)
    right = min(width, int(x + text_w) + padding)
    bottom = min(height, int(y + text_h) + padding)
    if right <= left or bottom <= top:
        return float("inf")

    region = image.crop((left, top, right, bottom)).convert("L")
    max_side = 96
    if max(region.size) > max_side:
        scale = max_side / max(region.size)
        region = region.resize((max(1, int(region.width * scale)), max(1, int(region.height * scale))))
    if hasattr(region, "get_flattened_data"):
        pixels = list(region.get_flattened_data())
    else:
        pixels = list(region.getdata())
    if not pixels:
        return float("inf")

    dark_ratio = sum(1 for value in pixels if value < 110) / len(pixels)
    stat = ImageStat.Stat(region)
    contrast = (stat.stddev[0] if stat.stddev else 0) / 128
    edge_mean = ImageStat.Stat(region.filter(ImageFilter.FIND_EDGES)).mean[0] / 255
    return dark_ratio * 3 + contrast + edge_mean


def _resolve_watermark_position(image: Image.Image, req: WatermarkRequest, text_w: int, text_h: int, margin: int) -> tuple[str, float, float]:
    positions = _watermark_positions(image.width, image.height, text_w, text_h, margin)
    if req.position != "auto":
        x, y = positions.get(req.position, positions["bottom_right"])
        return req.position if req.position in positions else "bottom_right", x, y

    corner_order = ["top_left", "top_right", "bottom_left", "bottom_right"]
    selected = min(
        corner_order,
        key=lambda name: (_visual_noise_score(image, *positions[name], text_w, text_h, margin), corner_order.index(name)),
    )
    x, y = positions[selected]
    return selected, x, y


def _render_watermark(image_bytes: bytes, req: WatermarkRequest, font_bytes: bytes | None = None) -> tuple[Image.Image, str]:
    with Image.open(BytesIO(image_bytes)) as src:
        image = ImageOps.exif_transpose(src).convert("RGBA")
    width, height = image.size
    if width * height > MAX_WATERMARK_INPUT_PIXELS:
        image.close()
        raise HTTPException(413, "水印图片分辨率过大，请压缩到 1200 万像素以内再处理。")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "请填写水印文字。")
    base_side = min(width, height)
    font_size = int(req.font_size or max(14, round(base_side * 0.043)))
    margin = int(req.margin or max(6, round(base_side * 0.018)))
    default_stroke = max(2, round(font_size * 0.11))
    stroke_width = max(0, int(req.stroke_width if req.stroke_width is not None else default_stroke))
    font = _font(font_size, style=req.font_style, text=text, font_bytes=font_bytes)
    spacing = max(2, round(font_size * 0.12))

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, stroke_width=stroke_width, spacing=spacing)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    selected_position, x, y = _resolve_watermark_position(image, req, text_w, text_h, margin)
    draw.multiline_text(
        (max(0, x), max(0, y)),
        text,
        font=font,
        fill=_rgba(req.color, req.opacity),
        stroke_width=stroke_width,
        stroke_fill=_rgba(req.stroke_color, req.opacity),
        spacing=spacing,
    )
    output = Image.alpha_composite(image, layer)
    image.close()
    layer.close()
    return output, selected_position


def _grid_shape(count: int, req: WatermarkRequest) -> tuple[int, int, int, int, int, int]:
    columns = min(req.grid_columns, count)
    rows = math.ceil(count / columns)
    cell = req.grid_cell_size
    gap = req.grid_gap
    width = columns * cell + (columns - 1) * gap
    height = rows * cell + (rows - 1) * gap
    return columns, rows, cell, gap, width, height


def _new_grid_canvas(count: int, req: WatermarkRequest) -> tuple[Image.Image, int, int, int, int]:
    columns, rows, cell, gap, width, height = _grid_shape(count, req)
    canvas = Image.new("RGB", (width, height), _solid_rgb(req.grid_background))
    return canvas, columns, rows, cell, gap


def _fit_grid_tile(image: Image.Image, cell: int) -> Image.Image:
    rgb = image.convert("RGB")
    try:
        return ImageOps.fit(rgb, (cell, cell), method=Image.Resampling.LANCZOS)
    finally:
        rgb.close()


def _paste_grid_tile(canvas: Image.Image, tile: Image.Image, *, index: int, columns: int, cell: int, gap: int) -> None:
    row, column = divmod(index, columns)
    canvas.paste(tile, (column * (cell + gap), row * (cell + gap)))


def _save_grid_canvas(canvas: Image.Image, *, count: int, columns: int, rows: int) -> dict:
    saved = _save_png(canvas, "watermark_grid")
    return {**saved, "count": count, "columns": columns, "rows": rows}


async def apply_watermark_batch(req: WatermarkRequest) -> dict:
    font_bytes = None
    if (req.font_url or "").strip():
        font_bytes, _ = await _read_font_bytes(req.font_url)
    elif (req.font_id or "").strip():
        font_bytes = await _font_bytes_from_id(req.font_id)
        if font_bytes is None:
            raise HTTPException(400, "字体不存在或已失效，请重新选择字体。")

    async with _local_image_slot():
        wants_separate = req.output_mode in {"separate", "both"}
        wants_grid = req.output_mode in {"grid", "both"}
        grid_canvas = None
        grid_columns = grid_rows = grid_cell = grid_gap = 0
        if wants_grid:
            grid_canvas, grid_columns, grid_rows, grid_cell, grid_gap = await asyncio.to_thread(
                _new_grid_canvas,
                len(req.image_urls),
                req,
            )

        results = []
        try:
            for index, url in enumerate(req.image_urls):
                data, _ = await _read_image_bytes(url)
                image, selected_position = await asyncio.to_thread(_render_watermark, data, req, font_bytes)
                try:
                    if wants_separate:
                        item = await asyncio.to_thread(_save_png, image, "watermark")
                        results.append({"source_url": url, "position": selected_position, **item})
                    if grid_canvas is not None:
                        tile = await asyncio.to_thread(_fit_grid_tile, image, grid_cell)
                        try:
                            await asyncio.to_thread(
                                _paste_grid_tile,
                                grid_canvas,
                                tile,
                                index=index,
                                columns=grid_columns,
                                cell=grid_cell,
                                gap=grid_gap,
                            )
                        finally:
                            tile.close()
                finally:
                    image.close()

            grid = None
            if grid_canvas is not None:
                grid = await asyncio.to_thread(
                    _save_grid_canvas,
                    grid_canvas,
                    count=len(req.image_urls),
                    columns=grid_columns,
                    rows=grid_rows,
                )
        finally:
            if grid_canvas is not None:
                grid_canvas.close()

        return {"images": results, "grid": grid}


def _image_size(req) -> tuple[int, int]:
    if req.aspect_ratio in IMAGE_ASPECT_RATIO_SIZES:
        return IMAGE_ASPECT_RATIO_SIZES[req.aspect_ratio]
    width = req.width if 256 <= req.width <= 4096 else 1024
    height = req.height if 256 <= req.height <= 4096 else 1024
    return width, height


def _style_lock_prompt(req: GenerateNineRequest) -> str:
    if req.style_lock == "off":
        return "基础统一：保持画风大体一致，但允许轻微构图差异。"

    option_keys = req.style_lock_options or list(NINE_IMAGE_STYLE_LOCK_OPTIONS.keys())
    requirements = [
        NINE_IMAGE_STYLE_LOCK_OPTIONS[key]
        for key in option_keys
        if key in NINE_IMAGE_STYLE_LOCK_OPTIONS
    ]
    if not requirements:
        requirements = list(NINE_IMAGE_STYLE_LOCK_OPTIONS.values())

    prefix = "严格风格锁：" if req.style_lock == "strict" else "柔性风格锁："
    return prefix + "；".join(requirements)


def _style_contract_prompt(req: GenerateNineRequest, index: int) -> str:
    style = req.visual_style or (
        "朋友圈九图统一模板：白底或浅米底，2D 卡通，粗黑圆润描边，明亮柔和配色，"
        "固定俯视或正视角，主体居中且大小一致，留白比例一致"
    )
    variation = NINE_IMAGE_VARIATIONS[(index - 1) % len(NINE_IMAGE_VARIATIONS)]
    fixed_items = [
        "固定背景：所有候选图必须保持同一种白底或浅米底，不允许改变背景，不允许换成蓝天、森林、厨房、桌面、渐变或深色背景",
        "固定色调：所有候选图必须保持同一套明亮柔和配色，不允许忽冷忽暖、忽深忽浅、饱和度大幅变化",
        "固定线条：所有候选图必须保持同样粗细的黑色圆润描边、同样阴影方式和同样卡通精度",
        "固定视角：所有候选图必须保持同一俯视或正视角、同一镜头距离，不允许切换透视或裁切方式",
        "固定主体比例：主体占画面比例、居中方式、留白、元素密度必须一致，不允许忽大忽小",
    ]
    if req.style_lock != "strict":
        fixed_items = fixed_items[:3] + ["柔性一致：允许轻微构图变化，但不能破坏整套九图模板感"]

    anchor = (
        "参考图贴近：已提供风格样板图，必须优先复刻样板图的背景、色调、线条粗细、视角、主体比例和画面密度。\n"
        if req.style_anchor_url else ""
    )
    if req.variation_policy == "creative" and req.style_lock != "strict":
        variation_rule = "变化规则：允许轻微创意变化，但背景、色调、线条和主体比例仍要稳定。"
    else:
        variation_rule = "变化规则：只允许替换主体元素或同主题道具组合，不允许改变画面模板。"

    return (
        "你是游戏素材套图设计师。生成 1 张正方形候选素材，不要输出解释文字。\n"
        f"画面主体：{req.theme}\n"
        f"固定风格：{style}\n"
        f"构图锁定：{variation}\n"
        f"{anchor}"
        f"{_style_lock_prompt(req)}\n"
        + "\n".join(fixed_items)
        + "\n"
        f"{variation_rule}\n"
        "禁止项：禁止出现任何文字、标题、水印、logo、边框、拼贴分割线、对比图、UI、手写标注；"
        "禁止背景漂移、色调漂移、镜头变化、线条粗细变化、主体比例忽大忽小；"
        f"这是候选素材批次中的第 {index}/{req.count or req.batch_size} 张。"
    )


def _nine_image_prompt(req: GenerateNineRequest, index: int) -> str:
    return _style_contract_prompt(req, index)


async def _generate_reference_context(req: GenerateNineRequest) -> dict:
    if not req.style_anchor_url:
        return {"jimeng_urls": [], "gemini_bytes": []}
    if req.provider == "gemini_image":
        data = await _read_gemini_reference_bytes(req.style_anchor_url)
        return {"jimeng_urls": [], "gemini_bytes": [data]}
    return {
        "jimeng_urls": [await deps.resolve_image_for_external(req.style_anchor_url)],
        "gemini_bytes": [],
    }


async def _generate_nine_image(req: GenerateNineRequest, prompt: str, index: int, reference_context: dict | None = None) -> dict:
    width, height = _image_size(req)
    reference_context = reference_context or {}
    if req.provider == "gemini_image":
        svc = _provider_registry.gemini()
        if not svc:
            raise HTTPException(400, "Gemini 图片还没有配置 API Key，请先到设置里配置，或切换到即梦 / Seedream。")

        async def _call_gemini(reference_images: list[bytes]):
            return await run_provider_call(
                "gemini_image",
                "image_tools_generate_nine",
                lambda: svc.generate_image(
                    prompt=prompt,
                    model=req.model,
                    width=width,
                    height=height,
                    reference_images=reference_images,
                ),
            )

        gemini_refs = reference_context.get("gemini_bytes") or []
        try:
            result = await _call_gemini(gemini_refs)
        except Exception:
            if not gemini_refs:
                raise
            logger.info("Gemini style anchor failed for image_tools_generate_nine; retrying without reference image.")
            result = await _call_gemini([])
        cached = await asyncio.to_thread(deps.save_gemini_image_result, result)
    else:
        svc = _provider_registry.jimeng()
        if not svc:
            raise HTTPException(400, "即梦 / Seedream 还没有配置 API Key，请先到设置里配置，或切换到 Gemini 图片。")

        async def _call_jimeng(reference_urls: list[str]):
            return await run_provider_call(
                "jimeng",
                "image_tools_generate_nine",
                lambda: svc.generate_image(
                    prompt=prompt,
                    model=req.model,
                    size=f"{width}x{height}",
                    reference_urls=reference_urls,
                    edit_mode=False,
                    image_quality="2K",
                    prompt_optimize_mode="standard",
                    output_format="png",
                ),
            )

        jimeng_refs = reference_context.get("jimeng_urls") or []
        try:
            result = await _call_jimeng(jimeng_refs)
        except Exception:
            if not jimeng_refs:
                raise
            logger.info("Jimeng style anchor failed for image_tools_generate_nine; retrying without reference image.")
            result = await _call_jimeng([])
        cached = await deps.cache_remote_file_result(result)

    images = cached.get("images") or []
    url = (images[0].get("url") if images else cached.get("image_url")) or ""
    if not url:
        raise Exception("模型没有返回图片")
    filename = url.rsplit("/", 1)[-1] if url.startswith("/api/files/") else ""
    return {"url": url, "filename": filename, "prompt": prompt, "index": index, "source": "ai_generate"}


async def generate_nine_images(req: GenerateNineRequest) -> dict:
    if req.provider == "gemini_image" and not _provider_registry.gemini():
        raise HTTPException(400, "Gemini 图片还没有配置 API Key，请先到设置里配置，或切换到即梦 / Seedream。")
    if req.provider != "gemini_image" and not _provider_registry.jimeng():
        raise HTTPException(400, "即梦 / Seedream 还没有配置 API Key，请先到设置里配置，或切换到 Gemini 图片。")

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    requested_count = req.count or req.batch_size
    try:
        reference_context = await _generate_reference_context(req)
    except Exception as exc:
        logger.warning("Style anchor preparation failed for generate_nine batch=%s: %s", batch_id, exc)
        reference_context = {"jimeng_urls": [], "gemini_bytes": []}

    semaphore = asyncio.Semaphore(IMAGE_TOOLS_AI_GENERATION_CONCURRENCY)

    async def _worker(index: int):
        prompt = _nine_image_prompt(req, index)
        async with semaphore:
            try:
                item = await _generate_nine_image(req, prompt, index, reference_context)
                return {"ok": True, "batch_id": batch_id, **item}
            except Exception as exc:
                logger.warning("Generate nine image failed index=%s: %s", index, exc)
                return {"ok": False, "batch_id": batch_id, "index": index, "prompt": prompt, "error": str(exc)[:500]}

    results = await asyncio.gather(*[_worker(index) for index in range(1, requested_count + 1)])
    images = [
        {key: value for key, value in item.items() if key != "ok"}
        for item in results
        if item.get("ok")
    ]
    failures = [item for item in results if not item.get("ok")]
    if not images:
        detail = failures[0]["error"] if failures else "未知错误"
        raise HTTPException(502, f"九图生成失败：{detail}")
    return {
        "batch_id": batch_id,
        "images": images,
        "failures": failures,
        "count": len(images),
        "requested_count": requested_count,
        "batch_size": requested_count,
        "provider": req.provider,
        "model": req.model,
        "style_anchor_url": req.style_anchor_url,
        "style_lock": req.style_lock,
        "variation_policy": req.variation_policy,
    }


def _role_image_prompt(req: GenerateRolesRequest, role_name: str, index: int) -> str:
    style = req.visual_style or (
        "朋友圈九图统一模板：白底或浅米底，2D 卡通，粗黑圆润描边，明亮柔和配色，"
        "固定俯视或正视角，主体居中且大小一致，留白比例一致"
    )
    anchor = (
        "参考图贴近：已提供风格样板图，必须优先复刻样板图的背景、色调、线条粗细、视角、主体比例和画面密度。\n"
        if req.style_anchor_url else ""
    )
    variation_rule = (
        "变化规则：本张只生成指定角色/物品，不要混入其他角色；只允许替换主体，不允许改变画面模板。"
        if req.variation_policy == "subject_only"
        else "变化规则：可以加入少量同主题小道具，但指定角色/物品必须是唯一主角，统一模板不能漂移。"
    )
    return (
        "你是游戏素材套图设计师。生成 1 张正方形角色/物品素材，不要输出解释文字。\n"
        f"套图主题：{req.theme}\n"
        f"本张主体：{role_name}\n"
        f"固定风格：{style}\n"
        f"{anchor}"
        f"{_style_lock_prompt(req)}\n"
        "固定背景：所有角色图必须保持同一种白底或浅米底，不允许换成场景背景、深色背景或渐变背景。\n"
        "固定色调：所有角色图必须保持同一套明亮柔和配色，饱和度、明暗和冷暖关系稳定。\n"
        "固定线条：所有角色图必须保持同样粗细的黑色圆润描边、同样阴影方式和同样卡通精度。\n"
        "固定视角：所有角色图必须保持同一俯视或正视角、同一镜头距离，不允许切换透视。\n"
        "固定主体比例：主体占画面比例、居中方式、留白和元素密度必须一致。\n"
        f"{variation_rule}\n"
        "禁止项：禁止出现任何文字、标题、水印、logo、边框、拼贴分割线、对比图、UI、手写标注；"
        "禁止背景漂移、色调漂移、镜头变化、线条粗细变化、主体比例忽大忽小；"
        f"这是同风格角色九图中的第 {index}/9 张。"
    )


async def generate_role_images(req: GenerateRolesRequest) -> dict:
    if req.provider == "gemini_image" and not _provider_registry.gemini():
        raise HTTPException(400, "Gemini 图片还没有配置 API Key，请先到设置里配置，或切换到即梦 / Seedream。")
    if req.provider != "gemini_image" and not _provider_registry.jimeng():
        raise HTTPException(400, "即梦 / Seedream 还没有配置 API Key，请先到设置里配置，或切换到 Gemini 图片。")

    batch_id = f"roles_{uuid.uuid4().hex[:12]}"
    try:
        reference_context = await _generate_reference_context(req)
    except Exception as exc:
        logger.warning("Style anchor preparation failed for generate_roles batch=%s: %s", batch_id, exc)
        reference_context = {"jimeng_urls": [], "gemini_bytes": []}

    semaphore = asyncio.Semaphore(IMAGE_TOOLS_AI_GENERATION_CONCURRENCY)

    async def _worker(index: int, role_name: str):
        prompt = _role_image_prompt(req, role_name, index)
        async with semaphore:
            try:
                item = await _generate_nine_image(req, prompt, index, reference_context)
                return {"ok": True, "batch_id": batch_id, "role": role_name, **item}
            except Exception as exc:
                logger.warning("Generate role image failed role=%s index=%s: %s", role_name, index, exc)
                return {
                    "ok": False,
                    "batch_id": batch_id,
                    "index": index,
                    "role": role_name,
                    "prompt": prompt,
                    "error": str(exc)[:500],
                }

    results = await asyncio.gather(*[
        _worker(index, role_name)
        for index, role_name in enumerate(req.roles, start=1)
    ])
    images = [
        {key: value for key, value in item.items() if key != "ok"}
        for item in results
        if item.get("ok")
    ]
    failures = [item for item in results if not item.get("ok")]
    if not images:
        detail = failures[0]["error"] if failures else "未知错误"
        raise HTTPException(502, f"同风格角色九图生成失败：{detail}")
    return {
        "batch_id": batch_id,
        "images": images,
        "failures": failures,
        "count": len(images),
        "requested_count": len(req.roles),
        "batch_size": len(req.roles),
        "roles": req.roles,
        "provider": req.provider,
        "model": req.model,
        "style_anchor_url": req.style_anchor_url,
        "style_lock": req.style_lock,
        "variation_policy": req.variation_policy,
    }


def _derive_prompt(req: DeriveRequest) -> str:
    mode = req.mode if req.mode in DERIVE_MODE_PROMPTS else "fine_tune"
    instruction = (req.instruction or "").strip()
    return (
        f"{DERIVE_MODE_PROMPTS[mode]}\n"
        "输出必须是一张完整图片，不要添加解释文字、对比图、边框或水印。\n"
        f"用户要求：{instruction or '根据该模式做一个稳定、可投放的图片衍生版本。'}"
    )


async def _derive_with_jimeng(req: DeriveRequest, prompt: str) -> dict:
    svc = _provider_registry.jimeng()
    if not svc:
        raise HTTPException(400, "即梦 / Seedream 还没有配置 API Key，请先到设置里配置，或切换到 Gemini 图片。")
    ref_urls = [await deps.resolve_image_for_external(url) for url in req.reference_urls]
    width, height = _image_size(req)
    async def _call_jimeng(model: str):
        return await run_provider_call(
            "jimeng",
            "image_tools_derive",
            lambda: svc.generate_image(
                prompt=prompt,
                model=model,
                size=f"{width}x{height}",
                reference_urls=ref_urls,
                edit_mode=req.mode != "creative_fusion",
            ),
        )

    try:
        result = await _call_jimeng(req.model)
    except Exception:
        if req.model != "seedream-5.0":
            raise
        logger.info("Seedream 5.0 failed for image_tools_derive; retrying with seedream-4.5.")
        result = await _call_jimeng("seedream-4.5")
    cached = await deps.cache_remote_file_result(result)
    if req.model == "seedream-5.0":
        cached["fallback_model"] = "seedream-4.5"
    return cached


async def _derive_with_gemini(req: DeriveRequest, prompt: str) -> dict:
    svc = _provider_registry.gemini()
    if not svc:
        raise HTTPException(400, "Gemini 图片还没有配置 API Key，请先到设置里配置，或切换到即梦 / Seedream。")
    ref_bytes = []
    for url in req.reference_urls:
        ref_bytes.append(await _read_gemini_reference_bytes(url))
    width, height = _image_size(req)
    result = await run_provider_call(
        "gemini_image",
        "image_tools_derive",
        lambda: svc.generate_image(
            prompt=prompt,
            model=req.model,
            width=width,
            height=height,
            reference_images=ref_bytes,
        ),
    )
    return deps.save_gemini_image_result(result)


async def derive_image_batch(req: DeriveRequest) -> dict:
    prompt = _derive_prompt(req)
    try:
        if req.provider == "gemini_image":
            result = await _derive_with_gemini(req, prompt)
        elif req.provider == "jimeng":
            result = await _derive_with_jimeng(req, prompt)
        else:
            raise HTTPException(400, f"不支持的图片服务商：{req.provider}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, _friendly_image_tool_error(exc, feature_name="图片衍生")) from exc
    return {"prompt": prompt, **result}


def _friendly_image_tool_error(exc: Exception, *, feature_name: str) -> str:
    detail = str(getattr(exc, "detail", exc) or "").strip()
    lower = detail.lower()
    if "api key" in lower or "key is required" in lower or "未配置" in detail:
        return f"{feature_name}失败：服务商 API Key 未配置，请先到设置里配置。"
    if "reference" in lower or "参考图" in detail:
        return f"{feature_name}失败：当前模型不支持参考图，或参考图过大/无法访问。{detail}"
    if "oversize" in lower or "too large" in lower or "过大" in detail:
        return f"{feature_name}失败：图片过大，请压缩后重试。{detail}"
    return f"{feature_name}失败：{detail or 'provider 返回失败'}"


def _string_list(value, *, max_items: int = 8) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:max_items]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[、,，;\n]+", value) if item.strip()][:max_items]
    return []


def _style_summary_from_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= 36:
        return cleaned
    return cleaned[:36].rstrip("，,；;。 ") + "..."


def _reverse_generation_prompt_from_parts(
    *,
    theme: str,
    visual_style: str,
    negative_prompt: str,
    description: str = "",
    subject: str = "",
    scene: str = "",
) -> str:
    parts = []
    subject_text = theme or subject
    if subject_text:
        parts.append(f"主体：{subject_text}")
    if scene:
        parts.append(f"构图/场景：{scene}")
    elif description:
        parts.append(f"构图/场景：{description}")
    if visual_style:
        parts.append(f"画风、线条、色彩、背景、材质：{visual_style}")
    parts.append("成图要求：完整单张图片，主体清晰，商业游戏广告素材质感，适合继续衍生为同风格九图。")
    if negative_prompt:
        parts.append(f"禁用项：{negative_prompt}")
    return "；".join(parts)


async def _reverse_one(url: str, model: str) -> dict:
    data, ext = await _read_image_bytes(url)
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".png": "image/png",
    }.get(ext, "image/png")
    prompt = (
        "你是爆款游戏广告图片分析师和 AI 生图提示词设计师。请分析这张图片，并只返回一个 JSON object，"
        "不要输出 Markdown、解释文字或代码块。格式："
        "{\"theme\":\"画面内容/主体题材，只写主体不要写画风\","
        "\"visual_style\":\"可复用画风摘要，写构图、画风、线条、色彩、背景、材质约束\","
        "\"style_summary\":\"20 字以内的短摘要\","
        "\"prompt\":\"完整中文生图提示词，必须包含主体、构图、画风、线条、色彩、背景、材质、禁用项，能直接用于生成同风格图片\","
        "\"negative_prompt\":\"生成时需要避免的内容\","
        "\"description\":\"画面描述\",\"style\":\"画风\",\"subject\":\"主体\","
        "\"scene\":\"场景\",\"selling_points\":[\"爆点元素\"]}。"
        "要求：prompt 要比 visual_style 更完整，适合直接回填到生图提示词；"
        "negative_prompt 必须包含无文字、无水印、无 logo、无 UI、无边框、不要风格漂移。"
    )

    if deps.is_openai_model(model):
        svc = _provider_registry.openai()
        if not svc:
            raise HTTPException(400, "OpenAI API Key 未配置，请先到设置里配置。")
        text = await run_provider_call(
            "openai",
            "image_tools_reverse_prompt",
            lambda: svc.chat_vision(text_prompt=prompt, image_data_list=[(data, mime)], model=model),
        )
    else:
        svc = _provider_registry.gemini()
        if not svc:
            raise HTTPException(400, "Gemini API Key 未配置，请先到设置里配置。")
        from google.genai import types
        response = await run_provider_call(
            "gemini",
            "image_tools_reverse_prompt",
            lambda: svc.generate_content(
                model=model,
                contents=types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=data, mime_type=mime),
                        types.Part.from_text(text=prompt),
                    ],
                ),
            ),
        )
        text = response.text or ""

    parsed = deps.extract_json(text)
    if not isinstance(parsed, dict):
        raise Exception("模型没有返回可解析的 JSON")
    theme = str(parsed.get("theme") or parsed.get("subject") or "").strip()
    description = str(parsed.get("description") or "").strip()
    style = str(parsed.get("style") or "").strip()
    subject = str(parsed.get("subject") or "").strip()
    scene = str(parsed.get("scene") or "").strip()
    visual_style = str(parsed.get("visual_style") or style or "").strip()
    negative_prompt = str(
        parsed.get("negative_prompt")
        or "无文字、无水印、无 logo、无 UI、无边框、不要风格漂移"
    ).strip()
    full_prompt = str(parsed.get("prompt") or parsed.get("full_prompt") or "").strip()
    if not full_prompt:
        full_prompt = _reverse_generation_prompt_from_parts(
            theme=theme,
            visual_style=visual_style,
            negative_prompt=negative_prompt,
            description=description,
            subject=subject,
            scene=scene,
        )
    if not visual_style:
        visual_style = full_prompt
    style_summary = str(parsed.get("style_summary") or "").strip() or _style_summary_from_text(visual_style)
    return {
        "image_url": url,
        "theme": theme,
        "visual_style": visual_style,
        "style_summary": style_summary,
        "negative_prompt": negative_prompt,
        "description": description,
        "style": style,
        "subject": subject,
        "scene": scene,
        "selling_points": _string_list(parsed.get("selling_points")),
        "prompt": full_prompt,
    }


async def reverse_prompt_batch(req: ReversePromptsRequest) -> dict:
    results = []
    for url in req.image_urls:
        try:
            item = await _reverse_one(url, req.model)
            results.append({"ok": True, **item})
        except Exception as exc:
            logger.warning("Reverse image prompt failed for %s: %s", url, exc)
            results.append({"ok": False, "image_url": url, "error": str(exc)[:500]})
    return {"results": results}


async def reverse_style_prompt(req: ReverseStylePromptRequest) -> dict:
    image_url = _normalize_urls([req.image_url], max_count=1, label="参考图")[0]
    item = await _reverse_one(image_url, req.model or "gemini-2.5-flash")
    theme = item.get("theme") or item.get("subject") or item.get("description") or ""
    style_prompt = item.get("visual_style") or "，".join(
        part for part in [item.get("style"), item.get("scene")] if part
    )
    full_prompt = item.get("prompt") or _reverse_generation_prompt_from_parts(
        theme=theme,
        visual_style=style_prompt,
        negative_prompt=item.get("negative_prompt", ""),
        description=item.get("description", ""),
        subject=item.get("subject", ""),
        scene=item.get("scene", ""),
    )
    return {
        "image_url": image_url,
        "model": req.model,
        "theme": theme,
        "visual_style": style_prompt,
        "style_summary": item.get("style_summary", ""),
        "negative_prompt": item.get("negative_prompt", ""),
        "description": item.get("description", ""),
        "style": item.get("style", ""),
        "subject": item.get("subject", ""),
        "scene": item.get("scene", ""),
        "selling_points": item.get("selling_points", []),
        "prompt": full_prompt,
    }


async def _chat_prompt_model(model: str, prompt: str, operation: str) -> str:
    selected_model = model or "gemini-2.5-flash"
    if deps.is_openai_model(selected_model):
        svc = _provider_registry.openai()
        if not svc:
            raise HTTPException(400, "OpenAI API Key 未配置，请先到设置里配置。")
        return await run_provider_call(
            "openai",
            operation,
            lambda: svc.chat(prompt, model=selected_model),
        )

    svc = _provider_registry.gemini()
    if not svc:
        raise HTTPException(400, "Gemini API Key 未配置，请先到设置里配置。")
    result = await run_provider_call(
        "gemini",
        operation,
        lambda: svc.chat(prompt, f"image_prompt_{uuid.uuid4().hex[:8]}", selected_model),
    )
    return result.get("response", "") if isinstance(result, dict) else str(result or "")


async def polish_generation_prompt(req: PromptPolishRequest) -> dict:
    theme = (req.theme or "").strip()
    visual_style = (req.visual_style or "").strip()
    if not theme and not visual_style:
        raise HTTPException(400, "请先填写画面内容或画风提示词。")

    prompt = (
        "你是游戏广告图片提示词设计师，请把用户输入整理成可直接用于 AI 生图的九宫格素材提示词。"
        "只返回一个 JSON object，不要返回数组，不要 Markdown，格式："
        "{\"theme\":\"更清晰的画面内容\",\"visual_style\":\"完整画风提示词\"}。\n"
        "要求：适合微信朋友圈九宫格；同一系列；明确主体、画风、构图、线条、色彩、背景；"
        "不要要求模型生成文字、水印、logo、边框或拼贴分割线。\n"
        f"画面内容：{theme}\n"
        f"当前画风提示词：{visual_style}"
    )
    try:
        text = await _chat_prompt_model(req.model, prompt, "image_tools_prompt_polish")
    except Exception as exc:
        logger.warning("Prompt polish model request failed for %s: %s", req.model, exc)
        selected = (req.model or "").strip() or "当前模型"
        raise HTTPException(
            502,
            f"生成提示词失败：当前选择的模型 {selected} 暂时不可用。\n"
            f"具体原因：{str(exc)[:300]}\n"
            "请稍后重试，或切换到其他提示词模型后再试。",
        ) from exc
    parsed = _extract_prompt_polish_payload(text)
    if not isinstance(parsed, dict):
        parsed = {}
    polished_theme = str(parsed.get("theme") or theme).strip()
    polished_style = str(parsed.get("visual_style") or parsed.get("prompt") or text or visual_style).strip()
    return {
        "theme": polished_theme,
        "visual_style": polished_style,
        "prompt": polished_style,
        "model": req.model,
    }


async def suggest_role_items(req: RoleSuggestionRequest) -> dict:
    topic = (req.topic or "").strip()
    theme = (req.theme or "").strip()
    subject_type = (req.subject_type or "object").strip().lower()
    if subject_type not in {"character", "object"}:
        subject_type = "object"
    subject_label = "角色" if subject_type == "character" else "物品"
    subject_rule = (
        "必须推荐拟人化或可作为游戏角色的主体，例如不同职业、性格、造型或生物角色；不要推荐纯道具、食材、装饰物。"
        if subject_type == "character"
        else "必须推荐具体可画的物品、道具、食材、装备或素材元素；不要推荐人物职业、真人姓名或抽象性格。"
    )
    if not topic and not theme:
        raise HTTPException(400, "请先输入一个主题，例如：甜品、恐龙、武器。")
    source_theme = topic or theme
    unified_theme = theme or source_theme

    count = max(1, min(9, int(req.count or 9)))
    prompt = (
        "你是游戏广告素材策划，请根据用户主题推荐适合做“同风格角色九图”的主体名称。"
        "只返回 JSON object，不要 Markdown，不要解释，格式："
        "{\"items\":[\"主体1\",\"主体2\",\"主体3\"]}。\n"
        "要求：\n"
        f"- 当前选择类型：{subject_label}。\n"
        f"- {subject_rule}\n"
        f"- 必须返回 {count} 个中文{subject_label}名称。\n"
        "- 每个名称 2 到 8 个中文字符为主，适合作为单张图的主体。\n"
        "- 主体之间要有明显差异，避免“1号/2号/3号”这种占位命名。\n"
        "- 不要包含品牌名、真人姓名、血腥暴力、色情或违法内容。\n"
        "- 如果主题很宽泛，要给出具体可画的物品/角色。\n"
        "- 必须同时参考“九图统一主题”和“同风格主体主题”：统一主题决定系列场景/玩法/大方向，同风格主体主题决定这 9 个具体主体。\n"
        "- 不要混入示例按钮、历史缓存或未在下面两项中出现的主题。\n"
        f"九图统一主题：{unified_theme}\n"
        f"同风格主体主题：{source_theme}"
    )
    try:
        text = await _chat_prompt_model(req.model, prompt, "image_tools_role_suggest")
    except Exception as exc:
        logger.warning("Role suggestion model request failed for %s: %s", req.model, exc)
        selected = (req.model or "").strip() or "当前模型"
        raise HTTPException(
            502,
            f"推荐主体失败：当前选择的模型 {selected} 暂时不可用。\n"
            f"具体原因：{str(exc)[:300]}\n"
            "请稍后重试，或切换到其他提示词模型后再试。",
        ) from exc

    parsed = deps.extract_json(text)
    if not isinstance(parsed, dict):
        parsed = _extract_prompt_polish_payload(text)
    raw_items = parsed.get("items") if isinstance(parsed, dict) else []
    if not isinstance(raw_items, list):
        raw_items = []

    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        item = re.sub(r"^\s*\d+[\.、)\-]\s*", "", str(raw or "").strip())
        item = re.sub(r"\s+", "", item)
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item[:16])
        if len(items) >= count:
            break

    if len(items) < count:
        raise HTTPException(502, "模型返回的主体推荐不完整，请重新生成一次。")

    return {
        "items": items,
        "model": req.model,
        "topic": source_theme,
        "theme": unified_theme,
        "subject_type": subject_type,
    }


def _extract_prompt_polish_payload(text: str) -> dict:
    parsed = deps.extract_json(text)
    if isinstance(parsed, dict):
        return parsed

    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text or "").strip()
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]") + 1
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return payload if isinstance(payload, dict) else {}


def recover_interrupted_image_tool_tasks() -> int:
    db.init_db()
    return db.mark_stale_image_tool_tasks_interrupted()


def _image_tool_task_response(task: dict | None) -> dict:
    if not task:
        raise HTTPException(404, "图片工具任务不存在。")
    return {
        "task_id": task["id"],
        "id": task["id"],
        "type": task.get("type", ""),
        "status": task.get("status", ""),
        "provider": task.get("provider", ""),
        "model": task.get("model", ""),
        "input_payload": task.get("input_payload") or {},
        "result_payload": task.get("result_payload") or {},
        "error": task.get("error", ""),
        "progress": task.get("progress", 0),
        "created_at": task.get("created_at", ""),
        "updated_at": task.get("updated_at", ""),
    }


def _prepare_image_tool_task_payload(req: ImageToolTaskRequest) -> tuple[str, dict, str, str]:
    task_type = (req.type or "").strip()
    payload = req.payload or {}
    if task_type == "generate_nine":
        prepared = prepare_generate_nine_request(GenerateNineRequest(**payload))
        return task_type, prepared.model_dump(), prepared.provider, prepared.model
    if task_type == "generate_roles":
        prepared = prepare_generate_roles_request(GenerateRolesRequest(**payload))
        return task_type, prepared.model_dump(), prepared.provider, prepared.model
    if task_type == "derive":
        prepared = prepare_derive_request(DeriveRequest(**payload))
        return task_type, prepared.model_dump(), prepared.provider, prepared.model
    if task_type == "reverse_prompts":
        prepared = prepare_reverse_request(ReversePromptsRequest(**payload))
        provider = "openai" if deps.is_openai_model(prepared.model) else "gemini"
        return task_type, prepared.model_dump(), provider, prepared.model
    if task_type == "watermark":
        prepared = prepare_watermark_request(WatermarkRequest(**payload))
        return task_type, prepared.model_dump(), "local", "watermark"
    raise HTTPException(400, f"不支持的图片工具任务类型：{task_type}")


def _start_image_tool_task_runner(task_id: str) -> None:
    existing = _image_tool_task_runners.get(task_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(_run_image_tool_task(task_id))
    _image_tool_task_runners[task_id] = task

    def _cleanup(_task):
        if _image_tool_task_runners.get(task_id) is _task:
            _image_tool_task_runners.pop(task_id, None)

    task.add_done_callback(_cleanup)


async def create_image_tool_task(req: ImageToolTaskRequest) -> dict:
    task_type, payload, provider, model = _prepare_image_tool_task_payload(req)
    await asyncio.to_thread(db.init_db)
    task = await asyncio.to_thread(
        db.create_image_tool_task,
        type_=task_type,
        provider=provider,
        model=model,
        input_payload=payload,
    )
    _start_image_tool_task_runner(task["id"])
    return _image_tool_task_response(task)


async def list_image_tool_tasks(limit: int = 50, status: str = "") -> dict:
    safe_limit = min(100, max(1, int(limit or 50)))
    await asyncio.to_thread(db.init_db)
    tasks = await asyncio.to_thread(db.list_image_tool_tasks, status, safe_limit)
    return {"tasks": [_image_tool_task_response(task) for task in tasks]}


async def get_image_tool_task(task_id: str) -> dict:
    await asyncio.to_thread(db.init_db)
    task = await asyncio.to_thread(db.get_image_tool_task, task_id)
    return _image_tool_task_response(task)


async def cancel_image_tool_task(task_id: str) -> dict:
    await asyncio.to_thread(db.init_db)
    task = await asyncio.to_thread(db.get_image_tool_task, task_id)
    if not task:
        raise HTTPException(404, "图片工具任务不存在。")
    if task.get("status") in {"completed", "failed", "canceled"}:
        return _image_tool_task_response(task)
    await asyncio.to_thread(
        db.update_image_tool_task,
        task_id,
        status="canceled",
        error="已取消。本地停止等待；如果请求已发送给 provider，外部平台可能仍会继续处理。",
        progress=0,
    )
    runner = _image_tool_task_runners.get(task_id)
    if runner and not runner.done():
        runner.cancel()
    return await get_image_tool_task(task_id)


def _delete_local_task_output_files(task: dict) -> int:
    if task.get("type") not in {"generate_nine", "generate_roles", "derive", "watermark"}:
        return 0

    payload = task.get("result_payload") or {}
    urls = [image.get("url", "") for image in payload.get("images") or [] if isinstance(image, dict)]
    if payload.get("image_url"):
        urls.append(payload["image_url"])
    grid = payload.get("grid")
    if isinstance(grid, dict) and grid.get("url"):
        urls.append(grid["url"])

    files_dir = deps.get_files_dir().resolve()
    deleted = 0
    for url in urls:
        path = urlparse(str(url)).path
        if not path.startswith("/api/files/"):
            continue
        target = (files_dir / Path(path).name).resolve()
        if target.parent != files_dir:
            continue
        try:
            if target.exists():
                target.unlink()
                deleted += 1
        except OSError:
            logger.warning("Failed to delete image tool task output file: %s", target)
    return deleted


async def delete_image_tool_task(task_id: str) -> dict:
    await asyncio.to_thread(db.init_db)
    task = await asyncio.to_thread(db.get_image_tool_task, task_id)
    if not task:
        raise HTTPException(404, "图片工具任务不存在。")
    runner = _image_tool_task_runners.get(task_id)
    if runner and not runner.done():
        runner.cancel()
        _image_tool_task_runners.pop(task_id, None)
    await asyncio.to_thread(_delete_local_task_output_files, task)
    deleted = await asyncio.to_thread(db.delete_image_tool_task, task_id)
    if not deleted:
        raise HTTPException(404, "图片工具任务不存在。")
    return {"task_id": task_id, "deleted": True}


async def _execute_image_tool_task(task_type: str, payload: dict) -> dict:
    if task_type == "generate_nine":
        return await generate_nine_images(GenerateNineRequest(**payload))
    if task_type == "generate_roles":
        return await generate_role_images(GenerateRolesRequest(**payload))
    if task_type == "derive":
        return await derive_image_batch(DeriveRequest(**payload))
    if task_type == "reverse_prompts":
        return await reverse_prompt_batch(ReversePromptsRequest(**payload))
    if task_type == "watermark":
        return await apply_watermark_batch(WatermarkRequest(**payload))
    raise HTTPException(400, f"不支持的图片工具任务类型：{task_type}")


async def _run_image_tool_task(task_id: str) -> None:
    task = await asyncio.to_thread(db.get_image_tool_task, task_id)
    if not task or task.get("status") == "canceled":
        return
    await asyncio.to_thread(db.update_image_tool_task, task_id, status="running", progress=0.05)
    try:
        result = await _execute_image_tool_task(task.get("type", ""), task.get("input_payload") or {})
        latest = await asyncio.to_thread(db.get_image_tool_task, task_id)
        if latest and latest.get("status") == "canceled":
            return
        await asyncio.to_thread(
            db.update_image_tool_task,
            task_id,
            status="completed",
            result_payload=result,
            error="",
            progress=1,
        )
    except asyncio.CancelledError:
        latest = await asyncio.to_thread(db.get_image_tool_task, task_id)
        if latest and latest.get("status") != "canceled":
            await asyncio.to_thread(
                db.update_image_tool_task,
                task_id,
                status="canceled",
                error="已取消。本地停止等待；如果请求已发送给 provider，外部平台可能仍会继续处理。",
                progress=0,
            )
        raise
    except Exception as exc:
        logger.warning("Image tool task failed task_id=%s: %s", task_id, exc)
        await asyncio.to_thread(
            db.update_image_tool_task,
            task_id,
            status="failed",
            result_payload={},
            error=_friendly_image_tool_error(exc, feature_name="图片工具任务"),
            progress=1,
        )
