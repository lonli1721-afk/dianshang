from __future__ import annotations

import asyncio
import math
import os
import re
import struct
import uuid
import wave
import json
import hashlib
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

import database as db
import deps
from doubao_speech_service import DoubaoSpeechError, synthesize_speech_2_0_file, transcribe_media_file
from video_model_registry import (
    enrich_video_model_cost_estimates,
    get_video_model_spec,
    get_video_model_specs,
    parse_toapis_credit_price_overrides,
    parse_toapis_usd_cny_rate,
)


router = APIRouter()


ASR_API_KEY_FIELD = {
    "id": "api_key",
    "label": "豆包语音 API Key",
    "setting_keys": ["game_doubao_speech_api_key", "doubao_speech_api_key"],
    "env": "DOUBAO_SPEECH_API_KEY",
}

POSTER_TRANSITION_DURATION = 0.45

ARK_MODEL_ID = "doubao-seed-2-0-pro-260215"
ARK_CHAT_COMPLETIONS_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

LEGACY_ASR_CONFIG_FIELDS = [
    {
        "id": "app_id",
        "label": "App ID",
        "setting_keys": ["game_volcengine_asr_app_id", "volcengine_asr_app_id"],
        "env": "VOLCENGINE_ASR_APP_ID",
    },
    {
        "id": "access_key",
        "label": "Access Key",
        "setting_keys": ["game_volcengine_asr_access_key", "volcengine_asr_access_key"],
        "env": "VOLCENGINE_ASR_ACCESS_KEY",
    },
    {
        "id": "secret_key",
        "label": "Secret Key / Token",
        "setting_keys": ["game_volcengine_asr_secret_key", "volcengine_asr_secret_key"],
        "env": "VOLCENGINE_ASR_SECRET_KEY",
    },
    {
        "id": "ws_endpoint",
        "label": "WebSocket Endpoint",
        "setting_keys": ["game_volcengine_asr_ws_endpoint", "volcengine_asr_ws_endpoint"],
        "env": "VOLCENGINE_ASR_WS_ENDPOINT",
    },
]


LANGUAGE_MODELS = [
    {
        "id": "doubao-seed-2-0-pro-260215",
        "name": "Doubao Seed 2.0 Pro",
        "provider": "volcengine_ark",
        "available": True,
    },
    {
        "id": "doubao-seed-2-0-mini",
        "name": "Doubao Seed 2.0 Mini",
        "provider": "volcengine_ark",
        "available": False,
        "note": "请按火山方舟控制台的模型 ID 配置后启用",
    },
    {
        "id": "doubao-seed-2-0-lite",
        "name": "Doubao Seed 2.0 Lite",
        "provider": "volcengine_ark",
        "available": False,
        "note": "请按火山方舟控制台的模型 ID 配置后启用",
    },
]

IMAGE_MODELS = [
    {
        "id": "seedream-5.0",
        "name": "Seedream 5.0",
        "provider": "jimeng",
        "available": True,
    },
    {
        "id": "seedream-4.5",
        "name": "Seedream 4.5",
        "provider": "jimeng",
        "available": True,
    },
    {
        "id": "image2",
        "name": "Image2 产品还原",
        "provider": "toapis",
        "available": True,
        "note": "使用 ToAPIs API 调用 Image2/GPT Image 2 生成完整产品详情表",
    },
    {
        "id": "nanobanana",
        "name": "Nano Banana",
        "provider": "custom_image",
        "available": False,
        "note": "待接入图片模型适配器",
    },
]

DEFAULT_STORYBOARD_SCENE_COUNT = 6
VEO_STORYBOARD_SCENE_COUNT = 4
VEO_STORYBOARD_DURATION = 8
WORKBENCH_DRAFT_SETTING_KEY = "batch_video_workbench_draft_v1"
PRODUCT_MEMORY_SETTING_KEY = "batch_video_product_memory_v1"
PRODUCT_MEMORY_LIMIT = 80


def _toapis_price_overrides() -> dict[str, float]:
    return parse_toapis_credit_price_overrides(
        deps.settings_manager.get("toapis_video_credit_prices", "")
        if getattr(deps, "settings_manager", None)
        else ""
    )


def _toapis_usd_cny_rate() -> float:
    return parse_toapis_usd_cny_rate(
        deps.settings_manager.get("toapis_usd_cny_rate", "")
        if getattr(deps, "settings_manager", None)
        else ""
    )


def _batch_video_models() -> list[dict]:
    models = get_video_model_specs(
        provider_filter=["jimeng", "happyhorse", "toapis"],
        toapis_credit_prices=_toapis_price_overrides(),
    )
    batch_ids = {
        "seedance-2.0",
        "happyhorse-1.0-i2v",
        "happyhorse-1.0-t2v",
        *{item["id"] for item in models if item.get("provider") == "toapis"},
    }
    available = [{**item, "available": True} for item in models if item.get("id") in batch_ids]
    return enrich_video_model_cost_estimates(available, toapis_usd_cny_rate=_toapis_usd_cny_rate())


def _is_fixed_eight_second_model(model_id: str) -> bool:
    spec = get_video_model_spec(model_id)
    return spec.get("provider") == "toapis" and int(spec.get("min_duration") or 0) == 8 and int(spec.get("max_duration") or 0) == 8


class ProductInput(BaseModel):
    name: str = ""
    category: str = ""
    description: str = ""
    image_urls: list[str] = Field(default_factory=list)
    detail_sheet_url: str = ""


class TranscriptionRequest(BaseModel):
    product: ProductInput = Field(default_factory=ProductInput)
    live_video_url: str = ""
    asr_provider: str = "volcengine_streaming_asr_2_0"
    language: str = "zh-CN"


class SellingPoint(BaseModel):
    title: str
    description: str = ""
    evidence: str = ""
    source: str = "manual"


class SellingPointsRequest(BaseModel):
    product: ProductInput = Field(default_factory=ProductInput)
    transcript_text: str = ""
    manual_selling_points: list[str] = Field(default_factory=list)
    language_model: str = "doubao-seed-2-0-pro-260215"


class StoryboardPlanRequest(BaseModel):
    product: ProductInput = Field(default_factory=ProductInput)
    selling_points: list[SellingPoint] = Field(default_factory=list)
    storyboard_reference_urls: list[str] = Field(default_factory=list)
    creative_brief: str = ""
    language_model: str = "doubao-seed-2-0-pro-260215"
    image_model: str = "seedream-5.0"
    video_model: str = "seedance-2.0"
    aspect_ratio: str = "9:16"
    duration: int = 5
    variant_count: int = 6
    creative_seed: str = ""
    regenerate_index: int = 0


class ProductReconstructionRequest(BaseModel):
    product: ProductInput = Field(default_factory=ProductInput)
    image_model: str = "image2"
    aspect_ratio: str = "16:9"


class ProductPosterRequest(BaseModel):
    product: ProductInput = Field(default_factory=ProductInput)
    selling_points: list[SellingPoint] = Field(default_factory=list)
    image_model: str = "image2"
    aspect_ratio: str = "9:16"


class StoryboardScene(BaseModel):
    id: str = ""
    title: str = ""
    selling_point: str = ""
    hook: str = ""
    image_prompt: str = ""
    video_prompt: str = ""
    voiceover_text: str = ""
    shot_notes: str = ""
    storyboard_image_url: str = ""
    video_url: str = ""


class SubmitBatchRequest(BaseModel):
    product: ProductInput = Field(default_factory=ProductInput)
    scenes: list[StoryboardScene] = Field(default_factory=list)
    image_model: str = "seedream-5.0"
    video_model: str = "seedance-2.0"
    aspect_ratio: str = "9:16"
    duration: int = 5
    resolution: str = "720p"


class FinalVideoSegment(BaseModel):
    scene_id: str = ""
    title: str = ""
    reference_mode: str = ""
    video_url: str = ""
    subtitle: str = ""
    voiceover_text: str = ""
    start_time: float | None = None
    end_time: float | None = None


class ComposeFinalVideoRequest(BaseModel):
    segments: list[FinalVideoSegment] = Field(default_factory=list)
    product_name: str = ""
    aspect_ratio: str = "9:16"
    subtitle_enabled: bool = True
    voiceover_enabled: bool = True
    keep_original_audio: bool = True
    bgm_enabled: bool = True
    bgm_url: str = ""
    original_audio_volume: float = 0.78
    voiceover_volume: float = 1.0
    bgm_volume: float = 0.45
    poster_image_url: str = ""
    poster_duration: float = 2.0
    tts_provider: str = "doubao_speech_2_0"
    tts_voice_type: str = ""
    tts_speed_ratio: float = 1.0
    output_name: str = ""


class WorkbenchDraftRequest(BaseModel):
    draft: dict[str, Any] = Field(default_factory=dict)


class ProductMemoryRequest(BaseModel):
    product_name: str = ""
    memory: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(text: str, limit: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:limit]


def _product_memory_key(product_name: str) -> str:
    return re.sub(r"\s+", " ", (product_name or "").strip()).lower()


def _cloud_sync_config() -> tuple[str, str]:
    settings = getattr(deps, "settings_manager", None)
    if not settings:
        return "", ""
    cloud_url = str(settings.get("cloud_url", "") or "").rstrip("/")
    cloud_token = str(settings.get("cloud_token", "") or "")
    return cloud_url, cloud_token


def _is_self_cloud_url(cloud_url: str) -> bool:
    public_base = (os.environ.get("PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not cloud_url or not public_base:
        return False
    try:
        cloud = urlparse(cloud_url)
        public = urlparse(public_base)
    except Exception:
        return cloud_url == public_base
    cloud_host = (cloud.hostname or "").lower()
    public_host = (public.hostname or "").lower()
    if not cloud_host or cloud_host != public_host:
        return False
    cloud_port = cloud.port
    public_port = public.port
    return cloud_port is None or public_port is None or cloud_port == public_port


def _is_cloud_forwarded_request(request: Request | None) -> bool:
    if request is None:
        return False
    return (request.headers.get("X-Wanpi-Cloud-Sync") or "").strip() == "1"


def _cloud_memory_url(product_name: str) -> str:
    return f"/api/batch-video/product-memory?product_name={quote(product_name or '')}"


def _absolute_cloud_file_url(url: str, cloud_url: str) -> str:
    value = str(url or "")
    if not value or value.startswith(("http://", "https://", "data:")):
        return value
    if value.startswith(("/api/files/", "/public-files/")):
        return f"{cloud_url}{value}"
    return value


def _rewrite_memory_file_urls_for_cloud(memory: dict[str, Any], cloud_url: str) -> dict[str, Any]:
    if not isinstance(memory, dict) or not cloud_url:
        return memory

    def rewrite(value):
        if isinstance(value, str):
            return _absolute_cloud_file_url(value, cloud_url)
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value

    return rewrite(memory)


def _collect_memory_local_file_paths(memory: dict[str, Any]) -> list[Path]:
    paths: set[Path] = set()

    def collect(value):
        if isinstance(value, str):
            try:
                local_path = deps.get_local_file_path_from_url(value)
            except Exception:
                local_path = None
            if local_path and local_path.is_file():
                paths.add(Path(local_path))
            return
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                collect(item)

    collect(memory)
    return sorted(paths, key=lambda path: str(path))


async def _upload_cloud_memory_files(memory: dict[str, Any], cloud_url: str, cloud_token: str) -> int:
    client = deps.http_client
    if client is None or not cloud_url or not cloud_token:
        return 0
    uploaded = 0
    for path in _collect_memory_local_file_paths(memory):
        try:
            with path.open("rb") as file_obj:
                resp = await client.post(
                    f"{cloud_url}/api/sync/push-file",
                    headers={
                        "Authorization": f"Bearer {cloud_token}",
                        "X-Wanpi-Cloud-Sync": "1",
                    },
                    files={"file": (path.name, file_obj, "application/octet-stream")},
                    timeout=120,
                )
            if 200 <= resp.status_code < 300:
                uploaded += 1
        except Exception:
            continue
    return uploaded


async def _fetch_cloud_product_memory(product_name: str, request: Request | None = None) -> dict[str, Any] | None:
    if _is_cloud_forwarded_request(request):
        return None
    cloud_url, cloud_token = _cloud_sync_config()
    if not cloud_url or not cloud_token or _is_self_cloud_url(cloud_url):
        return None
    try:
        client = deps.http_client
        if client is None:
            return None
        resp = await client.get(
            f"{cloud_url}{_cloud_memory_url(product_name)}",
            headers={
                "Authorization": f"Bearer {cloud_token}",
                "X-Wanpi-Cloud-Sync": "1",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        data = resp.json() if resp.content else {}
        memory = data.get("memory") if isinstance(data, dict) else None
        return memory if isinstance(memory, dict) else None
    except Exception:
        return None


async def _push_cloud_product_memory(product_name: str, memory: dict[str, Any], request: Request | None = None) -> bool:
    if _is_cloud_forwarded_request(request):
        return False
    cloud_url, cloud_token = _cloud_sync_config()
    if not cloud_url or not cloud_token or _is_self_cloud_url(cloud_url):
        return False
    try:
        client = deps.http_client
        if client is None:
            return False
        await _upload_cloud_memory_files(memory, cloud_url, cloud_token)
        resp = await client.put(
            f"{cloud_url}/api/batch-video/product-memory",
            headers={
                "Authorization": f"Bearer {cloud_token}",
                "X-Wanpi-Cloud-Sync": "1",
                "Content-Type": "application/json",
            },
            json={"product_name": product_name, "memory": memory},
            timeout=20,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def _load_product_memories() -> dict[str, Any]:
    raw = db.get_user_setting(PRODUCT_MEMORY_SETTING_KEY, "")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_product_memories(memories: dict[str, Any]) -> None:
    items = [
        (key, value)
        for key, value in (memories or {}).items()
        if key and isinstance(value, dict)
    ]
    items.sort(key=lambda item: int(item[1].get("updatedAt") or 0), reverse=True)
    trimmed = dict(items[:PRODUCT_MEMORY_LIMIT])
    db.set_user_setting(
        PRODUCT_MEMORY_SETTING_KEY,
        json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")),
    )


def _normalize_product_memory(raw: dict[str, Any], product_name: str) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    product = source.get("product") if isinstance(source.get("product"), dict) else {}
    product = dict(product)
    product["name"] = _clean_text(product.get("name") or product_name, 100)
    selling_points = source.get("sellingPoints") or source.get("selling_points") or []
    if not isinstance(selling_points, list):
        selling_points = []
    updated_at = int(source.get("updatedAt") or source.get("updated_at") or datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "productName": product["name"],
        "product": product,
        "liveVideo": source.get("liveVideo") or source.get("live_video") or None,
        "transcript": str(source.get("transcript") or "")[:200000],
        "manualSellingPoints": str(source.get("manualSellingPoints") or source.get("manual_selling_points") or "")[:50000],
        "sellingPoints": [point for point in selling_points[:80] if isinstance(point, dict)],
        "updatedAt": updated_at,
    }


def _setting_value(*keys: str) -> str:
    for key in keys:
        value = ""
        try:
            value = db.get_user_setting(key, "")
        except Exception:
            value = ""
        if not value:
            try:
                value = deps.settings_manager.get(key, "") or ""
            except Exception:
                value = ""
        if value:
            return str(value).strip()
    return ""


def _asr_config_status() -> dict[str, Any]:
    api_key = _setting_value(*ASR_API_KEY_FIELD["setting_keys"]) or os.environ.get(ASR_API_KEY_FIELD["env"], "")
    configured = bool(api_key)
    missing_fields = [] if configured else [
        {
            "id": ASR_API_KEY_FIELD["id"],
            "label": ASR_API_KEY_FIELD["label"],
            "setting_key": ASR_API_KEY_FIELD["setting_keys"][-1],
            "workspace_setting_key": ASR_API_KEY_FIELD["setting_keys"][0],
            "env": ASR_API_KEY_FIELD["env"],
        }
    ]
    return {
        "id": "volcengine_streaming_asr_2_0",
        "name": "豆包语音流式语音识别",
        "available": configured,
        "configured": configured,
        "configured_keys": ["api_key"] if api_key else [],
        "auth_mode": "doubao_speech_api_key" if api_key else "",
        "missing_fields": missing_fields,
        "settings_path": "系统设置 > ApiKey 设置 > 直播转写 / 语音识别",
        "workspace_settings_path": "电商素材 API 设置 > 豆包语音 API Key",
        "config_required": [
            "doubao_speech_api_key / game_doubao_speech_api_key",
        ],
        "message": "豆包语音 API Key 已配置，可直接调用豆包大模型流式语音识别 2.0。" if configured else "豆包语音 API Key 尚未配置，请先填写 API Key 管理页里创建的 Key。",
    }


def _ark_api_key() -> str:
    group_value = deps.get_group_api_key("ark_api_key")
    if group_value:
        return group_value
    candidates = ("game_ark_api_key", "ark_api_key", "game_jimeng_api_key", "jimeng_api_key")
    value = _setting_value(*candidates)
    if value:
        return value
    for env in ("GAME_ARK_API_KEY", "ARK_API_KEY", "GAME_JIMENG_API_KEY", "JIMENG_API_KEY"):
        value = (os.environ.get(env, "") or "").strip()
        if value:
            return value
    return ""


async def _ark_chat_completion(prompt: str, *, model: str = ARK_MODEL_ID, max_tokens: int = 2400) -> str:
    api_key = _ark_api_key()
    if not api_key:
        raise RuntimeError("ARK API Key 未配置，请先在 API 设置里填写火山引擎 ARK Key。")
    payload = {
        "model": model or ARK_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            ARK_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        try:
            err = resp.json()
            message = err.get("error", {}).get("message") or err.get("message") or resp.text
        except Exception:
            message = resp.text
        raise RuntimeError(f"豆包 Seed 2.0 Pro 请求失败：{message[:300]}")
    data = resp.json()
    return str((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def _split_manual_points(points: list[str]) -> list[str]:
    items: list[str] = []
    for item in points or []:
        for line in re.split(r"[\n；;]+", item or ""):
            line = _clean_text(line, 120)
            if line:
                items.append(line)
    return items


def _transcript_snippets(text: str) -> list[str]:
    source = re.sub(r"\s+", " ", (text or "").strip())
    if not source:
        return []
    parts = re.split(r"[。！？!?；;\n]+", source)
    snippets = [_clean_text(part, 120) for part in parts if _clean_text(part, 120)]
    return snippets[:8]


def _fallback_selling_points(product: ProductInput, transcript_text: str) -> list[dict[str, str]]:
    name = _clean_text(product.name, 80) or "产品"
    snippets = _transcript_snippets(transcript_text)
    base = [
        {
            "title": f"{name}核心卖点",
            "description": f"围绕{name}的主要使用价值做短视频开场，突出用户第一眼能理解的好处。",
            "evidence": snippets[0] if snippets else "",
            "source": "local_draft",
        },
        {
            "title": "场景化痛点",
            "description": "把直播口播中的高频问题转成真实使用场景，让画面先给出需求再给出产品。",
            "evidence": snippets[1] if len(snippets) > 1 else "",
            "source": "local_draft",
        },
        {
            "title": "细节与质感",
            "description": "用产品近景、材质、功能细节建立信任感，适合作为分镜图和视频中段。",
            "evidence": snippets[2] if len(snippets) > 2 else "",
            "source": "local_draft",
        },
    ]
    if product.description:
        base[0]["evidence"] = _clean_text(product.description, 140)
    return base


def _selling_points_prompt(product: ProductInput, transcript_text: str) -> str:
    name = _clean_text(product.name, 80) or "未命名产品"
    category = _clean_text(product.category, 80) or "电商产品"
    description = _clean_text(product.description, 500)
    transcript = (transcript_text or "").strip()
    if len(transcript) > 12000:
        transcript = transcript[:12000] + "\n[后续转写过长已截断，请基于已给内容提炼。]"
    return f"""
你是资深电商短视频卖点策划，擅长从直播口播转写中提炼可以直接用于商品视频的卖点。

产品名称：{name}
产品类目：{category}
产品补充信息：{description or "无"}

直播转写文本：
{transcript}

请基于直播文本提炼 5-8 个高质量产品卖点，要求：
1. 必须优先来自直播文本，不要凭空编造。
2. 每个卖点要适合后续生成短视频分镜。
3. 标题短、具体、有商品感，不要写“核心卖点”“场景化痛点”这种模板词。
4. description 解释这个卖点对消费者的价值。
5. evidence 摘取或概括直播文本里的依据。
6. scene_angle 写成后续视频画面可拍/可生成的呈现角度。
7. 如果直播文本信息不足，只输出能确定的卖点。

只返回严格 JSON object，不要 Markdown，不要解释。格式：
{{
  "selling_points": [
    {{
      "title": "卖点标题",
      "description": "消费者价值说明",
      "evidence": "直播文本依据",
      "scene_angle": "视频画面呈现角度"
    }}
  ]
}}
""".strip()


def _normalize_model_selling_points(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, list):
        raw_points = payload
    elif isinstance(payload, dict):
        raw_points = (
            payload.get("selling_points")
            or payload.get("sellingPoints")
            or payload.get("points")
            or payload.get("卖点")
        )
    else:
        return []
    if not isinstance(raw_points, list):
        return []
    points: list[dict[str, str]] = []
    for item in raw_points:
        if isinstance(item, str):
            title = _clean_text(item, 80)
            if title:
                points.append({"title": title, "description": title, "evidence": "", "source": "doubao_seed_2_0_pro"})
            continue
        if not isinstance(item, dict):
            continue
        title = _clean_text(str(item.get("title") or item.get("name") or ""), 80)
        description = _clean_text(str(item.get("description") or item.get("value") or ""), 220)
        evidence = _clean_text(str(item.get("evidence") or item.get("quote") or ""), 220)
        scene_angle = _clean_text(str(item.get("scene_angle") or item.get("scene") or ""), 180)
        if not title:
            continue
        if scene_angle and scene_angle not in description:
            description = f"{description} 视频呈现：{scene_angle}" if description else f"视频呈现：{scene_angle}"
        points.append(
            {
                "title": title,
                "description": description or title,
                "evidence": evidence,
                "source": "doubao_seed_2_0_pro",
            }
        )
    return points[:8]


def _normalize_text_selling_points(text: str) -> list[dict[str, str]]:
    raw = re.sub(r"```[\s\S]*?```", "", text or "").strip()
    if not raw:
        return []

    object_chunks = re.findall(r"\{[^{}]*(?:title|标题|卖点)[^{}]*\}", raw, flags=re.IGNORECASE)
    object_points: list[dict[str, str]] = []
    for chunk in object_chunks:
        title_match = re.search(r'["“”]?(?:title|标题|卖点)["“”]?\s*[:：]\s*["“”]?([^",，\n}]+)', chunk, re.IGNORECASE)
        if not title_match:
            continue
        description_match = re.search(r'["“”]?(?:description|描述|说明|价值)["“”]?\s*[:：]\s*["“”]?([^"\n}]+)', chunk, re.IGNORECASE)
        evidence_match = re.search(r'["“”]?(?:evidence|依据|证据)["“”]?\s*[:：]\s*["“”]?([^"\n}]+)', chunk, re.IGNORECASE)
        title = _clean_text(title_match.group(1), 80)
        if not title:
            continue
        object_points.append({
            "title": title,
            "description": _clean_text(description_match.group(1), 220) if description_match else title,
            "evidence": _clean_text(evidence_match.group(1), 220) if evidence_match else "",
            "source": "doubao_seed_2_0_pro",
        })
    if object_points:
        return object_points[:8]

    points: list[dict[str, str]] = []
    for line in re.split(r"[\n\r]+", raw):
        line = re.sub(r"^\s*(?:[-*•]|[0-9一二三四五六七八九十]+[\.、\)]?)\s*", "", line).strip()
        line = re.sub(r"^(?:卖点|标题)\s*[0-9一二三四五六七八九十]*\s*[:：]\s*", "", line).strip()
        if not line or len(line) < 4:
            continue
        if any(marker in line.lower() for marker in ("selling_points", "json", "```")):
            continue
        if line.startswith(("{", "}", "[", "]")):
            continue
        if re.search(r"[:：|-]", line):
            title, rest = re.split(r"[:：|-]", line, maxsplit=1)
        else:
            title, rest = line, ""
        title = _clean_text(title, 80)
        description = _clean_text(rest or line, 220)
        if title and title not in {point["title"] for point in points}:
            points.append({
                "title": title,
                "description": description or title,
                "evidence": "",
                "source": "doubao_seed_2_0_pro",
            })
        if len(points) >= 8:
            break
    return points


def _sanitize_storyboard_prompt_text(text: str) -> str:
    cleaned = str(text or "")
    stale_blocks = [
        r"【声音规则】[^。]*。?",
        r"声音规则[:：][^。]*。?",
        r"【旁白】[\s\S]*?(?=【|$)",
        r"旁白(?:内容)?[:：]\s*[“\"']?[^。；\n”\"']+[”\"']?(?:[。；\n]|$)",
        r"【声音限制】[^。]*(?:背景音乐|BGM|bgm|配乐|音乐节奏|轻音乐|鼓点|现场音效|旁白)[^。]*。?",
        r"【声音限制】不要生成[^。]*(?:旁白|配音|语音音轨)[^。]*。?",
        r"不要生成[^。；]*(?:旁白|配音|语音音轨)[^。；]*(?:[。；]|$)",
        r"不要出现[^。；]*(?:说话的人|主播|口播)[^。；]*(?:[。；]|$)",
        r"只保留真实现场环境音[^。；]*(?:[。；]|$)",
        r"加入一条[^。；\n]*(?:旁白|配音|口播|人声)[^。；\n]*(?:[。；\n]|$)",
        r"声音只能由真实现场音效和一条普通话广告旁白组成[^。；\n]*(?:[。；\n]|$)",
        r"不要(?:生成|出现|加入|使用|有)?[^。；]*(?:背景音乐|BGM|bgm|配乐|音乐节奏|轻音乐|鼓点)[^。；]*(?:[。；]|$)",
    ]
    for pattern in stale_blocks:
        cleaned = re.sub(pattern, "", cleaned)
    replacements = {
        "不要出现主播": "",
        "不出现主播": "",
        "禁止主播": "",
        "无人物主播": "",
        "主播": "产品运动动作",
        "配音": "",
        "人声解说": "",
        "口播": "",
        "主播声音": "",
        "直播间": "户外自然环境",
        "直播带货": "户外品牌广告",
        "带货": "产品广告",
        "真人讲解": "产品细节展示",
        "手机下单": "产品细节定格",
        "购物车": "产品细节",
        "购物界面": "产品细节",
        "购买按钮": "产品细节",
        "购买画面": "产品定格画面",
        "点击下单": "产品定格",
        "价格促销": "卖点",
        "促销文案": "卖点",
        "促销": "卖点",
        "价格": "卖点",
        "CTA": "卖点",
        "低频户外广告鼓点": "现场音效",
        "低频鼓点": "现场音效",
        "音乐节奏": "现场音效",
        "轻音乐节奏": "现场音效",
        "背景音乐": "现场音效",
        "轻音乐": "现场音效",
        "配乐": "现场音效",
        "BGM": "现场音效",
        "bgm": "现场音效",
        "鼓点": "现场音效",
        "防滑声": "脚步与地面摩擦声",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


_STORYBOARD_LEGACY_TERMS = (
    "新旧",
    "旧鞋",
    "旧鞋底",
    "磨损差异",
    "并排摆放",
    "并排",
    "完全没有移位",
    "湿滑瓷砖",
    "瓷砖",
    "实验室",
    "硬测评",
    "测评",
    "打滑",
    "防滑挑战",
    "耐磨挑战",
    "功能挑战",
    "功能测试",
    "测试画面",
    "证明画面",
    "证据画面",
    "痛点反转",
    "反差画面",
)


def _legacy_neutral_text(text: str) -> str:
    value = str(text or "")
    return re.sub(
        r"(?:不|不要|不能|禁止|避免|杜绝|拒绝)[^。；\n]*(?:对比|反差|痛点|证明|证据|测试|挑战|旧鞋|新旧|瓷砖|实验室|测评)[^。；\n]*(?:[。；\n]|$)",
        " ",
        value,
    )


def _contains_legacy_storyboard_logic(text: str) -> bool:
    neutral = _legacy_neutral_text(text)
    return any(term in neutral for term in _STORYBOARD_LEGACY_TERMS)


def _clean_model_storyboard_text(text: str, max_length: int) -> str:
    cleaned = _clean_text(_sanitize_storyboard_prompt_text(text), max_length)
    if _contains_legacy_storyboard_logic(cleaned):
        return ""
    return cleaned


def _normalize_video_prompt_sound(text: str) -> str:
    cleaned = _sanitize_storyboard_prompt_text(text)
    sound_rule = "【声音规则】生成单段视频时不要旁白、配音、人声或口播；不要唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点；只保留真实现场音效，例如脚步声、风声、水花声、材质与地面轻微摩擦声。"
    if cleaned and sound_rule not in cleaned:
        cleaned = f"{cleaned} {sound_rule}"
    return _clean_text(cleaned, 1400)


WEARING_ACTION_RE = re.compile(r"(脚步|行走|奔跑|踩水|跨步|转向|跟拍|贴地|穿越|运动状态|步伐|鞋底|鞋身贴合)")


def _requires_wearing_scene(*texts: str) -> bool:
    return any(WEARING_ACTION_RE.search(text or "") for text in texts)


def _ensure_wearing_image_prompt(image_prompt: str, *context_texts: str) -> str:
    cleaned = _clean_text(image_prompt, 1200)
    if not cleaned or not _requires_wearing_scene(cleaned, *context_texts):
        return cleaned
    if "穿着" in cleaned and ("真人" in cleaned or "脚部" in cleaned or "下肢" in cleaned):
        return cleaned
    wearing_rule = "【穿着状态】该分镜包含脚步/运动/行进动作，首帧图片必须有人穿着当前产品，画面出现真人脚部或下肢与产品的真实穿着关系；不要生成空鞋、孤立产品或静物摆拍。"
    return _clean_text(f"{cleaned} {wearing_rule}", 1200)


def _parse_selling_points_json(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence_match:
        candidates.append(fence_match.group(1).strip())
    object_start = raw.find("{")
    object_end = raw.rfind("}") + 1
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw[object_start:object_end])
    array_start = raw.find("[")
    array_end = raw.rfind("]") + 1
    if array_start >= 0 and array_end > array_start:
        candidates.append(raw[array_start:array_end])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return deps.extract_json(raw)


async def _generate_model_selling_points(req: SellingPointsRequest) -> list[dict[str, str]]:
    transcript = (req.transcript_text or "").strip()
    if not transcript:
        return []
    model = (req.language_model or ARK_MODEL_ID).strip() or ARK_MODEL_ID
    prompt = _selling_points_prompt(req.product, transcript)
    text = await _ark_chat_completion(prompt, model=model, max_tokens=2400)
    parsed = _parse_selling_points_json(text)
    points = _normalize_model_selling_points(parsed)
    if not points:
        points = _normalize_text_selling_points(text)
    if not points:
        raise RuntimeError("豆包 Seed 2.0 Pro 未返回可解析的卖点 JSON。")
    return points


def _caption_text(text: str, fallback: str) -> str:
    value = _clean_text(text or fallback, 24)
    value = re.sub(r"[，。；、,.!?！？:：\"“”'‘’\s]", "", value)
    return value[:14] or fallback


def _storyboard_seed(req: StoryboardPlanRequest) -> int:
    seed_source = (req.creative_seed or "").strip() or uuid.uuid4().hex
    raw = f"{seed_source}|{req.regenerate_index}"
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def _parse_storyboard_creative_brief(text: str) -> tuple[int | None, int | None]:
    value = text or ""
    count_match = re.search(r"(\d{1,2})\s*(?:段|条|个)\s*(?:分镜|镜头|视频|片段)?", value)
    if not count_match:
        count_match = re.search(r"(?:分镜|镜头|视频|片段)\s*(\d{1,2})\s*(?:段|条|个)?", value)
    duration_match = re.search(r"(\d{1,2})\s*(?:s|S|秒)", value)
    scene_count = int(count_match.group(1)) if count_match else None
    duration = int(duration_match.group(1)) if duration_match else None
    return scene_count, duration


def _creative_route(seed: int) -> dict[str, str]:
    routes = [
        {
            "name": "雨后溪谷大片",
            "visual": "雨后溪谷、湿石反光、逆光水雾、低机位穿越、水花慢动作和产品英雄特写",
            "tempo": "用贴地跟拍、自然脚步和水光细节营造高级户外运动广告感",
        },
        {
            "name": "山路穿越大片",
            "visual": "碎石山路、林间逆光、尘土与水珠飞溅、跟拍奔走和压迫感远景",
            "tempo": "用长镜头行进、低机位跟拍和材质微距形成高级运动节奏",
        },
        {
            "name": "雨后岩壁硬核片",
            "visual": "雨后岩壁、深色湿润质感、斜坡压力、水滴微距、鞋底纹理和石面摩擦特写",
            "tempo": "用湿润质感、转向动作和慢动作水滴呈现硬朗户外气质",
        },
        {
            "name": "清晨出发大片",
            "visual": "清晨自然光、溪边营地、木栈道、浅水边出发、金色逆光和产品定格",
            "tempo": "更像生活方式品牌广告，卖点藏在真实出行动作里",
        },
        {
            "name": "微距质感大片",
            "visual": "鞋面网眼、扣具、鞋底纹路、水滴挂珠、材质反光和极近景结构扫描",
            "tempo": "用电影级微距、扫光和材质声音把卖点拍得高级、可信、可感知",
        },
    ]
    return routes[seed % len(routes)]


def _selling_point_ad_drama(title: str, detail: str = "") -> dict[str, str]:
    text = f"{title} {detail}"
    cases = [
        (
            ("防滑", "不打滑", "抓地", "止滑", "湿滑"),
            {
                "scene": "雨后溪谷和湿石反光，浅水从石缝间流过，画面干净但有真实户外质感",
                "action": "脚步贴着湿石自然向前，鞋底压过水膜，水花轻轻向两侧散开",
                "detail": "低机位掠过鞋底纹路、湿石水珠和鞋身轮廓，抓地感通过脚步稳定性自然出现",
                "ending": "脚步停在逆光水面边缘，产品轮廓清晰，像户外品牌主视觉",
                "voiceover": "湿滑路面，也能从容向前。",
            },
        ),
        (
            ("防水", "拒水", "涉水", "泼水", "速干"),
            {
                "scene": "浅溪、雨后木栈道或潮湿山路中，逆光水雾和水珠营造清爽户外氛围",
                "action": "产品随着脚步轻快穿过浅水，水珠沿材质表面滑落，动作干净利落",
                "detail": "微距扫过水珠滚落、包边、接缝和材质反光，防水感自然藏在质感里",
                "ending": "脚步离开水面，水珠在逆光里飞散，产品保持清晰有型",
                "voiceover": "穿过潮湿，也保持清爽。",
            },
        ),
        (
            ("透气", "干爽", "排汗", "不闷", "通风"),
            {
                "scene": "清晨林道、山间微风和柔和逆光，空气感充足，画面轻盈干净",
                "action": "脚步保持轻快节奏，镜头跟随鞋面掠过风和光，运动状态自然舒展",
                "detail": "浅景深微距扫过网眼、织物层次和空气流动感，干爽透气通过画面质感呈现",
                "ending": "人物继续向前，画面明亮通透，产品在步伐里显得轻松",
                "voiceover": "让每一步，都更轻快。",
            },
        ),
        (
            ("缓震", "减震", "回弹", "软弹", "舒适"),
            {
                "scene": "碎石路、木栈道或山径坡面，晨光从侧后方打出运动轮廓",
                "action": "脚步落地再抬起，动作连贯有弹性，水珠或细尘随落点轻轻弹开",
                "detail": "镜头贴近中底、鞋跟落点和身体重心变化，用慢动作表现柔和回弹",
                "ending": "连续步伐向前延伸，产品和身体动作保持轻盈节奏",
                "voiceover": "落地轻一点，走得更远一点。",
            },
        ),
        (
            ("支撑", "稳定", "包裹", "护踝", "不崴"),
            {
                "scene": "山路转弯、斜坡碎石和林间逆光形成运动户外氛围",
                "action": "人物自然转向、跨步或停顿，鞋身贴合脚步，动作稳定而不僵硬",
                "detail": "微距扫过鞋帮、后跟、包边和包裹结构，稳定感从动作和轮廓里出来",
                "ending": "脚步在斜坡边缘稳稳停住，画面高级克制，不做夸张测试",
                "voiceover": "每一次转向，都稳稳跟上。",
            },
        ),
        (
            ("耐磨", "抗磨", "耐穿", "耐用", "结实"),
            {
                "scene": "粗粝山路、碎石、尘土和低角度自然光，画面硬朗但不测试化",
                "action": "产品从碎石和山路表面掠过，脚步有速度，尘土轻轻被带起",
                "detail": "镜头扫过鞋底纹路、包边、缝线和材质边缘，让耐用感藏在细节质感里",
                "ending": "产品停在山路光影中，轮廓清晰，像刚完成一次户外行进",
                "voiceover": "路走得越远，细节越可靠。",
            },
        ),
        (
            ("轻量", "轻便", "不累", "轻"),
            {
                "scene": "开阔山野、清晨风和明亮天空，画面有轻快的出发感",
                "action": "脚步快速掠过浅水、木栈道或碎石，抬脚动作轻盈自然",
                "detail": "慢动作呈现鞋身线条、薄厚比例和脚步离地瞬间，轻量感通过节奏体现",
                "ending": "镜头拉出开阔空间，产品随步伐向前，画面清爽有速度",
                "voiceover": "轻装出发，步伐自然更远。",
            },
        ),
    ]
    for keywords, drama in cases:
        if any(keyword in text for keyword in keywords):
            return drama
    return {
        "scene": f"真实运动户外环境中，自然光、风、脚步和空间感围绕“{title}”形成高级广告氛围",
        "action": f"产品跟随自然运动动作进入画面，让“{title}”在步伐、姿态和环境互动里被感知",
        "ending": "动作结束后产品稳稳定格，质感、结构和轮廓都像品牌广告主视觉",
        "detail": "关键材质、结构、纹理和运动细节用电影级微距自然带出",
        "voiceover": f"{title}，随每一步自然发生。",
    }


def _timeline_items(raw: Any, *, name: str, title: str, hook: str, detail: str, duration: int, drama: dict[str, str] | None = None) -> list[str]:
    items: list[str] = []
    if isinstance(raw, list):
        for item in raw[:4]:
            raw_desc = ""
            if isinstance(item, dict):
                time_label = _clean_text(str(item.get("time") or item.get("range") or ""), 20)
                parts = [
                    item.get("shot") or item.get("景别"),
                    item.get("camera") or item.get("运镜"),
                    item.get("action") or item.get("动作"),
                    item.get("visual") or item.get("画面"),
                    item.get("effect") or item.get("效果"),
                ]
                raw_desc = "，".join(str(part) for part in parts if part)
                desc = _clean_model_storyboard_text(raw_desc, 260)
                if time_label and desc:
                    items.append(f"{time_label}：{desc}")
                elif desc:
                    items.append(desc)
            elif isinstance(item, str):
                raw_desc = item
                line = _clean_model_storyboard_text(item, 260)
                if line:
                    items.append(line)
            if raw_desc and _contains_legacy_storyboard_logic(raw_desc):
                items = []
                break
    if items:
        if duration >= 8:
            clean_items = [re.sub(r"^\s*[^：:]{1,24}[：:]\s*", "", item).strip() for item in items]
            continuous_scene = "；".join(part for part in clean_items if part) or f"{name}在户外动作场景中自然进入画面"
            return [
                f"0-{duration}秒：同一户外广告场景内连贯推进，{continuous_scene}；不要切换到第二个场景，镜头可通过推近、低机位跟随、景别变化和焦点转移自然带到产品英雄近景、材质微距或产品样式收束，结尾回到产品本身的样式、轮廓、材质和广告主视觉。",
            ]
        return items
    drama = drama or _selling_point_ad_drama(title, detail)
    return [
        f"0-{duration}秒：一个完整连贯的高级运动户外广告镜头，{drama['scene']}；镜头压低贴近地面，{name}自然进入画面，{drama['action']}，让“{title}”通过运动状态被感知；中后段在同一场景内自然推近到产品英雄近景或材质细节，{drama['detail']}；结尾回到产品本身的样式、轮廓、材质和广告主视觉，{drama['ending']}，画面干净、可做品牌主视觉定格。",
    ]


def _veo_storyboard_scene(
    product: ProductInput,
    *,
    index: int,
    beat_name: str,
    selling_point: str,
    hook: str,
    detail: str,
    aspect_ratio: str,
    duration: int,
    image_frame: str = "",
    timeline: Any = None,
    sound: str = "",
    voiceover: str = "",
    ending_frame: str = "",
    route: dict[str, str] | None = None,
) -> dict[str, str]:
    name = _clean_text(product.name, 80) or "产品"
    title = _clean_text(selling_point, 80) or f"卖点 {index + 1}"
    caption = _caption_text(hook, title)
    drama = _selling_point_ad_drama(title, detail)
    route = route or {"name": "雨后溪谷大片", "visual": "真实山溪、湿石、苔藓、浅水、逆光水雾和慢动作水花", "tempo": "运动感自然推进，卖点融进脚步、材质和光影"}
    frame = _clean_text(
        image_frame,
        320,
    ) or f"{beat_name}，{route['visual']}中，{name}以运动户外品牌片的英雄近景进入画面，卖点“{title}”通过脚步、材质、光影和环境互动自然被看见。"
    ending = _clean_text(
        ending_frame,
        220,
    ) or f"{drama['ending']}；{name}轮廓、材质和关键结构清晰，画面干净无文字，可衔接下一分镜。"
    sound_design = _clean_text(
        sound,
        180,
    ) or "现场音效：溪水声、脚步踩水声、轻微水花声、鞋底摩擦湿石声；不要背景音乐、BGM、配乐、音乐节奏或鼓点。"
    if _contains_legacy_storyboard_logic(sound_design):
        sound_design = "现场音效：脚步声、风声、浅水声、水花声、材质与地面轻微摩擦声；不要背景音乐、BGM、配乐、音乐节奏或鼓点。"
    voiceover_text = _clean_text(voiceover, 180) or drama["voiceover"]
    if _contains_legacy_storyboard_logic(voiceover_text):
        voiceover_text = drama["voiceover"]
    timeline_lines = _timeline_items(
        timeline,
        name=name,
        title=title,
        hook=caption,
        detail=detail,
        duration=duration,
        drama=drama,
    )
    image_prompt = "\n".join([
        "【用途】生成首帧图片 @图片1：竖屏户外产品广告大片的单张分镜图，作为后续视频生成首帧/视觉参考。",
        f"【参考】产品外观完全以@产品参考图为准，保持{name}的轮廓、结构、比例、材质、鞋面/鞋底/扣具/纹理等关键细节一致；外观细节不在文字里二次发挥。",
        f"【画幅】{aspect_ratio}，竖屏电影广告构图，产品是英雄主体，不是普通商品摆拍。",
        f"【创意路线】{route['name']}：{route['visual']}，{route['tempo']}。",
        f"【卖点气质】场景：{drama['scene']}；动作：{drama['action']}；细节：{drama['detail']}。",
        f"【镜头】{frame}",
        "【质感】电影级自然光、浅景深、湿石反光、逆光水雾、水滴、尘土或水花慢动作，真实户外鞋服品牌广告大片质感。",
        "【画面要求】不要生成字幕、文字、价格、促销词、按钮、水印或二维码；不要做对比、测评、实验化演示或硬性证明；用运动状态、产品动作、材质细节和光影表达卖点。",
        f"【结尾帧】{ending}",
    ])
    image_prompt = _ensure_wearing_image_prompt(image_prompt, frame, " ".join(timeline_lines), drama["action"], drama["scene"])
    video_prompt = "\n".join([
        f"【技术参数】{aspect_ratio}，{duration}秒，24fps，竖屏户外产品广告大片，电影级自然光，浅景深，真实现场质感。",
        f"【参考素材】@图片1为首帧、构图、场景、光线和动作起点，负责整段 {duration} 秒的同一广告场景；镜头可以在同一场景内自然推进到产品英雄近景、材质微距或产品样式镜头，但不能切到测试/测评/对比场景；@产品参考图只用于保持{name}外观、结构、比例、材质、鞋面/鞋底/扣具/纹理等关键细节一致，外观细节不在文字里二次发挥。",
        f"【创意路线】{route['name']}：{route['visual']}，{route['tempo']}。",
        f"【卖点表达】不要直白解释“{title}”，让它自然出现在“{drama['scene']}”里的运动动作、材质细节和户外光影中；画面要能承接后期旁白和字幕。",
        "【时间戳分镜】",
        *timeline_lines,
        "【镜头节奏】这是一段完整连贯的 8 秒单场景广告镜头；可以通过推近、低机位跟随、轻微横移、景别变化和焦点转移，从户外动作自然推进到产品英雄近景、材质微距或产品样式收束，结尾内容要回到产品本身的样式、轮廓、材质和广告主视觉。",
        f"【音效】{sound_design}；脚步、摩擦、水花、风声或材质声音要与画面动作同步。",
        "【声音限制】生成阶段不要旁白、配音、人声、口播、唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点，只保留真实现场音效。",
        f"【禁止项】全片不要出现任何字幕、屏幕文字、价格、促销词、按钮、水印、二维码；不要出现对比、测评、实验化演示、道具验证、硬性证明或测评感画面；不要出现说话的人、主播画面或直播带货口播；只用同一户外广告场景、产品细节和现场音效表现“{caption}”。",
        f"【结尾帧】{ending}",
    ])
    return {
        "id": f"scene_{uuid.uuid4().hex[:8]}",
        "title": f"{index + 1}. {beat_name}：{title}",
        "selling_point": title,
        "hook": caption,
        "image_prompt": image_prompt,
        "video_prompt": video_prompt,
        "voiceover_text": voiceover_text,
        "shot_notes": f"{beat_name}，约 {duration} 秒。参考产品图生成分镜图，再用分镜图作为 Veo 首帧。",
        "storyboard_image_url": "",
        "video_url": "",
    }


def _scene_templates(
    product: ProductInput,
    point: SellingPoint,
    index: int,
    aspect_ratio: str,
    duration: int,
    scene_count: int = DEFAULT_STORYBOARD_SCENE_COUNT,
    route: dict[str, str] | None = None,
) -> dict[str, str]:
    name = _clean_text(product.name, 80) or "产品"
    title = _clean_text(point.title, 80) or f"卖点 {index + 1}"
    detail = _clean_text(point.description or point.evidence, 180)
    product_lock_hint = " 产品完整形态已由产品详情表确认，必须保持同一产品结构、颜色、材质和比例，不要自行改款。" if product.detail_sheet_url else ""
    if scene_count == VEO_STORYBOARD_SCENE_COUNT:
        route_name = (route or {}).get("name", "")
        fallback_beats = {
            "山路穿越": [
                ("林间山路入场", "脚步进入清晨山路"),
                ("逆光英雄近景", f"{title}自然出现"),
                ("山路运动跟拍", f"{title}融进步伐"),
                ("山路细节定格", "风和脚步继续向前"),
            ],
            "雨后岩壁": [
                ("雨后岩面开场", "湿石水光映出脚步"),
                ("水滴英雄近景", f"{title}自然可感"),
                ("岩面运动跟拍", f"{title}藏在动作里"),
                ("纹理微距收束", "细节在水光里定格"),
            ],
            "清晨露营地": [
                ("溪边营地开场", "出门轻松上脚"),
                ("晨光产品近景", f"{title}清晰可见"),
                ("浅水步伐跟拍", f"{title}自然发挥"),
                ("露营定格收束", "通勤露营都好搭"),
            ],
            "极近微距": [
                ("材质微距开场", "细节一眼看清"),
                ("结构英雄近景", f"{title}看得见"),
                ("纹理光影扫过", f"{title}融入质感"),
                ("水滴定格收束", "质感细节拉满"),
            ],
        }
        beat_pool = fallback_beats.get(route_name, [
            ("溪流实测开场", "下水踩石走山路"),
            ("产品英雄近景", f"{title}看得见"),
            ("运动动作跟拍", f"{title}自然发挥"),
            ("细节定格收束", "户外出行更安心"),
        ])
    else:
        beat_pool = [
            ("山野氛围开场", f"用运动户外环境自然引出{name}"),
            ("产品运动近景", f"完整展示{name}外观、比例和核心结构"),
            ("卖点自然融入", f"让“{title}”出现在真实脚步和动作里"),
            ("材质光影细节", f"用材质、结构、纹理和光影承接“{title}”"),
            ("户外行动片段", f"把{name}放入真实户外动作，画面高级克制"),
            ("品牌定格收束", f"回到{name}干净、有力量的广告主视觉"),
        ]
    beat_name, hook = beat_pool[index % len(beat_pool)]
    if scene_count == VEO_STORYBOARD_SCENE_COUNT:
        return _veo_storyboard_scene(
            product,
            index=index,
            beat_name=beat_name,
            selling_point=title,
            hook=hook,
            detail=detail,
            aspect_ratio=aspect_ratio,
            duration=duration,
            route=route,
        )
    drama = _selling_point_ad_drama(title, detail)
    scene_style = "真实产品广告大片，电影级户外/生活场景，产品为英雄主体，画面适合手机竖屏投放"
    if aspect_ratio == "16:9":
        scene_style = "真实产品广告大片横版视频，电影级户外/生活场景，产品为英雄主体，画面适合横版投放"
    image_prompt = (
        f"{scene_style}。分镜阶段：{beat_name}。产品：{name}。对应卖点：{title}。"
        f"场景：{drama['scene']}；动作：{drama['action']}。"
        f"画面要求：产品清晰可见，前景有真实户外运动状态或材质细节，电影级自然光，构图有冲击力，"
        f"保留品牌广告大片质感，不出现多余文字。{product_lock_hint}"
    )
    if detail:
        image_prompt += f" 参考信息：{detail}。"
    image_prompt = _ensure_wearing_image_prompt(image_prompt, drama["action"], drama["scene"], beat_name, title)
    video_prompt = (
        f"{duration}秒左右产品广告大片分镜，阶段：{beat_name}。{hook}。"
        f"镜头必须把卖点“{title}”融入高级运动户外画面：{drama['scene']}；{drama['action']}；最后用{drama['detail']}承接后期字幕。"
        f"保持同一产品外观与比例，画面真实、节奏有电影广告推进感，适合和其他分镜拼成一条完整品牌广告片。"
        "生成阶段不要旁白、配音、人声或口播；不要唱歌、吟唱、Rap、歌词化或音乐化念白；声音只保留真实现场音效，不要背景音乐、BGM、配乐、音乐节奏或鼓点。"
    )
    if detail:
        video_prompt += f" 卖点补充：{detail}。"
    return {
        "id": f"scene_{uuid.uuid4().hex[:8]}",
        "title": f"{index + 1}. {beat_name}：{title}",
        "selling_point": title,
        "hook": hook,
        "image_prompt": image_prompt,
        "video_prompt": video_prompt,
        "voiceover_text": drama["voiceover"],
        "shot_notes": f"{beat_name}，约 {duration} 秒，服务卖点：{title}。",
        "storyboard_image_url": "",
        "video_url": "",
    }


def _storyboard_prompt(
    product: ProductInput,
    selling_points: list[SellingPoint],
    *,
    aspect_ratio: str,
    duration: int,
    scene_count: int,
    route: dict[str, str] | None = None,
    storyboard_reference_count: int = 0,
    creative_brief: str = "",
    creative_seed: str = "",
    regenerate_index: int = 0,
) -> str:
    name = _clean_text(product.name, 80) or "未命名产品"
    category = _clean_text(product.category, 80) or "电商产品"
    description = _clean_text(product.description, 500)
    creative_brief_text = _clean_text(creative_brief, 600)
    points_text = "\n".join(
        f"{index + 1}. {point.title}：{_clean_text(point.description or point.evidence, 260)}"
        for index, point in enumerate(selling_points)
    )
    detail_sheet_note = "已有产品完整形态详情表，所有分镜必须保持同一个产品的结构、颜色、材质、比例和细节。" if product.detail_sheet_url else "如果有产品参考图，所有分镜必须保持同一个产品的结构、颜色、材质、比例和细节。"
    storyboard_reference_note = (
        f"用户额外上传了 {storyboard_reference_count} 张分镜/场景参考图。写 image_frame、timeline 和镜头质感时要参考这些图的构图、环境、光线、机位、动作节奏和广告质感；但产品外观仍以产品参考图为准。"
        if storyboard_reference_count
        else "用户未额外上传分镜/场景参考图，请根据产品卖点和创意路线自行构思画面。"
    )
    if scene_count == VEO_STORYBOARD_SCENE_COUNT and duration == VEO_STORYBOARD_DURATION:
        route = route or {"name": "溪流广告大片", "visual": "溪流浅水、湿石、苔藓、水花慢动作、低机位跟拍", "tempo": "真实户外广告片，动作自然，卖点融进画面"}
        seed_text = creative_seed or uuid.uuid4().hex
        return f"""
你是户外装备品牌广告导演、电影广告摄影指导和 Veo 3.1 视频提示词专家。请根据产品卖点，先构思一条有“广告大片感”的竖屏产品广告脚本，再拆成 {scene_count} 个适合 Veo 3.1 生成的分镜。

产品名称：{name}
产品类目：{category}
产品补充信息：{description or "无"}
画幅：{aspect_ratio}
单个分镜时长：约 {duration} 秒
产品一致性要求：{detail_sheet_note}
分镜参考图要求：{storyboard_reference_note}
本次创意路线：{route["name"]} - {route["visual"]}；节奏：{route["tempo"]}
本次重生成编号：{regenerate_index}
创意随机种子：{seed_text}
用户创作需求：{creative_brief_text or f"请根据上面的卖点，为我写 {scene_count} 段 {duration}s 的电商广告视频；分镜图片和视频提示词都按 Seedance 风格生成。"}

已整理/已编辑的卖点：
{points_text or "无明确卖点，请基于产品信息生成保守的产品广告片卖点。"}

生成要求：
1. 这是户外品牌广告大片，单段视频生成提示词里不要旁白、配音、人声或口播；voiceover 字段只给后期统一配音和字幕使用。
2. 不要写对比、痛点反转、测评式演示、道具验证、实验化场景或硬性证明；只拍当前这双鞋在高级户外广告场景中的状态，每个卖点都要通过运动动作、户外环境、材质细节和光影自然体现。
3. 视觉参考方向：偏运动、偏户外的高级品牌广告片，溪流/湿石/苔藓/山路/浅水/雨后逆光/尘土/水雾，自然光，低机位英雄跟拍，水花慢动作，产品微距，鞋底/纹理/材质特写，画面真实但品牌广告质感强。
4. 先在脑中完成广告脚本：自然户外氛围开场、产品跟随脚步进入、运动动作展开、材质光影细节、品牌主视觉收束；输出时只输出分镜 JSON。
5. 4 个分镜必须分别承担：山野氛围开场、产品运动近景、动作中的卖点呈现、品牌质感收束。
6. 每个分镜约 {duration} 秒，适合 Veo 3.1 直接生成一段高质量 AI 视频，再拼成一条完整广告大片。
7. 每个分镜必须围绕卖点，但卖点只作为画面气质和动作设计的方向：防滑可以是湿石上自然稳定的步伐；防水可以是水珠从材质表面滑落；透气可以是清晨风和轻快脚步；支撑可以是山路转向时的稳定姿态；耐磨可以是碎石路上的运动质感。所有表达都只出现当前产品，不出现旧产品、对照物或测试道具。
8. 不要直接输出散文式 image_prompt/video_prompt；请输出结构字段，后端会拼成最终提示词。
9. image_frame 写首帧图片 @图片1 的画面：产品英雄主体、景别、构图、户外环境、电影光线、水花/湿石/苔藓/尘土/水雾/清晨风等质感，必须能和视频开头自然衔接；不要在文字里二次发挥鞋身外观细节，产品外观由参考图决定。
10. 如果 timeline/video_prompt 要求人穿着产品运动、脚步、行走、奔跑、踩水、转向、贴地跟拍或户外行进，那么 image_frame 也必须明确写真人脚部/下肢穿着当前产品，保持真实穿着关系；不要写成空鞋、孤立产品或静物摆拍。
11. 每一段 8 秒分镜就是一个完整连贯的单场景广告镜头。timeline 只写一条 0-8秒，或写同一场景内的镜头推进，但必须保持同一地点、同一光线和同一产品动作逻辑；结尾内容要回到产品本身的样式、轮廓、材质和广告主视觉，不要写成测试/测评/对比场景。
12. sound 只写真实现场音效，并与画面动作对应，例如溪水声、脚步踩水声、水花声、鞋底摩擦湿石声、风声、布料摩擦声；不要写背景音乐、BGM、配乐、音乐节奏或鼓点。
13. voiceover 写一句最终合成时使用的普通话广告旁白，12-24字，用引号包裹时也成立，要像品牌广告片文案，由同一种干净克制的普通话声音自然说出来；不要唱歌、吟唱、Rap、歌词化表达、价格促销、购买引导、直播口播或主播出镜。
14. ending_frame 写本分镜最后一帧，包含产品姿态、背景、光线、构图和是否能衔接下一分镜，必须像品牌广告主视觉。
15. hook 字段只作为内部卖点钩子，用来指导镜头动作，不要让画面出现字幕、屏幕文字、价格、购买按钮或促销 CTA。
16. 所有输出必须是中文。
17. 每次重生成都必须明显更换场景组合、镜头顺序、入场动作、卖点呈现方式和结尾帧，不要复用上一版分镜。优先沿“本次创意路线”构思。
18. 必须优先满足“用户创作需求”；如果用户写了“6段5s”，就输出 6 个分镜、每个分镜围绕 5 秒节奏书写，除非当前视频模型有固定时长限制。

质量要求：
- 镜头语言必须具体且有大片感：低机位英雄跟拍、贴地运动近景、推镜头、横移、材质微距、手持轻微晃动、慢动作水花/尘土/水雾、逆光轮廓光。
- 如果有分镜/场景参考图，必须吸收其构图、场景、光线、机位和广告质感，但不能把参考图里的无关产品替换成当前产品。
- 每个分镜只围绕一个核心卖点气质，不要塞入多个不连续动作；不能平铺直叙地说功能，必须让画面自然承载卖点并能配得上后期旁白字幕。
- 产品一致性必须通过“@产品参考图”来维持，但 JSON 里只写结构字段。
- 提示词最终会按“技术参数、参考素材、时间戳分镜、现场音效、禁止项”拼接；voiceover 会作为独立后期配音/字幕字段保存，不能出现在 video_prompt 里。
- image_frame 负责整段视频的首帧、场景、光线和动作起点；timeline 保持单场景连贯推进，可以从户外动作自然推进到产品英雄近景、材质微距或更高级的户外产品收束，但不要切到第二个场景，也不要切到测试/测评/对比场景。不要在 image_frame/timeline/sound/ending_frame 中写禁止词或负面提示，禁止项由后端统一追加。

只返回严格 JSON object，不要 Markdown，不要解释。格式：
{{
  "ad_concept": "一句话户外功能广告创意概念",
  "scenes": [
    {{
      "title": "1. 户外广告开场：短标题",
      "selling_point": "对应卖点",
      "hook": "6-10 字内部卖点钩子，不要作为画面字幕",
      "image_frame": "首帧图片@图片1画面描述",
      "timeline": [
        {{"time": "0-8秒", "shot": "景别", "camera": "运镜", "action": "同一户外场景内的连贯动作", "visual": "户外氛围、卖点画面细节和产品样式收束"}}
      ],
      "sound": "声音设计",
      "voiceover": "一句中文旁白",
      "ending_frame": "结尾帧描述"
    }}
  ]
}}
""".strip()
    beat_description = "6 个分镜：山野氛围开场、产品运动近景、动作中的卖点呈现、材质光影细节、户外行动片段、品牌定格收束"
    return f"""
你是资深产品广告大片导演和 AI 视频分镜提示词专家。请根据产品卖点，为同一个产品生成一条完整广告大片的 {scene_count} 个分镜。

产品名称：{name}
产品类目：{category}
产品补充信息：{description or "无"}
画幅：{aspect_ratio}
单个分镜时长：约 {duration} 秒
产品一致性要求：{detail_sheet_note}
分镜参考图要求：{storyboard_reference_note}
用户创作需求：{creative_brief_text or f"请根据上面的卖点，为我写 {scene_count} 段 {duration}s 的电商广告视频；分镜图片和视频提示词都按 Seedance 风格生成。"}

已整理/已编辑的卖点：
{points_text or "无明确卖点，请基于产品信息生成保守的电商卖点分镜。"}

生成要求：
1. 必须围绕卖点制作场景与分镜，不要泛泛写产品展示；卖点要自然融入运动动作、户外环境、材质细节和光影，不要写成对比、痛点反转、功能测试、硬性证明或说明书。
2. 默认节奏为 {beat_description}；如果 scene_count 与默认节奏不同，也要保持完整起承转合。
3. 每个分镜约 {duration} 秒，适合后续分别调用视频模型生成，再拼成一条完整产品视频。
4. 每个分镜只围绕一个核心卖点气质，不要把多个镜头动作塞进同一条；画面要高级、克制、偏运动偏户外。
5. image_prompt 要适合图片模型生成广告大片首帧/分镜图，必须描述电影构图、产品英雄位置、户外环境、自然光线、材质质感和运动氛围；首帧要能作为 @图片1 被视频提示词引用；不要在文字里二次发挥鞋身外观细节，产品外观由参考图决定。
6. video_prompt 要适合 Seedance/视频模型生成 5 秒左右片段，必须用自然中文写清楚技术参数、@图片1首帧/产品参考用途、时间戳画面、运镜、动作节奏、现场音效和禁止项；视频画面必须延续 image_prompt 的同一场景、同一光线和同一动作起点，不能另起一个对比/测试场景；声音规则必须写明生成阶段不要旁白、配音、人声或口播，不要背景音乐、BGM、配乐、音乐节奏或鼓点，只允许真实现场音效。
7. 不要生成价格、促销词、二维码、水印、虚假认证、夸大医疗/功效承诺。
8. 必须优先满足“用户创作需求”；如果用户写了“6段5s”，就输出 6 个分镜、每个分镜围绕 5 秒节奏书写；如果用户要求广告大片、电商广告、户外实测、生活方式等风格，要体现在 image_prompt 和 video_prompt 里。
9. 不要使用“对比、反差、痛点、证明、证据、测试、挑战”作为分镜核心结构；不要出现实验化测评或道具验证画面；可以有真实路况和动作，但不要把它写成硬测评。
10. 所有输出必须是中文。

只返回严格 JSON object，不要 Markdown，不要解释。格式：
{{
  "scenes": [
    {{
      "title": "1. 山野氛围：短标题",
      "selling_point": "对应卖点",
      "hook": "这个分镜的画面钩子",
      "image_prompt": "分镜图提示词",
      "video_prompt": "视频提示词",
      "voiceover": "最终配音/字幕旁白",
      "shot_notes": "约 {duration} 秒，镜头说明"
    }}
  ]
}}
""".strip()


def _normalize_storyboard_scenes(
    payload: Any,
    *,
    product: ProductInput,
    count: int,
    duration: int,
    aspect_ratio: str,
    route: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    raw_scenes = payload.get("scenes") if isinstance(payload, dict) else payload
    if not isinstance(raw_scenes, list):
        return []
    scenes: list[dict[str, str]] = []
    for index, item in enumerate(raw_scenes):
        if not isinstance(item, dict):
            continue
        title = _clean_text(_sanitize_storyboard_prompt_text(str(item.get("title") or item.get("name") or f"分镜 {index + 1}")), 100)
        selling_point = _clean_text(_sanitize_storyboard_prompt_text(str(item.get("selling_point") or item.get("sellingPoint") or item.get("point") or "")), 100)
        hook = _clean_text(_sanitize_storyboard_prompt_text(str(item.get("hook") or item.get("scene_hook") or "")), 180)
        if count == VEO_STORYBOARD_SCENE_COUNT:
            beat_name = title.split("：", 1)[0].split(".", 1)[-1].strip() or f"分镜 {index + 1}"
            scene = _veo_storyboard_scene(
                product,
                index=index,
                beat_name=beat_name,
                selling_point=selling_point or title,
                hook=hook or selling_point or title,
                detail=_clean_text(str(item.get("detail") or item.get("description") or ""), 220),
                aspect_ratio=aspect_ratio,
                duration=duration,
                image_frame=_sanitize_storyboard_prompt_text(str(item.get("image_frame") or item.get("imageFrame") or "")),
                timeline=item.get("timeline") or item.get("time_axis") or item.get("时间轴"),
                sound=str(item.get("sound") or item.get("声音") or ""),
                voiceover=str(item.get("voiceover") or item.get("narration") or item.get("旁白") or ""),
                ending_frame=_sanitize_storyboard_prompt_text(str(item.get("ending_frame") or item.get("endingFrame") or "")),
                route=route,
            )
            scenes.append(scene)
            if len(scenes) >= count:
                break
            continue
        image_prompt = _clean_text(_sanitize_storyboard_prompt_text(str(item.get("image_prompt") or item.get("imagePrompt") or item.get("storyboard_prompt") or "")), 1200)
        video_prompt = _normalize_video_prompt_sound(str(item.get("video_prompt") or item.get("videoPrompt") or item.get("prompt") or ""))
        image_prompt = _ensure_wearing_image_prompt(image_prompt, video_prompt, hook, selling_point, title)
        voiceover_text = _clean_text(str(item.get("voiceover") or item.get("voiceover_text") or item.get("voiceoverText") or item.get("narration") or item.get("旁白") or ""), 180)
        if not voiceover_text or _contains_legacy_storyboard_logic(voiceover_text):
            voiceover_text = _selling_point_ad_drama(selling_point or title, "").get("voiceover", "")
        shot_notes = _clean_text(str(item.get("shot_notes") or item.get("shotNotes") or item.get("notes") or ""), 220)
        if not image_prompt or not video_prompt:
            continue
        scenes.append(
            {
                "id": f"scene_{uuid.uuid4().hex[:8]}",
                "title": title or f"分镜 {index + 1}",
                "selling_point": selling_point,
                "hook": hook,
                "image_prompt": image_prompt,
                "video_prompt": video_prompt,
                "voiceover_text": voiceover_text,
                "shot_notes": shot_notes or f"约 {duration} 秒，围绕卖点完成单一镜头。",
                "storyboard_image_url": "",
                "video_url": "",
            }
        )
        if len(scenes) >= count:
            break
    return scenes


async def _generate_model_storyboard(
    req: StoryboardPlanRequest,
    *,
    count: int,
    duration: int,
    route: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    raw_points = req.selling_points or [
        SellingPoint(**point) for point in _fallback_selling_points(req.product, "")
    ]
    model = (req.language_model or ARK_MODEL_ID).strip() or ARK_MODEL_ID
    prompt = _storyboard_prompt(
        req.product,
        raw_points,
        aspect_ratio=req.aspect_ratio,
        duration=duration,
        scene_count=count,
        route=route,
        storyboard_reference_count=len(req.storyboard_reference_urls or []),
        creative_brief=req.creative_brief,
        creative_seed=req.creative_seed,
        regenerate_index=req.regenerate_index,
    )
    text = await _ark_chat_completion(prompt, model=model, max_tokens=4200)
    parsed = _parse_selling_points_json(text)
    scenes = _normalize_storyboard_scenes(
        parsed,
        product=req.product,
        count=count,
        duration=duration,
        aspect_ratio=req.aspect_ratio,
        route=route,
    )
    if len(scenes) < count:
        raise RuntimeError("豆包 Seed 2.0 Pro 未返回足够可解析的分镜 JSON。")
    return scenes


def _model_provider(model_id: str, models: list[dict[str, Any]], fallback: str) -> str:
    for model in models:
        if model.get("id") == model_id:
            return str(model.get("provider") or fallback)
    return fallback


def _ffmpeg_exe() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("当前环境缺少 ffmpeg，无法合成完整视频。") from exc


def _target_video_size(aspect_ratio: str) -> tuple[int, int]:
    value = (aspect_ratio or "9:16").strip()
    if value == "16:9":
        return 1280, 720
    if value == "1:1":
        return 1080, 1080
    if value == "4:3":
        return 960, 720
    if value == "3:4":
        return 810, 1080
    return 720, 1280


def _drawtext_escape(text: str) -> str:
    value = _clean_text(text, 120)
    value = value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    value = value.replace("%", "\\%").replace("[", "\\[").replace("]", "\\]")
    value = value.replace("\n", "\\n")
    return value or " "


def _wrap_subtitle_text(text: str, *, width: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    max_chars = 11 if width <= 720 else 16
    max_lines = 3 if width <= 720 else 2
    chunks = [part.strip() for part in re.findall(r".+?[，。；、,.!?！？]|.+$", cleaned) if part.strip()]
    lines: list[str] = []
    for chunk in chunks:
        while len(chunk) > max_chars + 2:
            lines.append(chunk[:max_chars])
            chunk = chunk[max_chars:]
        if chunk:
            if lines and len(lines[-1]) + len(chunk) <= max_chars and len(lines) < max_lines:
                lines[-1] += chunk
            else:
                lines.append(chunk)
    lines = lines[:max_lines]
    if len(lines) == max_lines and sum(len(line) for line in lines) < len(cleaned):
        lines[-1] = f"{lines[-1].rstrip('，,。；;、')}..."
    return "\n".join(lines)


def _ffmpeg_filter_arg(value: str) -> str:
    return value.replace("\\", "/")


def _drawtext_font_path_arg(value: str) -> str:
    return value.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _subtitle_font_file() -> str:
    candidates = [
        os.environ.get("BATCH_VIDEO_SUBTITLE_FONT_FILE", ""),
        os.environ.get("SUBTITLE_FONT_FILE", ""),
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\Deng.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if candidate and Path(candidate).exists():
            return _drawtext_font_path_arg(candidate)
    return ""


def _run_ffmpeg(cmd: list[str]) -> None:
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=creationflags,
        timeout=600,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        message = detail[-1] if detail else "ffmpeg 合成失败"
        raise RuntimeError(message[:500])


def _ffprobe_exe(ffmpeg: str = "") -> str:
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    if ffmpeg:
        try:
            candidate = Path(ffmpeg).with_name(name)
            if candidate.exists():
                return str(candidate)
        except (OSError, ValueError):
            pass
    return shutil.which(name) or shutil.which("ffprobe") or ""


def _media_duration_seconds_sync(ffmpeg: str, input_path: Path) -> float | None:
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    ffprobe = _ffprobe_exe(ffmpeg)
    if ffprobe:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(input_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=creationflags,
            timeout=30,
        )
        if completed.returncode == 0:
            try:
                duration = float((completed.stdout or "").strip().splitlines()[0])
            except (IndexError, TypeError, ValueError):
                duration = 0.0
            if duration > 0:
                return duration

    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(input_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=creationflags,
        timeout=30,
    )
    detail = f"{completed.stderr or ''}\n{completed.stdout or ''}"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", detail)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    try:
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


def _prepare_video_segment_sync(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    subtitle: str,
    subtitle_enabled: bool,
    start_time: float | None = None,
    end_time: float | None = None,
) -> None:
    start = max(0.0, float(start_time or 0.0))
    end = max(0.0, float(end_time or 0.0)) if end_time is not None else 0.0
    duration = end - start if end > start else 0.0
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1,fps=30"
    )
    if subtitle_enabled and subtitle:
        text = _drawtext_escape(_wrap_subtitle_text(subtitle, width=width))
        font_file = _subtitle_font_file()
        font_part = f"fontfile='{font_file}':" if font_file else "font='Microsoft YaHei':"
        font_size = max(20, round(width * 0.036))
        box_border = max(8, round(width * 0.014))
        line_spacing = max(4, round(font_size * 0.24))
        video_filter += (
            f",drawtext={font_part}text='{text}':x=(w-text_w)/2:y=h*0.67-text_h/2"
            f":fontsize={font_size}:fontcolor=white"
            f":line_spacing={line_spacing}"
            f":box=1:boxcolor=black@0.48:boxborderw={box_border}"
        )
    cmd = [
        ffmpeg,
        "-y",
    ]
    if start > 0:
        cmd.extend(["-ss", f"{start:.3f}"])
    cmd.extend([
        "-i",
        str(input_path),
    ])
    if duration > 0:
        cmd.extend(["-t", f"{duration:.3f}"])
    cmd.extend([
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ])
    _run_ffmpeg(cmd)


def _prepare_poster_segment_sync(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    duration: float,
) -> None:
    safe_duration = max(0.5, min(9.0, float(duration or 2.0)))
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1,fps=30"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(input_path),
        "-t",
        f"{safe_duration:.3f}",
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _concat_videos_sync(ffmpeg: str, prepared_paths: list[Path], list_path: Path, output_path: Path) -> None:
    list_text = "".join(f"file '{_ffmpeg_filter_arg(str(path))}'\n" for path in prepared_paths)
    list_path.write_text(list_text, "utf-8")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _concat_videos_with_poster_transition_sync(
    ffmpeg: str,
    main_paths: list[Path],
    poster_path: Path,
    list_path: Path,
    output_path: Path,
    *,
    main_duration: float,
    transition_duration: float = POSTER_TRANSITION_DURATION,
) -> None:
    if not main_paths:
        shutil.copyfile(poster_path, output_path)
        return

    main_video_path = output_path.with_name(f"{output_path.stem}_main.mp4")
    _concat_videos_sync(ffmpeg, main_paths, list_path, main_video_path)
    duration = max(0.15, min(float(transition_duration or 0.45), 0.8, max(0.15, main_duration / 2)))
    poster_fade_path = output_path.with_name(f"{output_path.stem}_poster_fade.mp4")
    fade_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(poster_path),
        "-vf",
        f"fade=t=in:st=0:d={duration:.3f},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(poster_fade_path),
    ]
    _run_ffmpeg(fade_cmd)
    filter_complex = (
        "[0:v]setpts=PTS-STARTPTS,fps=30[v0];"
        "[1:v]setpts=PTS-STARTPTS,fps=30[v1];"
        "[v0][v1]concat=n=2:v=1:a=0,format=yuv420p[v]"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(main_video_path),
        "-i",
        str(poster_fade_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _concat_audio_sync(ffmpeg: str, audio_paths: list[Path], list_path: Path, output_path: Path) -> None:
    list_text = "".join(f"file '{_ffmpeg_filter_arg(str(path))}'\n" for path in audio_paths)
    list_path.write_text(list_text, "utf-8")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "160k",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _fit_audio_to_duration_sync(ffmpeg: str, input_path: Path, output_path: Path, duration: float | None) -> None:
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
    ]
    if duration and duration > 0.1:
        cmd.extend(["-af", "apad", "-t", f"{float(duration):.3f}"])
    cmd.extend([
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "160k",
        str(output_path),
    ])
    _run_ffmpeg(cmd)


def _safe_volume(value: float | None, fallback: float) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError):
        volume = fallback
    return max(0.0, min(3.0, volume))


def _segment_clip_duration(item: FinalVideoSegment) -> float:
    try:
        start = max(0.0, float(item.start_time or 0.0))
        end = max(0.0, float(item.end_time or 0.0)) if item.end_time is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return end - start if end > start else 0.0


def _poster_duration_for_voiceover(audio_duration: float | None, fallback: float) -> float:
    try:
        base_duration = float(audio_duration or 0.0)
    except (TypeError, ValueError):
        base_duration = 0.0
    if base_duration <= 0:
        base_duration = float(fallback or 2.0)
    return max(2.0, min(8.0, base_duration + 0.35))


def _voiceover_with_product_name(text: str, product_name: str) -> str:
    cleaned = _clean_text(text, 180)
    name = _clean_text(product_name, 60)
    if not name or name in cleaned:
        return cleaned
    if not cleaned:
        return f"{name}，为户外每一步而来。"
    return f"{name}，{cleaned}"


def _poster_voiceover_text(product_name: str, *, product_name_spoken: bool = False) -> str:
    name = _clean_text(product_name, 60)
    suffix = "为户外每一步而来。"
    if name and not product_name_spoken:
        return f"{name}，{suffix}"
    return suffix if name else ""


def _is_product_detail_final_segment(item: FinalVideoSegment) -> bool:
    marker = " ".join([
        item.reference_mode or "",
        item.scene_id or "",
        item.title or "",
    ]).lower()
    return "product_detail" in marker or "产品细节收尾" in marker


def _voiceover_for_final_segment(text: str, product_name: str, *, product_name_only: bool) -> str:
    cleaned = _clean_text(text, 180)
    name = _clean_text(product_name, 60)
    if product_name_only and name:
        return name
    return cleaned


def _silent_audio_sync(ffmpeg: str, output_path: Path, duration: float) -> None:
    safe_duration = max(0.1, float(duration or 0.1))
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{safe_duration:.3f}",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "160k",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _extract_segment_audio_sync(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    *,
    start_time: float | None,
    end_time: float | None,
    duration: float,
) -> None:
    safe_duration = max(0.1, float(duration or 0.1))
    start = max(0.0, float(start_time or 0.0))
    cmd = [ffmpeg, "-y"]
    if start > 0:
        cmd.extend(["-ss", f"{start:.3f}"])
    cmd.extend(["-i", str(input_path), "-t", f"{safe_duration:.3f}"])
    cmd.extend([
        "-vn",
        "-af",
        "apad",
        "-t",
        f"{safe_duration:.3f}",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "160k",
        str(output_path),
    ])
    try:
        _run_ffmpeg(cmd)
    except RuntimeError:
        _silent_audio_sync(ffmpeg, output_path, safe_duration)


def _generate_drum_bgm_sync(output_path: Path, duration: float, sample_rate: int = 44100) -> None:
    safe_duration = max(0.1, float(duration or 0.1))
    frame_count = max(1, int(safe_duration * sample_rate))
    beat_interval = max(1, int(sample_rate * 0.5))
    hat_interval = max(1, int(sample_rate * 0.25))
    kick_frames = max(1, int(sample_rate * 0.16))
    hat_frames = max(1, int(sample_rate * 0.035))

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        chunk = bytearray()
        max_chunk_bytes = sample_rate * 4
        for index in range(frame_count):
            kick = 0.0
            beat_pos = index % beat_interval
            if beat_pos < kick_frames:
                t = beat_pos / sample_rate
                progress = beat_pos / kick_frames
                freq = 92.0 - 38.0 * progress
                kick = math.sin(2 * math.pi * freq * t) * math.exp(-28.0 * t) * 0.85

            hat = 0.0
            hat_pos = index % hat_interval
            if hat_pos < hat_frames:
                noise = ((((index * 1103515245) + 12345) >> 16) & 0x7FFF) / 16384.0 - 1.0
                hat = noise * math.exp(-180.0 * (hat_pos / sample_rate)) * 0.1

            value = max(-1.0, min(1.0, kick + hat))
            sample = int(value * 32767)
            chunk.extend(struct.pack("<hh", sample, sample))
            if len(chunk) >= max_chunk_bytes:
                wav_file.writeframes(chunk)
                chunk.clear()
        if chunk:
            wav_file.writeframes(chunk)


def _fit_bgm_to_duration_sync(ffmpeg: str, input_path: Path, output_path: Path, duration: float) -> None:
    safe_duration = max(0.1, float(duration or 0.1))
    fade_out_start = max(0.0, safe_duration - 0.65)
    cmd = [
        ffmpeg,
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(input_path),
        "-t",
        f"{safe_duration:.3f}",
        "-vn",
        "-af",
        f"afade=t=in:st=0:d=0.25,afade=t=out:st={fade_out_start:.3f}:d=0.6",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "192k",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _mix_audio_tracks_sync(
    ffmpeg: str,
    tracks: list[tuple[Path, float]],
    output_path: Path,
    *,
    duration: float | None = None,
) -> None:
    active_tracks = [(path, _safe_volume(volume, 1.0)) for path, volume in tracks if path.exists()]
    if not active_tracks:
        _silent_audio_sync(ffmpeg, output_path, float(duration or 0.1))
        return
    if len(active_tracks) == 1:
        path, volume = active_tracks[0]
        cmd = [ffmpeg, "-y", "-i", str(path), "-af", f"volume={volume}"]
        if duration and duration > 0.1:
            cmd.extend(["-t", f"{float(duration):.3f}"])
        cmd.extend(["-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", str(output_path)])
        _run_ffmpeg(cmd)
        return

    cmd = [ffmpeg, "-y"]
    for path, _volume in active_tracks:
        cmd.extend(["-i", str(path)])
    filters: list[str] = []
    labels: list[str] = []
    for index, (_path, volume) in enumerate(active_tracks):
        label = f"a{index}"
        filters.append(f"[{index}:a]volume={volume}[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(active_tracks)}:duration=longest:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.95[mix]"
    )
    cmd.extend(["-filter_complex", ";".join(filters), "-map", "[mix]"])
    if duration and duration > 0.1:
        cmd.extend(["-t", f"{float(duration):.3f}"])
    cmd.extend(["-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", str(output_path)])
    _run_ffmpeg(cmd)


def _mux_video_audio_sync(ffmpeg: str, video_path: Path, audio_path: Path, output_path: Path) -> None:
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "160k",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _product_reconstruction_prompt(product: ProductInput) -> str:
    name = _clean_text(product.name, 80) or "产品"
    category = _clean_text(product.category, 80) or "电商产品"
    description = _clean_text(product.description, 320)
    detail = f"产品补充信息：{description}\n" if description else ""
    return (
        "任务：基于用户上传的多张产品参考图，忠实还原同一个产品的完整真实形态，并输出一张横版产品结构参考表。\n"
        "优先级最高：参考图就是唯一事实来源。必须先锁定同一双/同一件产品的鞋型或外形轮廓、配色边界、材质纹理、logo/文字位置、开口形状、鞋带/扣具/缝线/鞋底花纹等关键身份特征，再生成其他视角。\n"
        "不要重新设计产品，不要美化成另一款，不要把多个参考图混成多款产品，不要改变品牌字母、logo 位置、颜色分区、鞋底齿形和整体比例。\n"
        "画面必须是一张干净的产品结构参考表，不要做海报，不要做营销长图，不要生成夸张场景。\n"
        f"产品名称：{name}\n"
        f"产品类目：{category}\n"
        f"{detail}"
        "输出为一张 16:9 高清产品结构参考表，白底或浅灰工作室背景，必须使用 2 行 x 4 列的八宫格排版；每个视图都完整、不裁切、无遮挡。\n"
        "八宫格标题必须固定且清晰可读，严禁把左侧视图和右侧视图合并成一个“侧视图”，严禁出现单独名为“侧视图”的格子。\n"
        "必须包含 8 个分区，按从左到右、从上到下排列：\n"
        "1. 正视图：产品居中完整展示，保持参考图中的正面轮廓、鞋头/开口/鞋带或主要结构，不能拉宽、变短或改配色；\n"
        "2. 左侧视图：展示产品左侧完整轮廓，以参考图中可见的左侧或最接近左侧的侧面信息为强参考，保持鞋身高度、鞋底厚度、logo/文字位置、色块边界、鞋跟和鞋头比例；\n"
        "3. 右侧视图：展示产品右侧完整轮廓，以参考图中可见的右侧或最接近右侧的侧面信息为强参考；如果参考图只提供一侧，另一侧只能做保守镜像/合理补全，不能改成另一款产品；\n"
        "4. 俯视图：展示顶部开口、鞋舌/鞋带/扣具/鞋面纹理。参考图看不到的部分只做保守补全，不能凭空增加新结构；\n"
        "5. 仰视图：展示鞋底或底部结构，花纹必须与参考图中的鞋底齿形、分区和颜色逻辑一致；看不清时生成合理但克制的同款底纹，不要夸张越野齿；\n"
        "6. 细节特写：只截取参考图中真实存在的关键细节，例如鞋面网布、缝线、包边、logo 区域、鞋底纹路、扣具或材质纹理；\n"
        "7. 信息摘要区：只写短标签，不要编造品牌、型号、参数或宣传语。可写“正视图 / 左侧视图 / 右侧视图 / 俯视图 / 仰视图 / 细节特写 / 材质参考”。\n"
        "8. 材质与结构辅助区：展示鞋面材质、鞋底齿形、logo 区域、色块边界或扣具/鞋带等小细节拼图，只能来自参考图真实可见信息。\n"
        "文字规则：如果参考图里的 logo 或品牌字母清晰可见，就尽量保持其位置和形状；如果看不清，不要编造新的品牌名、型号名、英文单词或中文营销文案，宁可留空或用简短标签。\n"
        "一致性规则：所有分区必须是同一个产品、同一配色、同一材质、同一结构、同一比例；正视图、左侧视图、右侧视图、俯视图、仰视图之间不能像不同款式，左右侧视图也不能互相矛盾。\n"
        "禁止：改变产品品类、改变主配色、重画 logo、生成多款不同产品、添加无关配件、增加不存在的装饰、卡通化、过度磨皮、强透视变形、拼贴错位、水印、二维码、价格、促销标签、夸张广告字。\n"
        "输出要求：真实电商产品结构参考图，清晰、克制、专业，适合后续作为分镜图和视频生成的统一产品参考。"
    )


def _product_poster_prompt(product: ProductInput, selling_points: list[SellingPoint]) -> str:
    name = _clean_text(product.name, 80) or "产品"
    category = _clean_text(product.category, 80) or "户外运动产品"
    description = _clean_text(product.description, 260)
    selling_text = "；".join(
        _clean_text(point.title or point.description, 36)
        for point in selling_points[:4]
        if (point.title or point.description or "").strip()
    )
    detail_note = "参考图包含产品完整形态详情表，海报中的产品必须严格以该图为准。" if product.detail_sheet_url else "海报中的产品必须严格以用户上传的产品参考图为准。"
    return (
        "任务：基于参考图制作一张电商广告收尾产品海报，用作短视频结尾定格画面。\n"
        f"产品名称：{name}\n"
        f"产品类目：{category}\n"
        f"产品补充信息：{description}\n"
        f"核心卖点：{selling_text or '户外运动、稳定可靠、质感高级'}\n"
        f"产品一致性：{detail_note} 不要重新设计产品，不要改变轮廓、比例、材质、配色、logo/文字位置和鞋底结构。\n"
        "画面风格：高级运动户外品牌广告大片的结尾主视觉，干净、有质感、有冲击力；产品清晰完整，像正式电商广告海报，不像结构表、不像说明书、不像直播截图。\n"
        "构图要求：9:16 竖版海报，产品为绝对主角，画面下半部分或中心偏下有稳定落点，背景可以是山野、溪流、岩石、晨光、棚拍运动质感中的一种，但不要喧宾夺主；留出适合视频结尾停留的干净空间。\n"
        "文字要求：只允许少量高级广告字，必须包含产品名称；可以加一句短广告语，但不要价格、二维码、购买按钮、促销标签、联系方式、平台水印或大段文案。\n"
        "输出要求：真实商业摄影/广告海报质感，高清、锐利、产品边缘清楚，适合作为视频结尾定格收尾。"
    )


@router.get("/models")
async def list_batch_video_models():
    asr_status = _asr_config_status()
    return {
        "language_models": LANGUAGE_MODELS,
        "image_models": IMAGE_MODELS,
        "video_models": _batch_video_models(),
        "asr": asr_status,
    }


@router.get("/draft")
async def get_workbench_draft():
    raw = db.get_user_setting(WORKBENCH_DRAFT_SETTING_KEY, "")
    if not raw:
        return {"draft": None, "updatedAt": 0}
    try:
        draft = json.loads(raw)
    except Exception:
        return {"draft": None, "updatedAt": 0}
    if not isinstance(draft, dict):
        return {"draft": None, "updatedAt": 0}
    return {
        "draft": draft,
        "updatedAt": int(draft.get("updatedAt") or 0),
    }


@router.put("/draft")
async def save_workbench_draft(req: WorkbenchDraftRequest):
    draft = dict(req.draft or {})
    draft["updatedAt"] = int(draft.get("updatedAt") or datetime.now(timezone.utc).timestamp() * 1000)
    db.set_user_setting(
        WORKBENCH_DRAFT_SETTING_KEY,
        json.dumps(draft, ensure_ascii=False, separators=(",", ":")),
    )
    return {"ok": True, "updatedAt": draft["updatedAt"]}


@router.get("/product-memory")
async def get_product_memory(request: Request, product_name: str = ""):
    key = _product_memory_key(product_name)
    if not key:
        return {"found": False, "memory": None, "updatedAt": 0}
    memories = _load_product_memories()
    memory = memories.get(key)
    cloud_memory = await _fetch_cloud_product_memory(product_name, request)
    cloud_url, _cloud_token = _cloud_sync_config()
    if isinstance(cloud_memory, dict):
        cloud_memory = _rewrite_memory_file_urls_for_cloud(cloud_memory, cloud_url)
        if int(cloud_memory.get("updatedAt") or 0) > int((memory or {}).get("updatedAt") or 0):
            memory = cloud_memory
            memories[key] = cloud_memory
            _save_product_memories(memories)
    if not isinstance(memory, dict):
        return {"found": False, "memory": None, "updatedAt": 0}
    return {
        "found": True,
        "memory": memory,
        "updatedAt": int(memory.get("updatedAt") or 0),
    }


@router.put("/product-memory")
async def save_product_memory(req: ProductMemoryRequest, request: Request):
    product_name = _clean_text(req.product_name or req.memory.get("productName", ""), 100)
    key = _product_memory_key(product_name)
    if not key:
        return {"ok": False, "updatedAt": 0, "message": "Product name is required."}
    memory = _normalize_product_memory(req.memory or {}, product_name)
    if not _is_cloud_forwarded_request(request):
        memory["updatedAt"] = int(datetime.now(timezone.utc).timestamp() * 1000)
    memories = _load_product_memories()
    memories[key] = memory
    _save_product_memories(memories)
    synced = await _push_cloud_product_memory(product_name, memory, request)
    return {"ok": True, "updatedAt": memory["updatedAt"], "memory": memory, "cloudSynced": synced}


@router.post("/product-reconstruction")
async def build_product_reconstruction(req: ProductReconstructionRequest):
    reference_urls = [url for url in dict.fromkeys(req.product.image_urls or []) if str(url or "").strip()]
    image_provider = _model_provider(req.image_model or "image2", IMAGE_MODELS, "jimeng")
    reference_limit = 16 if image_provider == "toapis" else (4 if image_provider == "openai_image" else 8)
    if not reference_urls:
        return {
            "status": "needs_reference",
            "image_model": req.image_model,
            "provider": image_provider,
            "prompt": "",
            "reference_urls": [],
            "message": "请先上传产品参考图，再生成产品完整形态详情表。",
        }
    return {
        "status": "ready",
        "image_model": req.image_model or "image2",
        "provider": image_provider,
        "aspect_ratio": req.aspect_ratio or "16:9",
        "prompt": _product_reconstruction_prompt(req.product),
        "reference_urls": reference_urls[:reference_limit],
        "views": [
            {"id": "front", "label": "正视图"},
            {"id": "left_side", "label": "左侧视图"},
            {"id": "right_side", "label": "右侧视图"},
            {"id": "top", "label": "俯视图"},
            {"id": "bottom", "label": "仰视图"},
            {"id": "details", "label": "细节特写"},
        ],
        "message": "产品完整形态详情表提示词已生成，可调用 Image2/图片模型生成。",
    }


@router.post("/product-poster")
async def build_product_poster(req: ProductPosterRequest):
    product_refs = [url for url in [req.product.detail_sheet_url, *(req.product.image_urls or [])] if str(url or "").strip()]
    image_provider = _model_provider(req.image_model or "image2", IMAGE_MODELS, "toapis")
    reference_limit = 16 if image_provider == "toapis" else (4 if image_provider == "openai_image" else 8)
    if not product_refs:
        return {
            "status": "needs_reference",
            "image_model": req.image_model,
            "provider": image_provider,
            "prompt": "",
            "reference_urls": [],
            "message": "请先上传产品图，或先用 Image2 生成并选择最终版产品还原图，再制作收尾海报。",
        }
    return {
        "status": "ready",
        "image_model": req.image_model or "image2",
        "provider": image_provider,
        "aspect_ratio": req.aspect_ratio or "9:16",
        "prompt": _product_poster_prompt(req.product, req.selling_points or []),
        "reference_urls": product_refs[:reference_limit],
        "duration": 2,
        "message": "产品收尾海报提示词已生成，可调用 Image2/图片模型生成。",
    }


@router.post("/transcribe")
async def transcribe_live_video(req: TranscriptionRequest):
    asr_status = _asr_config_status()
    if not asr_status["configured"]:
        return {
            "status": "needs_config",
            "provider": req.asr_provider,
            "live_video_url": req.live_video_url,
            "transcript": "",
            "segments": [],
            "message": (
                "豆包语音 API Key 尚未配置。"
                "请先在系统设置或电商素材 API 设置中填写豆包语音 API Key；当前可在下方粘贴直播转写文本继续生成卖点。"
            ),
            "configured": False,
            "missing_fields": asr_status["missing_fields"],
            "settings_path": asr_status["settings_path"],
            "workspace_settings_path": asr_status["workspace_settings_path"],
            "config_required": asr_status["config_required"],
            "created_at": _now(),
        }

    if not (req.live_video_url or "").strip():
        return {
            "status": "needs_video",
            "provider": req.asr_provider,
            "live_video_url": req.live_video_url,
            "transcript": "",
            "segments": [],
            "configured": True,
            "message": "请先上传直播视频，再调用豆包语音 ASR 转写。",
            "created_at": _now(),
        }

    media_path = deps.get_local_file_path_from_url(req.live_video_url)
    if not media_path:
        return {
            "status": "unsupported_source",
            "provider": req.asr_provider,
            "live_video_url": req.live_video_url,
            "transcript": "",
            "segments": [],
            "configured": True,
            "message": "当前只支持转写本页面上传的本地直播视频文件，请重新上传后再试。",
            "created_at": _now(),
        }

    api_key = _setting_value(*ASR_API_KEY_FIELD["setting_keys"]) or os.environ.get(ASR_API_KEY_FIELD["env"], "")
    try:
        result = await transcribe_media_file(
            api_key=api_key,
            media_path=media_path,
            language=req.language or "zh-CN",
        )
    except DoubaoSpeechError as exc:
        return {
            "status": "failed",
            "provider": req.asr_provider,
            "live_video_url": req.live_video_url,
            "transcript": "",
            "segments": [],
            "configured": True,
            "task_id": getattr(exc, "task_id", ""),
            "audio_seconds": getattr(exc, "audio_seconds", None),
            "message": f"豆包语音转写失败：{exc}",
            "created_at": _now(),
        }

    return {
        "status": "ready",
        "provider": req.asr_provider,
        "live_video_url": req.live_video_url,
        "transcript": result["transcript"],
        "segments": result["segments"],
        "configured": True,
        "task_id": result["task_id"],
        "audio_seconds": result["audio_seconds"],
        "resource_id": result["resource_id"],
        "message": "直播视频已通过豆包大模型流式语音识别 2.0 转写完成。",
        "created_at": _now(),
    }


@router.post("/selling-points")
async def generate_selling_points(req: SellingPointsRequest):
    manual_points = _split_manual_points(req.manual_selling_points)
    if manual_points:
        points = [
            {
                "title": point,
                "description": point,
                "evidence": "",
                "source": "manual",
            }
            for point in manual_points[:12]
        ]
        return {
            "status": "ready",
            "mode": "manual",
            "language_model": req.language_model,
            "selling_points": points,
            "warnings": [],
        }

    try:
        points = await _generate_model_selling_points(req)
        if points:
            return {
                "status": "ready",
                "mode": "doubao_seed_2_0_pro",
                "language_model": req.language_model or ARK_MODEL_ID,
                "selling_points": points,
                "warnings": [],
            }
    except Exception as exc:
        fallback_points = _fallback_selling_points(req.product, req.transcript_text)
        return {
            "status": "draft",
            "mode": "local_fallback",
            "language_model": req.language_model or ARK_MODEL_ID,
            "selling_points": fallback_points,
            "warnings": [
                f"豆包 Seed 2.0 Pro 生成卖点失败，已返回本地草稿：{str(exc)[:180]}",
            ],
        }

    points = _fallback_selling_points(req.product, req.transcript_text)
    return {
        "status": "draft",
        "mode": "local_draft",
        "language_model": req.language_model or ARK_MODEL_ID,
        "selling_points": points,
        "warnings": [
            "直播转写文本为空，已返回本地可编辑草稿；粘贴或转写直播文本后会调用豆包 Seed 2.0 Pro 生成卖点。",
        ],
    }


@router.post("/storyboard-plan")
async def build_storyboard_plan(req: StoryboardPlanRequest):
    is_veo = _is_fixed_eight_second_model(req.video_model or "")
    brief_count, brief_duration = _parse_storyboard_creative_brief(req.creative_brief)
    requested_count = brief_count if brief_count else int(req.variant_count or DEFAULT_STORYBOARD_SCENE_COUNT)
    requested_duration = brief_duration if brief_duration else int(req.duration or 5)
    count = VEO_STORYBOARD_SCENE_COUNT if is_veo else max(1, min(requested_count, 12))
    duration = VEO_STORYBOARD_DURATION if is_veo else max(4, min(requested_duration, 15))
    seed_value = _storyboard_seed(req)
    route = _creative_route(seed_value) if is_veo else None
    raw_points = req.selling_points or [
        SellingPoint(**point) for point in _fallback_selling_points(req.product, "")
    ]
    warnings: list[str] = []
    mode = "doubao_seed_2_0_pro"
    try:
        scenes = await _generate_model_storyboard(req, count=count, duration=duration, route=route)
    except Exception as exc:
        mode = "local_fallback"
        scenes = []
        for index in range(count):
            point = raw_points[index % len(raw_points)]
            scenes.append(_scene_templates(req.product, point, index, req.aspect_ratio, duration, count, route=route))
        warnings.append(f"豆包 Seed 2.0 Pro 生成分镜失败，已返回本地 {count} 分镜草稿：{str(exc)[:180]}")
    route_text = f"创意路线：{route['name']}；" if route else ""
    warnings.append(f"{route_text}已按卖点生成 {count} 个分镜；每个分镜约 {duration} 秒，可继续编辑图片提示词和视频提示词。")
    return {
        "status": "ready",
        "mode": mode,
        "language_model": req.language_model,
        "image_model": req.image_model,
        "video_model": req.video_model,
        "aspect_ratio": req.aspect_ratio,
        "duration": duration,
        "creative_route": route,
        "creative_seed": req.creative_seed,
        "regenerate_index": req.regenerate_index,
        "scenes": scenes,
        "warnings": warnings,
    }


@router.post("/submit")
async def submit_batch_video(req: SubmitBatchRequest):
    batch_id = f"batch_{uuid.uuid4().hex[:10]}"
    image_provider = _model_provider(req.image_model, IMAGE_MODELS, "jimeng")
    video_provider = _model_provider(req.video_model, _batch_video_models(), "jimeng")
    product_refs = [url for url in [req.product.detail_sheet_url, *req.product.image_urls] if url]
    tasks = []
    for index, scene in enumerate(req.scenes):
        task_id = f"{batch_id}_{index + 1:02d}"
        image_request = {
            "project_id": "",
            "prompt": scene.image_prompt,
            "provider": image_provider,
            "model": req.image_model,
            "aspect_ratio": req.aspect_ratio,
            "asset_type": "scene",
            "reference_urls": product_refs[:8],
        }
        video_request = {
            "project_id": "",
            "prompt": _normalize_video_prompt_sound(scene.video_prompt),
            "provider": video_provider,
            "model": req.video_model,
            "duration": req.duration,
            "aspect_ratio": req.aspect_ratio,
            "resolution": req.resolution or "720p",
            "character_refs": [],
            "scene_refs": [scene.storyboard_image_url] if scene.storyboard_image_url else product_refs[:1],
            "reference_video_url": "",
            "advanced_reference_videos": [],
        }
        tasks.append(
            {
                "id": task_id,
                "scene_id": scene.id or task_id,
                "title": scene.title,
                "status": "draft_ready",
                "image_request": image_request,
                "video_request": video_request,
            }
        )
    return {
        "batch_id": batch_id,
        "status": "draft_ready",
        "created_at": _now(),
        "tasks": tasks,
        "message": "批量任务已整理为可执行请求，请在前端逐条或批量调用图片/视频模型。",
    }


@router.post("/compose-final-video")
async def compose_final_video(req: ComposeFinalVideoRequest):
    segments = [item for item in req.segments if (item.video_url or "").strip()]
    if not segments:
        return {
            "status": "needs_video",
            "video_url": "",
            "message": "请先为每个分镜选择最终视频版本，再合成完整视频。",
        }

    local_segments: list[tuple[FinalVideoSegment, Path]] = []
    for item in segments:
        path = deps.get_local_file_path_from_url(item.video_url)
        if not path or not path.exists():
            return {
                "status": "missing_file",
                "video_url": "",
                "scene_id": item.scene_id,
                "message": f"分镜「{item.title or item.scene_id or '未命名'}」的视频文件不在本地，请先重新拉取结果或重新上传。",
            }
        local_segments.append((item, path))

    custom_bgm_path: Path | None = None
    if req.bgm_enabled and (req.bgm_url or "").strip():
        custom_bgm_path = deps.get_local_file_path_from_url(req.bgm_url.strip())
        if not custom_bgm_path or not custom_bgm_path.exists():
            return {
                "status": "missing_bgm",
                "video_url": "",
                "message": "已选择自定义 BGM，但本地音频文件不存在，请重新上传 BGM 后再合成。",
            }

    poster_image_path: Path | None = None
    requested_poster_duration = max(0.0, min(8.0, float(req.poster_duration or 0.0)))
    poster_duration = requested_poster_duration if requested_poster_duration > 0 else 2.0
    if (req.poster_image_url or "").strip():
        poster_image_path = deps.get_local_file_path_from_url(req.poster_image_url.strip())
        if not poster_image_path or not poster_image_path.exists():
            return {
                "status": "missing_poster",
                "video_url": "",
                "message": "已选择收尾产品海报，但本地图片文件不存在，请重新生成或重新上传海报后再合成。",
            }

    width, height = _target_video_size(req.aspect_ratio)
    ffmpeg = _ffmpeg_exe()
    output_name = "".join(ch for ch in (req.output_name or "batch_final_video") if ch.isascii() and (ch.isalnum() or ch in ("_", "-")))
    output_name = output_name[:40] or "batch_final_video"
    final_name = f"{output_name}_{uuid.uuid4().hex[:10]}.mp4"
    final_path = deps.get_files_dir() / final_name
    voiceover_api_key = _setting_value(*ASR_API_KEY_FIELD["setting_keys"]) or os.environ.get(ASR_API_KEY_FIELD["env"], "")
    product_name = _clean_text(req.product_name, 80)
    has_product_detail_final_segment = any(_is_product_detail_final_segment(item) for item in segments)
    poster_voiceover_text = _poster_voiceover_text(
        product_name,
        product_name_spoken=has_product_detail_final_segment,
    ) if poster_image_path and product_name else ""
    has_voiceover_text = any(item.voiceover_text or _is_product_detail_final_segment(item) for item in segments) or bool(poster_voiceover_text)
    should_voiceover = (
        req.voiceover_enabled
        and (req.tts_provider or "doubao_speech_2_0") == "doubao_speech_2_0"
        and has_voiceover_text
    )
    voiceover_generated = False
    voiceover_error = ""
    voiceover_audio_count = 0
    poster_duration_used = poster_duration if poster_image_path else 0.0

    if should_voiceover and not voiceover_api_key:
        return {
            "status": "voiceover_failed",
            "video_url": "",
            "message": "旁白配音失败：豆包语音 API Key 未配置，无法生成有声完整视频。",
            "voiceover_error": "豆包语音 API Key 未配置。",
        }

    async def _compose_async() -> None:
        nonlocal voiceover_audio_count
        voiceover_audio_count = 0
        with tempfile.TemporaryDirectory(prefix="batch_video_compose_") as tmp:
            tmp_dir = Path(tmp)
            prepared_paths: list[Path] = []
            audio_paths: list[Path] = []
            for index, (item, input_path) in enumerate(local_segments):
                prepared = tmp_dir / f"segment_{index:03d}.mp4"
                subtitle = item.subtitle or item.voiceover_text or item.title or f"分镜 {index + 1}"
                await asyncio.to_thread(
                    _prepare_video_segment_sync,
                    ffmpeg,
                    input_path,
                    prepared,
                    width=width,
                    height=height,
                    subtitle=subtitle,
                    subtitle_enabled=req.subtitle_enabled,
                    start_time=item.start_time,
                    end_time=item.end_time,
                )
                prepared_paths.append(prepared)
                voiceover_text = (item.voiceover_text or item.subtitle or "").strip()
                if should_voiceover and voiceover_text:
                    audio_path = tmp_dir / f"voiceover_{index:03d}.mp3"
                    fitted_audio_path = tmp_dir / f"voiceover_fit_{index:03d}.m4a"
                    await synthesize_speech_2_0_file(
                        api_key=voiceover_api_key,
                        text=voiceover_text,
                        output_path=audio_path,
                        voice_type=req.tts_voice_type,
                        speed_ratio=req.tts_speed_ratio,
                    )
                    if not audio_path.exists() or audio_path.stat().st_size <= 0:
                        raise DoubaoSpeechError("豆包语音合成返回音频为空。")
                    try:
                        clip_start = max(0.0, float(item.start_time or 0.0))
                        clip_end = max(0.0, float(item.end_time or 0.0)) if item.end_time is not None else 0.0
                        segment_duration = clip_end - clip_start if clip_end > clip_start else 0.0
                    except (TypeError, ValueError):
                        segment_duration = 0.0
                    if segment_duration <= 0:
                        segment_duration = await asyncio.to_thread(deps.get_local_video_duration_seconds, item.video_url)
                    await asyncio.to_thread(_fit_audio_to_duration_sync, ffmpeg, audio_path, fitted_audio_path, segment_duration)
                    audio_paths.append(fitted_audio_path)
                    voiceover_audio_count += 1
            if should_voiceover and not audio_paths:
                raise DoubaoSpeechError("未生成任何旁白音频，请检查完整视频区域的旁白文案。")
            video_only_path = tmp_dir / "video_only.mp4" if should_voiceover and audio_paths else final_path
            await asyncio.to_thread(_concat_videos_sync, ffmpeg, prepared_paths, tmp_dir / "concat.txt", video_only_path)
            if should_voiceover and audio_paths:
                voiceover_path = tmp_dir / "voiceover.m4a"
                await asyncio.to_thread(_concat_audio_sync, ffmpeg, audio_paths, tmp_dir / "audio_concat.txt", voiceover_path)
                await asyncio.to_thread(_mux_video_audio_sync, ffmpeg, video_only_path, voiceover_path, final_path)

    async def _compose_async_v2() -> None:
        nonlocal voiceover_audio_count, poster_duration_used
        voiceover_audio_count = 0
        poster_duration_used = poster_duration if poster_image_path else 0.0
        with tempfile.TemporaryDirectory(prefix="batch_video_compose_") as tmp:
            tmp_dir = Path(tmp)
            prepared_paths: list[Path] = []
            voiceover_audio_paths: list[Path] = []
            original_audio_paths: list[Path] = []
            segment_durations: list[float] = []
            main_prepared_paths: list[Path] = []
            poster_prepared_path: Path | None = None

            for index, (item, input_path) in enumerate(local_segments):
                prepared = tmp_dir / f"segment_{index:03d}.mp4"
                raw_voiceover_text = (item.voiceover_text or "").strip()
                voiceover_text = _voiceover_for_final_segment(
                    raw_voiceover_text,
                    product_name,
                    product_name_only=bool(product_name and _is_product_detail_final_segment(item)),
                )
                subtitle = item.subtitle or voiceover_text or item.title or f"Segment {index + 1}"
                if req.voiceover_enabled and voiceover_text and subtitle == raw_voiceover_text:
                    subtitle = voiceover_text

                segment_duration = _segment_clip_duration(item)
                if segment_duration <= 0:
                    segment_duration = await asyncio.to_thread(deps.get_local_video_duration_seconds, item.video_url) or 0.0
                segment_durations.append(segment_duration)

                await asyncio.to_thread(
                    _prepare_video_segment_sync,
                    ffmpeg,
                    input_path,
                    prepared,
                    width=width,
                    height=height,
                    subtitle=subtitle,
                    subtitle_enabled=req.subtitle_enabled,
                    start_time=item.start_time,
                    end_time=item.end_time,
                )
                prepared_paths.append(prepared)
                main_prepared_paths.append(prepared)

                if req.keep_original_audio:
                    original_audio_path = tmp_dir / f"original_audio_{index:03d}.m4a"
                    await asyncio.to_thread(
                        _extract_segment_audio_sync,
                        ffmpeg,
                        input_path,
                        original_audio_path,
                        start_time=item.start_time,
                        end_time=item.end_time,
                        duration=segment_duration,
                    )
                    original_audio_paths.append(original_audio_path)

                if should_voiceover and voiceover_text:
                    audio_path = tmp_dir / f"voiceover_{index:03d}.mp3"
                    fitted_audio_path = tmp_dir / f"voiceover_fit_{index:03d}.m4a"
                    await synthesize_speech_2_0_file(
                        api_key=voiceover_api_key,
                        text=voiceover_text,
                        output_path=audio_path,
                        voice_type=req.tts_voice_type,
                        speed_ratio=req.tts_speed_ratio,
                    )
                    if not audio_path.exists() or audio_path.stat().st_size <= 0:
                        raise DoubaoSpeechError("Voiceover synthesis returned empty audio.")
                    await asyncio.to_thread(_fit_audio_to_duration_sync, ffmpeg, audio_path, fitted_audio_path, segment_duration)
                    voiceover_audio_paths.append(fitted_audio_path)
                    voiceover_audio_count += 1
                elif should_voiceover:
                    silent_voiceover_path = tmp_dir / f"voiceover_silence_{index:03d}.m4a"
                    await asyncio.to_thread(_silent_audio_sync, ffmpeg, silent_voiceover_path, segment_duration)
                    voiceover_audio_paths.append(silent_voiceover_path)

            if poster_image_path and poster_duration > 0:
                actual_poster_duration = poster_duration
                poster_text = poster_voiceover_text
                poster_fitted_audio_path: Path | None = None
                if should_voiceover and poster_text:
                    audio_path = tmp_dir / "voiceover_poster.mp3"
                    poster_fitted_audio_path = tmp_dir / "voiceover_fit_poster.m4a"
                    await synthesize_speech_2_0_file(
                        api_key=voiceover_api_key,
                        text=poster_text,
                        output_path=audio_path,
                        voice_type=req.tts_voice_type,
                        speed_ratio=req.tts_speed_ratio,
                    )
                    if not audio_path.exists() or audio_path.stat().st_size <= 0:
                        raise DoubaoSpeechError("Poster voiceover synthesis returned empty audio.")
                    poster_audio_duration = await asyncio.to_thread(_media_duration_seconds_sync, ffmpeg, audio_path)
                    actual_poster_duration = _poster_duration_for_voiceover(poster_audio_duration, poster_duration)
                    await asyncio.to_thread(_fit_audio_to_duration_sync, ffmpeg, audio_path, poster_fitted_audio_path, actual_poster_duration)
                    voiceover_audio_paths.append(poster_fitted_audio_path)
                    voiceover_audio_count += 1
                elif should_voiceover:
                    poster_fitted_audio_path = tmp_dir / "voiceover_silence_poster.m4a"
                    await asyncio.to_thread(_silent_audio_sync, ffmpeg, poster_fitted_audio_path, actual_poster_duration)
                    voiceover_audio_paths.append(poster_fitted_audio_path)

                poster_duration_used = actual_poster_duration
                poster_prepared = tmp_dir / "poster_segment.mp4"
                poster_source_duration = actual_poster_duration
                await asyncio.to_thread(
                    _prepare_poster_segment_sync,
                    ffmpeg,
                    poster_image_path,
                    poster_prepared,
                    width=width,
                    height=height,
                    duration=poster_source_duration,
                )
                prepared_paths.append(poster_prepared)
                poster_prepared_path = poster_prepared
                segment_durations.append(actual_poster_duration)
                if req.keep_original_audio:
                    poster_silent_audio = tmp_dir / "poster_silence.m4a"
                    await asyncio.to_thread(_silent_audio_sync, ffmpeg, poster_silent_audio, actual_poster_duration)
                    original_audio_paths.append(poster_silent_audio)

            if should_voiceover and voiceover_audio_count <= 0:
                raise DoubaoSpeechError("No voiceover audio was generated.")

            video_only_path = tmp_dir / "video_only.mp4"
            main_duration = sum(duration for duration in segment_durations[:-1] if duration and duration > 0) if poster_prepared_path else 0.0
            if poster_prepared_path:
                await asyncio.to_thread(
                    _concat_videos_with_poster_transition_sync,
                    ffmpeg,
                    main_prepared_paths,
                    poster_prepared_path,
                    tmp_dir / "concat.txt",
                    video_only_path,
                    main_duration=main_duration,
                )
            else:
                await asyncio.to_thread(_concat_videos_sync, ffmpeg, prepared_paths, tmp_dir / "concat.txt", video_only_path)

            total_duration = await asyncio.to_thread(_media_duration_seconds_sync, ffmpeg, video_only_path)
            if not total_duration or total_duration <= 0:
                total_duration = sum(duration for duration in segment_durations if duration and duration > 0)
            audio_tracks: list[tuple[Path, float]] = []

            if req.keep_original_audio and original_audio_paths:
                original_audio_path = tmp_dir / "original_audio.m4a"
                await asyncio.to_thread(
                    _concat_audio_sync,
                    ffmpeg,
                    original_audio_paths,
                    tmp_dir / "original_audio_concat.txt",
                    original_audio_path,
                )
                audio_tracks.append((original_audio_path, req.original_audio_volume))

            if should_voiceover and voiceover_audio_paths:
                voiceover_path = tmp_dir / "voiceover.m4a"
                await asyncio.to_thread(_concat_audio_sync, ffmpeg, voiceover_audio_paths, tmp_dir / "audio_concat.txt", voiceover_path)
                audio_tracks.append((voiceover_path, req.voiceover_volume))

            if req.bgm_enabled and total_duration > 0:
                if custom_bgm_path:
                    bgm_path = tmp_dir / "custom_bgm.m4a"
                    await asyncio.to_thread(_fit_bgm_to_duration_sync, ffmpeg, custom_bgm_path, bgm_path, total_duration)
                else:
                    bgm_path = tmp_dir / "drum_bgm.wav"
                    await asyncio.to_thread(_generate_drum_bgm_sync, bgm_path, total_duration)
                audio_tracks.append((bgm_path, req.bgm_volume))

            if audio_tracks:
                final_audio_path = tmp_dir / "final_audio.m4a"
                await asyncio.to_thread(_mix_audio_tracks_sync, ffmpeg, audio_tracks, final_audio_path, duration=total_duration)
                await asyncio.to_thread(_mux_video_audio_sync, ffmpeg, video_only_path, final_audio_path, final_path)
            else:
                shutil.copyfile(video_only_path, final_path)

    try:
        await _compose_async_v2()
        voiceover_generated = should_voiceover and voiceover_audio_count > 0
        deps.notify_media_file_saved(final_path)
    except DoubaoSpeechError as exc:
        try:
            final_path.unlink(missing_ok=True)
        except OSError:
            pass
        voiceover_error = str(exc)
        return {
            "status": "voiceover_failed",
            "video_url": "",
            "message": f"旁白配音失败：{voiceover_error[:300]}",
            "voiceover_enabled": req.voiceover_enabled,
            "voiceover_generated": False,
            "voiceover_provider": req.tts_provider,
            "voiceover_error": voiceover_error,
        }
    except Exception as exc:
        try:
            final_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "status": "failed",
            "video_url": "",
            "message": f"完整视频合成失败：{str(exc)[:300]}",
        }

    return {
        "status": "completed",
        "video_url": f"/api/files/{final_name}",
        "segment_count": len(local_segments),
        "aspect_ratio": req.aspect_ratio,
        "subtitle_enabled": req.subtitle_enabled,
        "voiceover_enabled": req.voiceover_enabled,
        "voiceover_generated": voiceover_generated,
        "voiceover_provider": req.tts_provider,
        "voiceover_error": voiceover_error,
        "poster_appended": bool(poster_image_path),
        "poster_duration": poster_duration_used if poster_image_path else 0,
        "message": (
            f"完整视频已合成：已保留片段原声，加入{'自定义' if custom_bgm_path else '默认鼓点'} BGM、旁白和字幕"
            f"{'，并用淡入转场在最后追加产品海报，海报停留时长会跟随产品名旁白' if poster_image_path else ''}，可以预览或下载。"
            if not voiceover_error
            else f"完整视频已合成，但旁白配音失败，仅保留字幕：{voiceover_error[:160]}"
        ),
    }
