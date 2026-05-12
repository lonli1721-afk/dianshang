"""游戏视频素材工具 — 共享依赖"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import uuid
import asyncio
import hmac
import hashlib
import base64
import io
import time
from pathlib import Path
from typing import Optional
from contextvars import ContextVar
from urllib.parse import urlencode, urlparse

import aiofiles
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx

import database as db
import auth
from settings import SettingsManager

logger = logging.getLogger("game-video-tool")

# ── 共享状态 ────────────────────────────────────────

settings_manager = SettingsManager()

DATA_DIR = Path(os.environ.get("USER_DATA_DIR", Path.home() / ".game-video-tool"))
FILES_DIR: Path = DATA_DIR / "files"
FILES_DIR.mkdir(parents=True, exist_ok=True)
_current_files_dir: ContextVar[Path] = ContextVar("current_files_dir", default=FILES_DIR)
_known_files_dirs: set[Path] = {FILES_DIR}
_files_dir_lock = threading.RLock()

# 服务实例 — 由 main.py 初始化
ai_service = None
openai_service = None
jimeng_service = None
vidu_service = None

# 游戏专用服务实例
game_ai_service = None
game_jimeng_service = None
game_vidu_service = None

_video_tasks: dict[str, dict] = {}

# 云端同步
cloud_sync = None

# Shared HTTP client (connection pooling, avoids repeated SSL context creation)
http_client: Optional[httpx.AsyncClient] = None
FILE_IO_CHUNK_SIZE = 1024 * 1024
MAX_INLINE_IMAGE_BYTES = int(os.environ.get("MAX_INLINE_IMAGE_BYTES", 20 * 1024 * 1024))
MAX_INLINE_VIDEO_BYTES = int(os.environ.get("MAX_INLINE_VIDEO_BYTES", 80 * 1024 * 1024))
JIMENG_INPUT_IMAGE_MAX_BYTES = int(os.environ.get("JIMENG_INPUT_IMAGE_MAX_BYTES", 10 * 1024 * 1024))
JIMENG_INPUT_IMAGE_TARGET_MIN_BYTES = int(os.environ.get("JIMENG_INPUT_IMAGE_TARGET_MIN_BYTES", 8 * 1024 * 1024))
JIMENG_INPUT_IMAGE_TARGET_BYTES = int(os.environ.get("JIMENG_INPUT_IMAGE_TARGET_BYTES", 9 * 1024 * 1024 + 512 * 1024))
HAPPYHORSE_INPUT_IMAGE_MAX_BYTES = int(os.environ.get("HAPPYHORSE_INPUT_IMAGE_MAX_BYTES", 10 * 1024 * 1024))
HAPPYHORSE_INPUT_IMAGE_TARGET_BYTES = int(os.environ.get("HAPPYHORSE_INPUT_IMAGE_TARGET_BYTES", 9 * 1024 * 1024 + 512 * 1024))


def _sanitize_remote_error_detail(text: str, url: str = "") -> str:
    cleaned = str(text or "").strip()
    if url:
        cleaned = cleaned.replace(url, "[remote-url]")
    cleaned = re.sub(r"https?://[^\s'\"<>]+", "[remote-url]", cleaned)
    return cleaned


def _response_url(response) -> str:
    try:
        return str(response.request.url)
    except Exception:  # noqa: BLE001 - best-effort observability only.
        return ""


def _http_remote_failure_reason(status_code: int) -> str:
    if status_code == 403:
        return "remote_http_403"
    if status_code == 404:
        return "remote_http_404"
    if 500 <= status_code <= 599:
        return "remote_http_5xx"
    return "remote_http_error"


class RemoteFileCacheError(RuntimeError):
    """Structured failure for remote media caching without exposing signed URLs."""

    def __init__(
        self,
        reason: str,
        *,
        url: str = "",
        status_code: int | None = None,
        content_type: str = "",
        content_length: str = "",
        detail: str = "",
        exception_type: str = "",
    ):
        self.reason = reason or "remote_cache_unknown"
        self.url = url or ""
        self.status_code = status_code
        self.content_type = content_type or ""
        self.content_length = content_length or ""
        self.detail = _sanitize_remote_error_detail(detail or "", self.url)
        self.exception_type = exception_type or ""
        super().__init__(self.user_message())

    def user_message(self) -> str:
        metadata = self._metadata_text()
        if self.reason.startswith("remote_http_"):
            status = self.status_code if self.status_code is not None else "非 200"
            return f"远程链接返回 HTTP {status}{metadata}"
        if self.reason == "remote_empty_response":
            return f"远程文件下载为空{metadata}"
        if self.reason == "local_write_failed":
            detail = self.detail or self.exception_type or "未知错误"
            return f"本地写入失败：{detail}{metadata}"
        detail = self.detail or self.exception_type or "未知错误"
        return f"远程文件下载失败：{detail}{metadata}"

    def _metadata_text(self) -> str:
        parts = []
        if self.content_type:
            parts.append(f"content-type={self.content_type}")
        if self.content_length:
            parts.append(f"content-length={self.content_length}")
        if self.exception_type:
            parts.append(f"exception={self.exception_type}")
        return f"（{', '.join(parts)}）" if parts else ""

    def safe_context(self) -> dict:
        parsed = urlparse(self.url)
        return {
            "reason": self.reason,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "exception_type": self.exception_type,
            "remote_host": parsed.netloc,
            "url_hash": hashlib.sha256(self.url.encode("utf-8", "ignore")).hexdigest()[:12] if self.url else "",
        }


async def init_http_client():
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(follow_redirects=True)


async def close_http_client():
    global http_client
    if http_client is not None:
        try:
            await http_client.aclose()
        finally:
            http_client = None


def notify_media_file_saved(fpath) -> None:
    """Queue a generated/uploaded media file for cloud sync and mark DBs for backup."""
    fpath = Path(fpath)
    if not fpath.is_file():
        return
    if cloud_sync:
        cloud_sync.queue_file(fpath)
        cloud_sync.mark_db_dirty()


def set_files_dir(path: Path):
    path = Path(path)
    _ensure_files_dir(path)
    _current_files_dir.set(path)


def get_files_dir() -> Path:
    path = _current_files_dir.get()
    _ensure_files_dir(path)
    return path


def _ensure_files_dir(path: Path) -> None:
    path = Path(path)
    with _files_dir_lock:
        if path in _known_files_dirs:
            return
        path.mkdir(parents=True, exist_ok=True)
        _known_files_dirs.add(path)


async def write_upload_to_path(upload_file, target_path: Path, chunk_size: int = FILE_IO_CHUNK_SIZE) -> int:
    """Persist an UploadFile to disk without reading the whole payload into memory."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    await upload_file.seek(0)
    async with aiofiles.open(target_path, "wb") as f:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            await f.write(chunk)
    await upload_file.seek(0)
    return size


def infer_extension_from_content_type(content_type: str, default_ext: str = ".bin") -> str:
    content_type = (content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "webp" in content_type:
        return ".webp"
    if "mp4" in content_type:
        return ".mp4"
    if "mp3" in content_type or "mpeg" in content_type:
        return ".mp3"
    if "wav" in content_type:
        return ".wav"
    return default_ext


def _normalize_image_output_to_png_bytes(raw: bytes) -> bytes:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("当前环境缺少 Pillow，无法统一转换图片输出为 PNG。") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True, compress_level=6)
        return buf.getvalue()
    except Exception as exc:
        raise RuntimeError("图片生成结果转换 PNG 失败。") from exc


async def _write_response_stream_to_local(response, ext: str = "") -> str:
    if response.status_code != 200:
        raise RemoteFileCacheError(
            _http_remote_failure_reason(int(response.status_code or 0)),
            url=_response_url(response),
            status_code=int(response.status_code or 0),
            content_type=response.headers.get("content-type", ""),
            content_length=response.headers.get("content-length", ""),
        )

    resolved_ext = ext or infer_extension_from_content_type(response.headers.get("content-type", ""))
    fname = f"cached_{uuid.uuid4().hex[:10]}{resolved_ext}"
    fpath = get_files_dir() / fname

    if resolved_ext == ".png":
        chunks = []
        async for chunk in response.aiter_bytes(FILE_IO_CHUNK_SIZE):
            if chunk:
                chunks.append(chunk)
        raw = b"".join(chunks)
        if not raw:
            raise RemoteFileCacheError(
                "remote_empty_response",
                url=_response_url(response),
                status_code=int(response.status_code or 0),
                content_type=response.headers.get("content-type", ""),
                content_length=response.headers.get("content-length", ""),
            )
        png = await asyncio.to_thread(_normalize_image_output_to_png_bytes, raw)
        try:
            fpath.write_bytes(png)
        except OSError as exc:
            raise RemoteFileCacheError(
                "local_write_failed",
                url=_response_url(response),
                status_code=int(response.status_code or 0),
                content_type=response.headers.get("content-type", ""),
                content_length=response.headers.get("content-length", ""),
                detail=str(exc),
                exception_type=exc.__class__.__name__,
            ) from exc
    else:
        total_bytes = 0
        try:
            async with aiofiles.open(fpath, "wb") as f:
                async for chunk in response.aiter_bytes(FILE_IO_CHUNK_SIZE):
                    if chunk:
                        total_bytes += len(chunk)
                        await f.write(chunk)
        except OSError as exc:
            raise RemoteFileCacheError(
                "local_write_failed",
                url=_response_url(response),
                status_code=int(response.status_code or 0),
                content_type=response.headers.get("content-type", ""),
                content_length=response.headers.get("content-length", ""),
                detail=str(exc),
                exception_type=exc.__class__.__name__,
            ) from exc
        if total_bytes <= 0:
            try:
                fpath.unlink(missing_ok=True)
            except OSError:
                pass
            raise RemoteFileCacheError(
                "remote_empty_response",
                url=_response_url(response),
                status_code=int(response.status_code or 0),
                content_type=response.headers.get("content-type", ""),
                content_length=response.headers.get("content-length", ""),
            )
    notify_media_file_saved(fpath)
    return f"/api/files/{fname}"


async def stream_remote_file_to_local(url: str, ext: str = "") -> str:
    client = http_client
    if client is None:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as tmp:
            async with tmp.stream("GET", url) as resp:
                local_url = await _write_response_stream_to_local(resp, ext)
                return local_url or url

    async with client.stream("GET", url, timeout=60) as resp:
        local_url = await _write_response_stream_to_local(resp, ext)
        return local_url or url


def _remote_cache_failure_detail(exc: Exception, url: str = "") -> str:
    if isinstance(exc, RemoteFileCacheError):
        return exc.user_message()
    text = _sanitize_remote_error_detail(str(exc).strip(), url)
    return text or exc.__class__.__name__ or "未知错误"


def _remote_cache_failure_context(exc: Exception, url: str = "") -> dict:
    if isinstance(exc, RemoteFileCacheError):
        return exc.safe_context()
    parsed = urlparse(url or "")
    return {
        "reason": "remote_cache_exception",
        "status_code": None,
        "content_type": "",
        "content_length": "",
        "exception_type": exc.__class__.__name__,
        "remote_host": parsed.netloc,
        "url_hash": hashlib.sha256(url.encode("utf-8", "ignore")).hexdigest()[:12] if url else "",
    }


# ── 模型路由 ─────────────────────────────────────────

def is_openai_model(model: str) -> bool:
    return model.startswith("gpt") or model.startswith("o3") or model.startswith("o4") or model.startswith("o1")


async def llm_chat(prompt: str, model: str, conversation_id: str = "") -> str:
    if is_openai_model(model):
        if not openai_service:
            raise Exception("OpenAI API Key 未配置，请在设置页面配置。")
        return await openai_service.chat(prompt, model=model)
    else:
        if not ai_service:
            raise Exception("Gemini API Key 未配置，请在设置页面配置。")
        cid = conversation_id or f"chat_{uuid.uuid4().hex[:6]}"
        result = await ai_service.chat(prompt, cid, model)
    return result.get("response", "")


# ── 权限 ─────────────────────────────────────────────

def require_admin(request: Request):
    if os.environ.get("AUTH_ENABLED", "true").lower() not in ("true", "1", "yes"):
        return
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")


def get_proxy_url() -> str:
    return (os.environ.get("HK_PROXY_URL", "") or settings_manager.get("api_proxy_url", "")).rstrip("/")


def build_signed_public_file_url(url: str, expires_in_seconds: int = 3600) -> str:
    local_path = _extract_local_file_path(url)
    if not local_path:
        return url
    public_base = (os.environ.get("PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not public_base:
        return url

    filename = local_path.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        return url

    expires = int(time.time()) + max(60, int(expires_in_seconds or 3600))
    payload = f"{filename}:{expires}"
    sig = hmac.new(auth.JWT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    query = urlencode({"expires": str(expires), "sig": sig})
    return f"{public_base}/public-files/{filename}?{query}"


def verify_signed_public_file(filename: str, expires: str, sig: str) -> bool:
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if expires_int < int(time.time()):
        return False
    payload = f"{filename}:{expires_int}"
    expected = hmac.new(auth.JWT_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig or "")


# ── JSON 提取 ────────────────────────────────────────

def extract_json(text: str) -> dict | None:
    import re
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    s = cleaned.find("{")
    e = cleaned.rfind("}") + 1
    if s >= 0 and e > s:
        try:
            return json.loads(cleaned[s:e])
        except json.JSONDecodeError:
            pass
    return None


# ── Keepalive 响应 ───────────────────────────────────

def keepalive_response(async_fn):
    import asyncio

    async def _stream():
        task = asyncio.ensure_future(async_fn())
        try:
            while not task.done():
                yield b" "
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=15)
                except asyncio.TimeoutError:
                    continue
            result = task.result()
            yield json.dumps(result, ensure_ascii=False).encode()
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
            raise
        except Exception as exc:
            yield json.dumps({"_error": str(exc)[:500]}, ensure_ascii=False).encode()
    return StreamingResponse(_stream(), media_type="application/json")


# ── 文件缓存 ────────────────────────────────────────

async def cache_remote_file(
    url: str,
    ext: str = "",
    *,
    strict: bool = False,
    strict_error_message: str = "远程文件已返回，但保存到本地失败",
) -> str:
    if not url or url.startswith("/api/files/"):
        return url
    try:
        cached_url = await stream_remote_file_to_local(url, ext)
        if strict and cached_url == url:
            raise RuntimeError("远程文件下载失败或响应为空")
        return cached_url
    except Exception as exc:
        detail = _remote_cache_failure_detail(exc, url)
        logger.warning(
            "Failed to cache remote file as %s: %s context=%s",
            ext or "original",
            detail,
            _remote_cache_failure_context(exc, url),
        )
        if strict:
            raise HTTPException(502, f"{strict_error_message}：{detail}") from exc
        return url


async def cache_remote_file_result(result: dict) -> dict:
    if "image_url" in result and result["image_url"]:
        result["image_url"] = await cache_remote_file(
            result["image_url"],
            ".png",
            strict=True,
            strict_error_message="生成图片已返回，但保存为 PNG 失败",
        )
    if "images" in result:
        for img in result["images"]:
            if "url" in img and img["url"]:
                img["url"] = await cache_remote_file(
                    img["url"],
                    ".png",
                    strict=True,
                    strict_error_message="生成图片已返回，但保存为 PNG 失败",
                )
                img["mime_type"] = "image/png"
    return result


def save_gemini_image_result(result: dict) -> dict:
    import base64 as _b64
    saved = []
    for img in result.get("images", []):
        data = img.get("data", "")
        if not data:
            continue
        png = _normalize_image_output_to_png_bytes(_b64.b64decode(data))
        fname = f"gemini_{uuid.uuid4().hex[:12]}.png"
        fpath = get_files_dir() / fname
        fpath.write_bytes(png)
        notify_media_file_saved(fpath)
        saved.append({"url": f"/api/files/{fname}", "mime_type": "image/png"})
    first_url = saved[0]["url"] if saved else ""
    return {"image_url": first_url, "images": saved}


# ── 图片/视频 URL 解析 ──────────────────────────────

def _extract_local_file_path(url: str) -> str:
    if not url:
        return ""
    def _public_file_to_api_path(path: str) -> str:
        prefix = "/public-files/"
        if not path.startswith(prefix):
            return ""
        from urllib.parse import unquote
        filename = unquote(path[len(prefix):]).strip()
        if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
            return ""
        return f"/api/files/{filename}"

    if url.startswith("/api/files/"):
        return url
    if url.startswith("/public-files/"):
        return _public_file_to_api_path(url.split("?", 1)[0].split("#", 1)[0])
    if url.startswith(("http://", "https://")):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.path.startswith("/api/files/"):
                return parsed.path
            public_file = _public_file_to_api_path(parsed.path)
            if public_file:
                return public_file
        except Exception:
            return ""
    return ""


def find_local_file_path(filename: str, *, include_all_user_dirs: bool = False) -> Path | None:
    filename = (filename or "").strip()
    if not filename:
        return None

    seen: set[Path] = set()

    def _candidates():
        # Default resolution must stay inside the current request scope plus the shared public files dir.
        for path in (get_files_dir(), DATA_DIR / "files"):
            candidate = Path(path)
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate / filename

        if include_all_user_dirs:
            users_dir = DATA_DIR / "users"
            if users_dir.exists():
                for user_files_dir in users_dir.glob("*/files"):
                    candidate_dir = Path(user_files_dir)
                    if candidate_dir in seen:
                        continue
                    seen.add(candidate_dir)
                    yield candidate_dir / filename

    for candidate in _candidates():
        if candidate.exists():
            return candidate
    return None


def get_local_file_path_from_url(url: str) -> Path | None:
    local_path = _extract_local_file_path(url)
    if not local_path:
        return None
    filename = local_path.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    if not filename or filename in (".", "..") or "/" in filename or "\\" in filename:
        return None
    return find_local_file_path(filename) or find_local_file_path(filename, include_all_user_dirs=True)


def read_local_file(filename: str) -> bytes | None:
    filepath = find_local_file_path(filename) or find_local_file_path(filename, include_all_user_dirs=True)
    if filepath:
        return filepath.read_bytes()
    return None


def _image_mime_from_suffix(suffix: str) -> str:
    ext = suffix.lower().lstrip(".")
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/png")


def _safe_image_cache_stem(filepath: Path) -> str:
    raw = filepath.stem or "image"
    stem = "".join(ch.lower() if ch.isascii() and ch.isalnum() else "_" for ch in raw)
    stem = "_".join(part for part in stem.split("_") if part)
    return (stem or "image")[:28]


def _image_to_png_bytes(raw: bytes, *, target_bytes: int, max_bytes: int, limit_label: str = "参考图") -> bytes:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise HTTPException(413, f"{limit_label}超过 10 MiB 限制，且当前环境缺少图片压缩组件 Pillow。") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    except Exception as exc:
        raise HTTPException(413, f"{limit_label}超过 10 MiB 限制，且自动压缩失败。请先把图片压缩到 10 MiB 以下再上传。") from exc

    width, height = img.size
    if width < 1 or height < 1:
        raise HTTPException(400, "参考图无效，请换一张图片后重试。")

    target_high = min(max(target_bytes, JIMENG_INPUT_IMAGE_TARGET_MIN_BYTES), max_bytes - 128 * 1024)
    target_low = min(JIMENG_INPUT_IMAGE_TARGET_MIN_BYTES, target_high)

    def save_png(source_img) -> bytes:
        buf = io.BytesIO()
        source_img.save(buf, format="PNG", optimize=True, compress_level=6)
        return buf.getvalue()

    full = save_png(img)
    if len(full) <= target_high:
        return full

    best_under: bytes | None = None
    closest_to_range: bytes | None = None
    low_scale = 0.1
    high_scale = 1.0

    for _attempt in range(12):
        scale = (low_scale + high_scale) / 2
        next_width = max(256, int(width * scale))
        next_height = max(256, int(height * scale))
        candidate_img = img.resize((next_width, next_height), Image.LANCZOS)
        data = save_png(candidate_img)
        size = len(data)

        if size <= target_high:
            if best_under is None or size > len(best_under):
                best_under = data
            if size >= target_low:
                return data
            low_scale = scale
        else:
            if size <= max_bytes and (closest_to_range is None or size < len(closest_to_range)):
                closest_to_range = data
            high_scale = scale

    candidate = best_under or closest_to_range
    if candidate and len(candidate) <= max_bytes:
        return candidate
    raise HTTPException(413, f"{limit_label}超过 10 MiB 限制，自动压缩后仍然过大。请先降低分辨率或压缩到 10 MiB 以下再上传。")


def _compressed_image_cache_path(filepath: Path, target_bytes: int, cache_prefix: str = "ref") -> Path:
    stat = filepath.stat()
    digest_src = f"{cache_prefix}:png:{filepath.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{target_bytes}"
    digest = hashlib.sha1(digest_src.encode("utf-8")).hexdigest()[:12]
    safe_prefix = "".join(ch.lower() if ch.isascii() and ch.isalnum() else "_" for ch in cache_prefix)[:24] or "ref"
    fname = f"{safe_prefix}_{_safe_image_cache_stem(filepath)}_{digest}.png"
    return get_files_dir() / fname


def _compress_local_image_for_external(
    filepath: Path,
    *,
    target_bytes: int,
    max_bytes: int,
    limit_label: str = "参考图",
    cache_prefix: str = "ref",
) -> Path:
    target_path = _compressed_image_cache_path(filepath, target_bytes, cache_prefix)
    if target_path.exists() and 0 < target_path.stat().st_size <= max_bytes:
        return target_path

    raw = filepath.read_bytes()
    compressed = _image_to_png_bytes(raw, target_bytes=target_bytes, max_bytes=max_bytes, limit_label=limit_label)
    target_path.write_bytes(compressed)
    notify_media_file_saved(target_path)
    logger.info(
        "Compressed Jimeng reference image: %s %d -> %d bytes",
        filepath.name,
        len(raw),
        len(compressed),
    )
    return target_path


def _compress_data_image_for_external(
    data_url: str,
    *,
    target_bytes: int,
    max_bytes: int,
    limit_label: str = "参考图",
) -> str:
    try:
        header, payload = data_url.split(",", 1)
        raw = base64.b64decode(payload)
    except Exception as exc:
        raise HTTPException(400, "参考图数据无效，请重新上传图片。") from exc
    if len(raw) <= max_bytes:
        return data_url
    compressed = _image_to_png_bytes(raw, target_bytes=target_bytes, max_bytes=max_bytes, limit_label=limit_label)
    logger.info("Compressed inline Jimeng reference image: %d -> %d bytes", len(raw), len(compressed))
    return f"data:image/png;base64,{base64.b64encode(compressed).decode()}"


async def resolve_image_for_external(
    url: str,
    *,
    max_image_bytes: int | None = None,
    auto_compress: bool = False,
    target_image_bytes: int | None = None,
    limit_label: str = "参考图",
    cache_prefix: str = "ref",
) -> str:
    max_bytes = int(max_image_bytes or 0)
    target_bytes = int(target_image_bytes or 0) if target_image_bytes else max(1, max_bytes - 1024 * 1024)

    if url.startswith("data:image") and max_bytes:
        if auto_compress:
            return await asyncio.to_thread(
                _compress_data_image_for_external,
                url,
                target_bytes=target_bytes,
                max_bytes=max_bytes,
                limit_label=limit_label,
            )
        try:
            _header, payload = url.split(",", 1)
            if len(base64.b64decode(payload)) > max_bytes:
                raise HTTPException(413, f"{limit_label}超过 10 MiB 限制，请压缩后重试。")
        except HTTPException:
            raise
        except Exception:
            return url

    local_path = _extract_local_file_path(url)
    if not local_path:
        return url
    filename = local_path.rsplit("/", 1)[-1]
    filepath = find_local_file_path(filename) or find_local_file_path(filename, include_all_user_dirs=True)
    if not filepath:
        return local_path
    if max_bytes and filepath.stat().st_size > max_bytes:
        if not auto_compress:
            raise HTTPException(413, f"{limit_label}超过 10 MiB 限制，请压缩后重试。")
        filepath = await asyncio.to_thread(
            _compress_local_image_for_external,
            filepath,
            target_bytes=target_bytes,
            max_bytes=max_bytes,
            limit_label=limit_label,
            cache_prefix=cache_prefix,
        )
        local_path = f"/api/files/{filepath.name}"

    signed_url = build_signed_public_file_url(local_path)
    if signed_url != local_path:
        return signed_url
    if filepath.stat().st_size > MAX_INLINE_IMAGE_BYTES:
        raise HTTPException(413, "图片文件过大，请配置 PUBLIC_BASE_URL 后使用公网文件地址。")
    content = await asyncio.to_thread(filepath.read_bytes)
    mime = _image_mime_from_suffix(filepath.suffix)
    b64 = base64.b64encode(content).decode()
    return f"data:{mime};base64,{b64}"


async def resolve_image_as_public_url(url: str) -> str:
    local_path = _extract_local_file_path(url)
    if not local_path:
        return url
    signed_url = build_signed_public_file_url(local_path)
    if signed_url != local_path:
        return signed_url
    return local_path


async def resolve_video_for_external(url: str) -> str:
    local_path = _extract_local_file_path(url)
    if not local_path:
        return url
    signed_url = build_signed_public_file_url(local_path)
    if signed_url != local_path:
        return signed_url
    import base64
    filename = local_path.rsplit("/", 1)[-1]
    filepath = find_local_file_path(filename) or find_local_file_path(filename, include_all_user_dirs=True)
    if not filepath:
        return local_path
    if filepath.stat().st_size > MAX_INLINE_VIDEO_BYTES:
        raise HTTPException(413, "视频文件过大，请配置 PUBLIC_BASE_URL 后使用公网文件地址。")
    content = await asyncio.to_thread(filepath.read_bytes)
    ext = filepath.suffix.lower().lstrip(".")
    mime = {"mp4": "video/mp4", "webm": "video/webm"}.get(ext, "video/mp4")
    b64 = base64.b64encode(content).decode()
    return f"data:{mime};base64,{b64}"


async def resolve_video_as_public_url(url: str) -> str:
    local_path = _extract_local_file_path(url)
    if not local_path:
        return url
    signed_url = build_signed_public_file_url(local_path)
    if signed_url != local_path:
        return signed_url
    return local_path


def get_local_video_duration_seconds(url: str) -> float | None:
    local_path = _extract_local_file_path(url)
    if not local_path:
        return None

    filename = local_path.rsplit("/", 1)[-1]
    filepath = find_local_file_path(filename, include_all_user_dirs=True)
    if filepath is None:
        return None

    def _read_mp4_duration_seconds(path: Path) -> float | None:
        def read_box_header(handle):
            header = handle.read(8)
            if len(header) < 8:
                return None
            size = int.from_bytes(header[:4], "big")
            box_type = header[4:8]
            header_size = 8
            if size == 1:
                extended = handle.read(8)
                if len(extended) < 8:
                    return None
                size = int.from_bytes(extended, "big")
                header_size = 16
            elif size == 0:
                size = path.stat().st_size - handle.tell() + header_size
            if size < header_size:
                return None
            return size, box_type, header_size

        def scan_boxes(handle, end_pos: int) -> float | None:
            while handle.tell() + 8 <= end_pos:
                box_start = handle.tell()
                header = read_box_header(handle)
                if not header:
                    return None
                size, box_type, header_size = header
                box_end = min(box_start + size, end_pos)
                payload_size = box_end - handle.tell()
                if payload_size < 0:
                    return None
                if box_type == b"mvhd":
                    payload = handle.read(min(payload_size, 32))
                    if len(payload) < 20:
                        return None
                    version = payload[0]
                    if version == 1:
                        if len(payload) < 32:
                            return None
                        timescale = int.from_bytes(payload[20:24], "big")
                        duration = int.from_bytes(payload[24:32], "big")
                    else:
                        timescale = int.from_bytes(payload[12:16], "big")
                        duration = int.from_bytes(payload[16:20], "big")
                    return duration / timescale if timescale > 0 and duration > 0 else None
                if box_type == b"moov":
                    duration = scan_boxes(handle, box_end)
                    if duration:
                        return duration
                handle.seek(box_end)
            return None

        try:
            with path.open("rb") as handle:
                return scan_boxes(handle, path.stat().st_size)
        except OSError:
            return None

    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(filepath),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return _read_mp4_duration_seconds(filepath)

    raw = (completed.stdout or "").strip()
    if not raw:
        return None
    try:
        duration = float(raw)
    except ValueError:
        return _read_mp4_duration_seconds(filepath)
    return duration if duration > 0 else _read_mp4_duration_seconds(filepath)
