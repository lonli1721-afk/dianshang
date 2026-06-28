from __future__ import annotations

"""OpenAI-compatible service for GPT models."""

import base64
import io
import httpx
import asyncio
import random
from typing import Optional, AsyncGenerator

OPENAI_MODELS = [
    {"id": "gpt-5.4", "name": "GPT-5.4 (旗舰)"},
    {"id": "gpt-5.4-mini", "name": "GPT-5.4 Mini"},
    {"id": "gpt-4.1", "name": "GPT-4.1"},
    {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini"},
    {"id": "gpt-4o", "name": "GPT-4o"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (快速)"},
    {"id": "o4-mini", "name": "o4-mini (推理)"},
    {"id": "o3", "name": "o3 (推理旗舰)"},
    {"id": "o3-mini", "name": "o3-mini"},
]

OPENAI_IMAGE_MODELS = [
    {
        "id": "gpt-image-2",
        "name": "GPT Image 2",
        "provider": "openai_image",
        "supports_ref_images": True,
        "max_ref_images": 4,
        "supported_qualities": ["1K", "2K", "4K"],
        "default_quality": "2K",
    },
]

OPENAI_IMAGE_MAX_REFERENCE_IMAGES = 4
OPENAI_IMAGE_REFERENCE_MAX_BYTES = 4 * 1024 * 1024
OPENAI_IMAGE_REFERENCE_MAX_SIDE = 1536

_NEW_API_MODELS = frozenset({
    "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4-pro",
    "gpt-5.3", "gpt-5.2", "gpt-5.2-pro", "gpt-5.1", "gpt-5",
    "gpt-5-mini", "gpt-5-nano", "gpt-5-pro",
    "o3", "o3-mini", "o4-mini", "o1", "o1-pro",
})


def _uses_max_completion_tokens(model: str) -> bool:
    base = model.rsplit("-202", 1)[0]
    return base in _NEW_API_MODELS


class OpenAIService:
    def __init__(self, api_key: str, base_url: str = "https://open-api.mincode.cn/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _build_body(self, model: str, messages: list, max_tokens: int, temperature: float, stream: bool = False) -> dict:
        body = {"model": model, "messages": messages}
        if _uses_max_completion_tokens(model):
            body["max_completion_tokens"] = max_tokens
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature
        if stream:
            body["stream"] = True
        return body

    def _friendly_error(self, exc: Exception) -> str:
        msg = str(exc)
        if "429" in msg or "Too Many Requests" in msg:
            return "OpenAI 通道当前触发限流，系统已重试多次仍失败，请稍后继续使用 GPT 重试。"
        if "503" in msg or "502" in msg or "504" in msg:
            return "OpenAI 通道当前繁忙，系统已重试多次仍失败，请稍后继续使用 GPT 重试。"
        if "401" in msg:
            return "OpenAI API Key 无效或已过期，请检查配置。"
        if "403" in msg:
            return "OpenAI API Key 权限不足，请检查账号或模型权限。"
        return msg[:300]

    def _friendly_image_error(self, exc: Exception) -> str:
        msg = str(exc)
        if "429" in msg or "Too Many Requests" in msg:
            return "OpenAI 图片通道当前触发限流，系统已重试多次仍失败，请稍后重试。"
        if "503" in msg or "502" in msg or "504" in msg:
            return "OpenAI 图片通道当前繁忙或代理超时，系统已重试多次仍失败；请减少参考图数量或稍后重试。"
        return self._friendly_error(exc)

    async def _post_json(self, body: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    resp.raise_for_status()
                    try:
                        return resp.json()
                    except ValueError as exc:
                        preview = (resp.text or "").strip()[:300] or "empty response"
                        raise Exception(f"OpenAI 通道返回了非 JSON 响应，可能是代理连接中断或上游返回错误页：{preview}") from exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in (429, 502, 503, 504) and attempt < 3:
                    retry_after = exc.response.headers.get("retry-after", "")
                    try:
                        wait_seconds = float(retry_after)
                    except (TypeError, ValueError):
                        wait_seconds = min(12.0, 2.0 * (2 ** attempt)) + random.uniform(0, 0.8)
                    await asyncio.sleep(max(0.8, min(wait_seconds, 20.0)))
                    continue
                raise Exception(self._friendly_error(exc))
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(min(8.0, 1.5 * (2 ** attempt)) + random.uniform(0, 0.5))
                    continue
                raise Exception(self._friendly_error(exc))
        raise Exception(self._friendly_error(last_error or Exception("OpenAI 请求失败")))

    async def chat(
        self,
        prompt: str,
        model: str = "gpt-4o",
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = self._build_body(model, messages, max_tokens, temperature)

        data = await self._post_json(body)
        return data["choices"][0]["message"]["content"]

    async def chat_vision(
        self,
        text_prompt: str,
        image_data_list: list[tuple[bytes, str]],
        model: str = "gpt-5.4",
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.5,
    ) -> str:
        """Vision chat: send text + images (bytes, mime_type) to GPT."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        content_parts: list[dict] = []
        for img_bytes, mime in image_data_list:
            b64 = base64.b64encode(img_bytes).decode()
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
            })
        content_parts.append({"type": "text", "text": text_prompt})
        messages.append({"role": "user", "content": content_parts})

        body = self._build_body(model, messages, max_tokens, temperature)

        data = await self._post_json(body)
        return data["choices"][0]["message"]["content"]

    async def _post_image_json(self, path: str, body: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    resp = await client.post(
                        f"{self.base_url}{path}",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in (429, 502, 503, 504) and attempt < 3:
                    await asyncio.sleep(min(12.0, 2.0 * (2 ** attempt)) + random.uniform(0, 0.8))
                    continue
                raise Exception(self._friendly_image_error(exc))
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(min(8.0, 1.5 * (2 ** attempt)) + random.uniform(0, 0.5))
                    continue
                raise Exception(self._friendly_image_error(exc))
        raise Exception(self._friendly_image_error(last_error or Exception("OpenAI image request failed")))

    async def _post_image_multipart(self, path: str, data: dict, files: list[tuple[str, tuple[str, bytes, str]]]) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            streams = []
            try:
                multipart_files = []
                for field, (filename, content, mime) in files:
                    stream = io.BytesIO(content)
                    streams.append(stream)
                    multipart_files.append((field, (filename, stream, mime)))
                async with httpx.AsyncClient(timeout=300) as client:
                    resp = await client.post(
                        f"{self.base_url}{path}",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        data=data,
                        files=multipart_files,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in (429, 502, 503, 504) and attempt < 3:
                    await asyncio.sleep(min(12.0, 2.0 * (2 ** attempt)) + random.uniform(0, 0.8))
                    continue
                raise Exception(self._friendly_image_error(exc))
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(min(8.0, 1.5 * (2 ** attempt)) + random.uniform(0, 0.5))
                    continue
                raise Exception(self._friendly_image_error(exc))
            finally:
                for stream in streams:
                    stream.close()
        raise Exception(self._friendly_image_error(last_error or Exception("OpenAI image request failed")))

    def _image_size(self, width: int, height: int) -> str:
        if width == height:
            return "1024x1024"
        return "1536x1024" if width > height else "1024x1536"

    def _image_quality(self, quality: str) -> str:
        normalized = (quality or "").strip().upper()
        return {"1K": "low", "2K": "medium", "4K": "high"}.get(normalized, "medium")

    def _image_model(self, model: str) -> str:
        normalized = (model or "").strip()
        if not normalized or normalized == "image2":
            return "gpt-image-2"
        return normalized

    def _image_result(self, data: dict) -> dict:
        images = []
        for item in data.get("data") or []:
            b64 = item.get("b64_json") or item.get("b64")
            url = item.get("url") or ""
            if b64:
                images.append({"data": b64, "mime_type": "image/png"})
            elif url:
                images.append({"url": url, "mime_type": "image/png"})
        return {"images": images, "image_url": images[0].get("url", "") if images else ""}

    def _prepare_reference_image(self, content: bytes, mime: str) -> tuple[bytes, str]:
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return content, mime or "image/png"

        try:
            with Image.open(io.BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source)
                if image.mode in ("RGBA", "LA"):
                    alpha = image.getchannel("A")
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    background.paste(image.convert("RGB"), mask=alpha)
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                if max(image.size) > OPENAI_IMAGE_REFERENCE_MAX_SIDE:
                    image.thumbnail(
                        (OPENAI_IMAGE_REFERENCE_MAX_SIDE, OPENAI_IMAGE_REFERENCE_MAX_SIDE),
                        Image.LANCZOS,
                    )

                for quality in (90, 82, 74, 66):
                    buf = io.BytesIO()
                    image.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
                    data = buf.getvalue()
                    if len(data) <= OPENAI_IMAGE_REFERENCE_MAX_BYTES:
                        return data, "image/jpeg"

                for _ in range(4):
                    width, height = image.size
                    image = image.resize((max(256, int(width * 0.75)), max(256, int(height * 0.75))), Image.LANCZOS)
                    buf = io.BytesIO()
                    image.save(buf, format="JPEG", quality=74, optimize=True, progressive=True)
                    data = buf.getvalue()
                    if len(data) <= OPENAI_IMAGE_REFERENCE_MAX_BYTES:
                        return data, "image/jpeg"
        except Exception:
            return content, mime or "image/png"

        return data, "image/jpeg"

    async def generate_image(
        self,
        prompt: str,
        model: str = "gpt-image-2",
        width: int = 1024,
        height: int = 1024,
        reference_images: list[tuple[bytes, str]] | None = None,
        quality: str = "2K",
    ) -> dict:
        body = {
            "model": self._image_model(model),
            "prompt": prompt,
            "size": self._image_size(width, height),
            "quality": self._image_quality(quality),
            "n": 1,
            "output_format": "png",
        }
        image_refs = (reference_images or [])[:OPENAI_IMAGE_MAX_REFERENCE_IMAGES]
        if not image_refs:
            return self._image_result(await self._post_image_json("/images/generations", body))

        files = []
        for index, (content, mime) in enumerate(image_refs):
            content, mime = self._prepare_reference_image(content, mime)
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")
            files.append(("image[]", (f"reference_{index}.{ext}", content, mime or "image/png")))
        return self._image_result(await self._post_image_multipart("/images/edits", body, files))

    async def chat_stream(
        self,
        prompt: str,
        model: str = "gpt-4o",
        system: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = self._build_body(model, messages, max_tokens, temperature, stream=True)

        async with httpx.AsyncClient(timeout=300) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(payload)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue
            except Exception as exc:
                raise Exception(self._friendly_error(exc))
