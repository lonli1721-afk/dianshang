from __future__ import annotations

import os
import re
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

import database as db
import deps
from doubao_speech_service import DoubaoSpeechError, transcribe_media_file


router = APIRouter()


ASR_API_KEY_FIELD = {
    "id": "api_key",
    "label": "豆包语音 API Key",
    "setting_keys": ["game_doubao_speech_api_key", "doubao_speech_api_key"],
    "env": "DOUBAO_SPEECH_API_KEY",
}

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
        "provider": "jimeng",
        "available": True,
        "note": "用于根据多张产品参考图生成完整产品详情表",
    },
    {
        "id": "nanobanana",
        "name": "Nano Banana",
        "provider": "custom_image",
        "available": False,
        "note": "待接入图片模型适配器",
    },
]

VIDEO_MODELS = [
    {
        "id": "seedance-2.0",
        "name": "Seedance 2.0",
        "provider": "jimeng",
        "available": True,
    },
    {
        "id": "happyhorse-1.0-i2v",
        "name": "HappyHorse I2V",
        "provider": "happyhorse",
        "available": True,
    },
    {
        "id": "happyhorse-1.0-t2v",
        "name": "HappyHorse T2V",
        "provider": "happyhorse",
        "available": True,
    },
    {
        "id": "veo3.1-fast",
        "name": "Veo 3.1 Fast",
        "provider": "toapis",
        "available": True,
    },
    {
        "id": "veo3.1-lite",
        "name": "Veo 3.1 Lite",
        "provider": "toapis",
        "available": True,
    },
    {
        "id": "veo3.1-quality",
        "name": "Veo 3.1 Quality",
        "provider": "toapis",
        "available": True,
    },
]

VEO_MODEL_IDS = {"veo3.1-fast", "veo3.1-lite", "veo3.1-quality"}
DEFAULT_STORYBOARD_SCENE_COUNT = 6
VEO_STORYBOARD_SCENE_COUNT = 4
VEO_STORYBOARD_DURATION = 8


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


class StoryboardScene(BaseModel):
    id: str = ""
    title: str = ""
    selling_point: str = ""
    hook: str = ""
    image_prompt: str = ""
    video_prompt: str = ""
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(text: str, limit: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:limit]


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
    replacements = {
        "不要出现主播": "",
        "不出现主播": "",
        "禁止主播": "",
        "无人物主播": "",
        "主播": "产品实测动作",
        "直播间": "户外自然环境",
        "直播带货": "户外功能广告",
        "带货": "功能展示",
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
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


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


def _creative_route(seed: int) -> dict[str, str]:
    routes = [
        {
            "name": "溪流实测",
            "visual": "溪流浅水、湿石、苔藓、水花慢动作、低机位跟拍",
            "tempo": "真实户外实测，动作清晰，卖点直接",
        },
        {
            "name": "山路穿越",
            "visual": "碎石山路、林间逆光、脚步扬起细小水珠和泥点、手持跟拍",
            "tempo": "纪录片式户外穿越，节奏更有行进感",
        },
        {
            "name": "雨后岩壁",
            "visual": "雨后岩石、深色湿润质感、微距水滴、鞋底纹路特写",
            "tempo": "偏硬核功能证明，强调抓地和结构细节",
        },
        {
            "name": "清晨露营地",
            "visual": "清晨自然光、溪边营地、木栈道、浅水边产品定格",
            "tempo": "更生活方式广告，质感明亮干净",
        },
        {
            "name": "极近微距",
            "visual": "鞋面网眼、扣具、鞋底纹路、水滴挂珠、材质反光",
            "tempo": "高质感微距商业摄影，强调产品细节",
        },
    ]
    return routes[seed % len(routes)]


def _timeline_items(raw: Any, *, name: str, title: str, hook: str, detail: str, duration: int) -> list[str]:
    items: list[str] = []
    if isinstance(raw, list):
        for item in raw[:4]:
            if isinstance(item, dict):
                time_label = _clean_text(str(item.get("time") or item.get("range") or ""), 20)
                parts = [
                    item.get("shot") or item.get("景别"),
                    item.get("camera") or item.get("运镜"),
                    item.get("action") or item.get("动作"),
                    item.get("visual") or item.get("画面"),
                    item.get("effect") or item.get("效果"),
                ]
                desc = _clean_text("，".join(str(part) for part in parts if part), 260)
                if time_label and desc:
                    items.append(f"{time_label}：{desc}")
                elif desc:
                    items.append(desc)
            elif isinstance(item, str):
                line = _clean_text(item, 260)
                if line:
                    items.append(line)
    if items:
        return items
    return [
        f"0-2秒：低机位近景，{name}进入真实山溪浅水或湿石环境，镜头直接用产品动作呈现“{hook}”。",
        f"2-5秒：跟随镜头推进，产品完成一次清晰实测动作，用水花、湿石、苔藓或碎石把“{title}”变成可见画面。",
        f"5-{duration}秒：微距特写切到鞋面/鞋底/扣具/纹理等关键结构，最后停在可继续衔接下一镜的产品定格。",
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
    route = route or {"name": "溪流实测", "visual": "真实山溪、湿石、苔藓和浅水环境", "tempo": "真实户外功能广告"}
    frame = _clean_text(
        image_frame,
        320,
    ) or f"{beat_name}，{route['visual']}中，{name}以低机位近景成为画面主角，突出“{title}”。"
    ending = _clean_text(
        ending_frame,
        220,
    ) or f"{name}停在湿石或溪水边缘，产品轮廓清晰，画面干净无文字，可衔接下一分镜。"
    sound_design = _clean_text(
        sound,
        180,
    ) or "清晰溪水声、脚步踩水声、轻微水花声，配合有节奏的户外广告鼓点。"
    voiceover_text = _clean_text(
        voiceover,
        140,
    ) or f"{name}{title}，真实户外环境里也能稳定发挥。"
    timeline_lines = _timeline_items(
        timeline,
        name=name,
        title=title,
        hook=caption,
        detail=detail,
        duration=duration,
    )
    image_prompt = "\n".join([
        "【用途】生成竖屏户外产品功能广告的单张分镜图，作为后续 Veo 视频首帧/视觉参考。",
        f"【参考】以@产品参考图为准，保持{name}的轮廓、颜色、材质、结构、鞋面/鞋底/扣具/纹理等关键细节一致。",
        f"【画幅】{aspect_ratio}，竖屏商业广告构图。",
        f"【创意路线】{route['name']}：{route['visual']}，{route['tempo']}。",
        f"【镜头】{frame}",
        "【质感】自然光、浅景深、湿石反光、苔藓、溪水、水滴、真实户外鞋服广告摄影质感。",
        "【画面要求】不要生成字幕、文字、价格、促销词、按钮、水印或二维码；用产品动作和环境细节表达卖点。",
        f"【结尾帧】{ending}",
    ])
    video_prompt = "\n".join([
        f"【风格】竖屏户外产品功能广告，{duration}秒，{aspect_ratio}，真实山溪/湿石/苔藓/浅水环境，自然光，低机位跟拍，微距特写，水花慢动作。",
        f"【参考】@图片1 作为本分镜首帧和构图参考；@产品参考图用于保持{name}外观、颜色、材质、结构和细节一致。",
        f"【创意路线】{route['name']}：{route['visual']}，{route['tempo']}。",
        "【时间轴】",
        *timeline_lines,
        f"【无字幕要求】全片不要出现任何字幕、屏幕文字、价格、促销词、按钮、水印或二维码；只用镜头动作、产品细节和环境音表现“{caption}”。",
        f"【声音】{sound_design}",
        f"【旁白】可以加入自然中文旁白音轨：“{voiceover_text}”。旁白只作为音频出现，不要生成字幕或任何屏幕文字。",
        f"【结尾帧】{ending}",
    ])
    return {
        "id": f"scene_{uuid.uuid4().hex[:8]}",
        "title": f"{index + 1}. {beat_name}：{title}",
        "selling_point": title,
        "hook": caption,
        "image_prompt": image_prompt,
        "video_prompt": video_prompt,
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
                ("林间山路入场", "碎石湿路也稳"),
                ("逆光英雄近景", f"{title}清晰可见"),
                ("碎石功能证明", f"{title}经得住走"),
                ("山路细节定格", "户外行走更安心"),
            ],
            "雨后岩壁": [
                ("雨后岩面开场", "湿石也能稳住"),
                ("水滴英雄近景", f"{title}看得见"),
                ("岩面抓地证明", f"{title}稳稳发挥"),
                ("纹理微距收束", "细节经得起放大"),
            ],
            "清晨露营地": [
                ("溪边营地开场", "出门轻松上脚"),
                ("晨光产品近景", f"{title}清晰可见"),
                ("浅水使用证明", f"{title}自然发挥"),
                ("露营定格收束", "通勤露营都好搭"),
            ],
            "极近微距": [
                ("材质微距开场", "细节一眼看清"),
                ("结构英雄近景", f"{title}看得见"),
                ("纹理功能证明", f"{title}经得住拍"),
                ("水滴定格收束", "质感细节拉满"),
            ],
        }
        beat_pool = fallback_beats.get(route_name, [
            ("溪流实测开场", "下水踩石走山路"),
            ("产品英雄近景", f"{title}看得见"),
            ("卖点功能证明", f"{title}稳稳发挥"),
            ("细节定格收束", "户外出行更安心"),
        ])
    else:
        beat_pool = [
            ("开场痛点", f"3 秒内展示用户遇到的问题，并自然引出{name}"),
            ("产品亮相", f"完整展示{name}外观、比例和核心结构"),
            ("卖点展开", f"围绕“{title}”展示产品带来的直接好处"),
            ("细节证明", f"用材质、结构、接口、纹理或关键细节证明“{title}”"),
            ("场景演示", f"把{name}放入真实使用场景，展示使用前后变化"),
            ("收尾定格", f"回到{name}完整产品定格，留下干净的商品展示画面"),
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
    scene_style = "真实电商短视频，干净背景，产品为主体，画面适合手机竖屏投放"
    if aspect_ratio == "16:9":
        scene_style = "真实电商横版视频，干净背景，产品为主体，画面适合店铺详情页和横版投放"
    image_prompt = (
        f"{scene_style}。分镜阶段：{beat_name}。产品：{name}。对应卖点：{title}。"
        f"画面要求：产品清晰可见，画面服务这个卖点，前景有使用场景或细节特写，光线明亮自然，"
        f"构图稳定，保留电商广告质感，不出现多余文字。{product_lock_hint}"
    )
    if detail:
        image_prompt += f" 参考信息：{detail}。"
    video_prompt = (
        f"{duration}秒左右电商素材分镜，阶段：{beat_name}。{hook}。"
        f"镜头必须围绕卖点“{title}”展开，保持同一产品外观与比例，"
        f"画面真实、节奏利落、适合和其他 5 个分镜拼成一条完整产品视频。"
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
    creative_seed: str = "",
    regenerate_index: int = 0,
) -> str:
    name = _clean_text(product.name, 80) or "未命名产品"
    category = _clean_text(product.category, 80) or "电商产品"
    description = _clean_text(product.description, 500)
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
        route = route or {"name": "溪流实测", "visual": "溪流浅水、湿石、苔藓、水花慢动作、低机位跟拍", "tempo": "真实户外实测，动作清晰，卖点直接"}
        seed_text = creative_seed or uuid.uuid4().hex
        return f"""
你是户外装备产品广告导演、短视频商业摄影指导和 Veo 3.1 视频提示词专家。请根据产品卖点，先构思一条类似“户外鞋服功能广告”的竖屏产品广告脚本，再拆成 {scene_count} 个适合 Veo 3.1 生成的分镜。

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

已整理/已编辑的卖点：
{points_text or "无明确卖点，请基于产品信息生成保守的产品广告片卖点。"}

生成要求：
1. 这是户外实测质感的产品广告，不是直播带货，不是主播口播，不是购买转化页面。
2. 视觉参考方向：竖屏，溪流/湿石/苔藓/山路/浅水，自然光，低机位跟拍，水花慢动作，产品微距，鞋底/纹理/结构特写，画面真实但商业广告质感强。
3. 先在脑中完成广告脚本：户外环境开场、产品上脚/入场、卖点功能证明、细节定格；输出时只输出分镜 JSON。
4. 4 个分镜必须分别承担：户外实测开场、产品英雄近景、卖点功能证明、细节定格收束。
5. 每个分镜约 {duration} 秒，适合 Veo 3.1 直接生成一段高质量 AI 视频，再拼成一条完整广告片。
6. 每个分镜必须围绕卖点，并把卖点转成可见动作或可见细节：防滑就拍湿石抓地，透气就拍网面和水汽/空气感，支撑就拍脚跟稳定，耐磨就拍鞋底纹理和碎石摩擦。
7. 不要直接输出散文式 image_prompt/video_prompt；请输出结构字段，后端会拼成最终提示词。
8. image_frame 写单张分镜图画面：主体位置、景别、构图、户外环境、光线、水花/湿石/苔藓等质感。
9. timeline 必须覆盖完整 0-8 秒，建议 0-2、2-5、5-8 三段；每段包含 time、shot、camera、action、visual。
10. sound 写环境音/音乐节奏，例如溪水声、脚步踩水声、低频鼓点。
11. voiceover 写一句自然中文旁白，10-24 个汉字左右，只作为音频口播，不作为画面字幕。
12. ending_frame 写本分镜最后一帧，包含产品姿态、背景、光线、构图和是否能衔接下一分镜。
13. hook 字段只作为内部卖点钩子，用来指导镜头动作，不要让画面出现字幕、屏幕文字、价格、购买按钮或促销 CTA。
14. 所有输出必须是中文。
15. 每次重生成都必须明显更换场景组合、镜头顺序、入场动作、卖点呈现方式和结尾帧，不要复用上一版分镜。优先沿“本次创意路线”构思。

质量要求：
- 镜头语言必须具体：低机位跟拍、推镜头、横移、微距特写、手持轻微晃动、慢动作水花等。
- 如果有分镜/场景参考图，必须吸收其构图、场景、光线、机位和广告质感，但不能把参考图里的无关产品替换成当前产品。
- 每个分镜只表达一个核心动作，不要塞入多个不连续动作。
- 产品一致性必须通过“@产品参考图”来维持，但 JSON 里只写结构字段。
- 不要在 image_frame/timeline/sound/ending_frame 中写禁止词或负面提示。

只返回严格 JSON object，不要 Markdown，不要解释。格式：
{{
  "ad_concept": "一句话户外功能广告创意概念",
  "scenes": [
    {{
      "title": "1. 户外实测开场：短标题",
      "selling_point": "对应卖点",
      "hook": "6-10 字内部卖点钩子，不要作为画面字幕",
      "image_frame": "单张分镜图画面描述",
      "timeline": [
        {{"time": "0-2秒", "shot": "景别", "camera": "运镜", "action": "动作", "visual": "画面细节"}},
        {{"time": "2-5秒", "shot": "景别", "camera": "运镜", "action": "动作", "visual": "画面细节"}},
        {{"time": "5-8秒", "shot": "景别", "camera": "运镜", "action": "动作", "visual": "画面细节"}}
      ],
      "sound": "声音设计",
      "voiceover": "一句自然中文旁白，只作为音频，不作为字幕",
      "ending_frame": "结尾帧描述"
    }}
  ]
}}
""".strip()
    beat_description = "6 个分镜：开场痛点、产品亮相、卖点展开、细节证明、场景演示、收尾定格"
    return f"""
你是资深电商短视频导演和 AI 视频分镜提示词专家。请根据产品卖点，为同一个产品生成一条完整短视频的 {scene_count} 个分镜。

产品名称：{name}
产品类目：{category}
产品补充信息：{description or "无"}
画幅：{aspect_ratio}
单个分镜时长：约 {duration} 秒
产品一致性要求：{detail_sheet_note}
分镜参考图要求：{storyboard_reference_note}

已整理/已编辑的卖点：
{points_text or "无明确卖点，请基于产品信息生成保守的电商卖点分镜。"}

生成要求：
1. 必须围绕卖点制作场景与分镜，不要泛泛写产品展示。
2. 默认节奏为 {beat_description}；如果 scene_count 与默认节奏不同，也要保持完整起承转合。
3. 每个分镜约 {duration} 秒，适合后续分别调用视频模型生成，再拼成一条完整产品视频。
4. 每个分镜只能表达一个清晰画面，不要把多个镜头动作塞进同一条。
5. image_prompt 要适合图片模型生成分镜图，必须描述画面、构图、产品位置、光线和场景。
6. video_prompt 要适合视频模型生成 5 秒左右片段，必须描述镜头运动、动作节奏、产品一致性和卖点呈现。
7. 不要生成价格、促销词、二维码、水印、虚假认证、夸大医疗/功效承诺。
8. 所有输出必须是中文。

只返回严格 JSON object，不要 Markdown，不要解释。格式：
{{
  "scenes": [
    {{
      "title": "1. 开场痛点：短标题",
      "selling_point": "对应卖点",
      "hook": "这个分镜的画面钩子",
      "image_prompt": "分镜图提示词",
      "video_prompt": "视频提示词",
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
        video_prompt = _clean_text(_sanitize_storyboard_prompt_text(str(item.get("video_prompt") or item.get("videoPrompt") or item.get("prompt") or "")), 1200)
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
        "输出为一张 16:9 高清产品结构参考表，白底或浅灰工作室背景，六宫格或清晰分区排版，每个视图都完整、不裁切、无遮挡。\n"
        "必须包含 6 个分区：\n"
        "1. 正视图：产品居中完整展示，保持参考图中的正面轮廓、鞋头/开口/鞋带或主要结构，不能拉宽、变短或改配色；\n"
        "2. 侧视图：以参考图中最清楚的侧面图为强参考，保持鞋身高度、鞋底厚度、logo/文字位置、色块边界、鞋跟和鞋头比例；\n"
        "3. 俯视图：展示顶部开口、鞋舌/鞋带/扣具/鞋面纹理。参考图看不到的部分只做保守补全，不能凭空增加新结构；\n"
        "4. 仰视图：展示鞋底或底部结构，花纹必须与参考图中的鞋底齿形、分区和颜色逻辑一致；看不清时生成合理但克制的同款底纹，不要夸张越野齿；\n"
        "5. 细节特写：只截取参考图中真实存在的关键细节，例如鞋面网布、缝线、包边、logo 区域、鞋底纹路、扣具或材质纹理；\n"
        "6. 信息摘要区：只写短标签，不要编造品牌、型号、参数或宣传语。可写“正视图 / 侧视图 / 俯视图 / 仰视图 / 细节特写 / 材质参考”。\n"
        "文字规则：如果参考图里的 logo 或品牌字母清晰可见，就尽量保持其位置和形状；如果看不清，不要编造新的品牌名、型号名、英文单词或中文营销文案，宁可留空或用简短标签。\n"
        "一致性规则：所有分区必须是同一个产品、同一配色、同一材质、同一结构、同一比例；正视图、侧视图、俯视图、仰视图之间不能像不同款式。\n"
        "禁止：改变产品品类、改变主配色、重画 logo、生成多款不同产品、添加无关配件、增加不存在的装饰、卡通化、过度磨皮、强透视变形、拼贴错位、水印、二维码、价格、促销标签、夸张广告字。\n"
        "输出要求：真实电商产品结构参考图，清晰、克制、专业，适合后续作为分镜图和视频生成的统一产品参考。"
    )


@router.get("/models")
async def list_batch_video_models():
    asr_status = _asr_config_status()
    return {
        "language_models": LANGUAGE_MODELS,
        "image_models": IMAGE_MODELS,
        "video_models": VIDEO_MODELS,
        "asr": asr_status,
    }


@router.post("/product-reconstruction")
async def build_product_reconstruction(req: ProductReconstructionRequest):
    reference_urls = [url for url in dict.fromkeys(req.product.image_urls or []) if str(url or "").strip()]
    if not reference_urls:
        return {
            "status": "needs_reference",
            "image_model": req.image_model,
            "provider": _model_provider(req.image_model, IMAGE_MODELS, "jimeng"),
            "prompt": "",
            "reference_urls": [],
            "message": "请先上传产品参考图，再生成产品完整形态详情表。",
        }
    return {
        "status": "ready",
        "image_model": req.image_model or "image2",
        "provider": _model_provider(req.image_model or "image2", IMAGE_MODELS, "jimeng"),
        "aspect_ratio": req.aspect_ratio or "16:9",
        "prompt": _product_reconstruction_prompt(req.product),
        "reference_urls": reference_urls[:8],
        "views": [
            {"id": "front", "label": "正视图"},
            {"id": "side", "label": "侧视图"},
            {"id": "top", "label": "俯视图"},
            {"id": "bottom", "label": "仰视图"},
            {"id": "details", "label": "细节特写"},
        ],
        "message": "产品完整形态详情表提示词已生成，可调用 Image2/图片模型生成。",
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
    is_veo = (req.video_model or "") in VEO_MODEL_IDS
    count = VEO_STORYBOARD_SCENE_COUNT if is_veo else max(DEFAULT_STORYBOARD_SCENE_COUNT, min(int(req.variant_count or DEFAULT_STORYBOARD_SCENE_COUNT), 12))
    duration = VEO_STORYBOARD_DURATION if is_veo else max(4, min(int(req.duration or 5), 15))
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
    video_provider = _model_provider(req.video_model, VIDEO_MODELS, "jimeng")
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
            "prompt": scene.video_prompt,
            "provider": video_provider,
            "model": req.video_model,
            "duration": req.duration,
            "aspect_ratio": req.aspect_ratio,
            "resolution": "720p",
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
