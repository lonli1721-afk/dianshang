from __future__ import annotations

import json


TOAPIS_CREDITS_PER_USD = 200
DEFAULT_TOAPIS_USD_CNY_RATE = 7.2
TOAPIS_UNKNOWN_PRICE_NOTE = (
    "ToAPIs balance is tracked in credits. Public docs do not expose a stable "
    "credits-per-second price for this model; configure toapis_video_credit_prices "
    "as JSON to enable estimates."
)


def parse_toapis_credit_price_overrides(value) -> dict[str, float]:
    if not value:
        return {}
    if isinstance(value, dict):
        raw = value
    else:
        try:
            raw = json.loads(str(value))
        except Exception:
            return {}
    parsed: dict[str, float] = {}
    for key, price in raw.items():
        try:
            number = float(price)
        except (TypeError, ValueError):
            continue
        if key and number > 0:
            parsed[str(key)] = number
    return parsed


def parse_toapis_usd_cny_rate(value, default: float = DEFAULT_TOAPIS_USD_CNY_RATE) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0
    return number if number > 0 else default


def _estimated_price_per_second_cny(spec: dict, usd_cny_rate: float) -> float:
    unit = str(spec.get("price_unit") or "CNY").lower()
    try:
        price = float(spec.get("price_per_second") or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return 0.0
    if unit == "cny":
        return round(price, 4)
    if unit == "credits":
        try:
            credits_per_usd = float(spec.get("toapis_credits_per_usd") or TOAPIS_CREDITS_PER_USD)
        except (TypeError, ValueError):
            credits_per_usd = 0.0
        if credits_per_usd > 0 and usd_cny_rate > 0:
            return round(price / credits_per_usd * usd_cny_rate, 4)
    return 0.0


def enrich_video_model_cost_estimates(
    models: list[dict],
    *,
    toapis_usd_cny_rate: float = DEFAULT_TOAPIS_USD_CNY_RATE,
) -> list[dict]:
    rate = parse_toapis_usd_cny_rate(toapis_usd_cny_rate)
    enriched: list[dict] = []
    for spec in models:
        item = {**spec}
        estimate = _estimated_price_per_second_cny(item, rate)
        item["estimated_price_per_second_cny"] = estimate
        item["estimated_price_status"] = "priced" if estimate > 0 else "unpriced"
        if str(item.get("price_unit") or "").lower() == "credits":
            item["toapis_usd_cny_rate"] = rate
        enriched.append(item)
    return enriched


def _toapis_credit_price(spec: dict, overrides: dict[str, float] | None = None) -> float:
    overrides = overrides or {}
    for key in (spec.get("id"), spec.get("api_model")):
        if key in overrides:
            return overrides[key]
    try:
        return float(spec.get("default_price_per_second") or 0)
    except (TypeError, ValueError):
        return 0.0


def _toapis_spec(
    model_id: str,
    name: str,
    *,
    api_model: str | None = None,
    min_duration: int = 4,
    max_duration: int = 15,
    duration_choices: list[int] | None = None,
    supports_ref_images: bool = True,
    min_ref_images: int = 0,
    max_ref_images: int = 3,
    supported_aspect_ratios: list[str] | None = None,
    supported_resolutions: list[str] | None = None,
    default_resolution: str = "720p",
    ref_image_payload: str = "image_urls",
    duration_payload: str = "duration",
    aspect_payload: str = "aspect_ratio",
    ref_task_type: str = "",
    mode_from_resolution: bool = False,
    prompt_image_tokens: bool = False,
    default_price_per_second: float = 0,
    price_note: str = TOAPIS_UNKNOWN_PRICE_NOTE,
) -> dict:
    spec = {
        "id": model_id,
        "name": name,
        "provider": "toapis",
        "api_model": api_model or model_id,
        "supports_ref_video": False,
        "supports_ref_images": supports_ref_images,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "max_ref_images": max_ref_images,
        "supported_aspect_ratios": supported_aspect_ratios or ["16:9", "9:16"],
        "supported_resolutions": supported_resolutions or ["720p"],
        "default_resolution": default_resolution,
        "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
        "supported_modes": ["generate"],
        "price_per_second": 0,
        "price_unit": "credits",
        "price_status": "unpriced",
        "price_note": price_note,
        "toapis_credits_per_usd": TOAPIS_CREDITS_PER_USD,
        "toapis_ref_image_payload": ref_image_payload,
        "toapis_duration_payload": duration_payload,
        "toapis_aspect_payload": aspect_payload,
    }
    if ref_task_type:
        spec["toapis_ref_task_type"] = ref_task_type
    if min_ref_images:
        spec["min_ref_images"] = min_ref_images
    if duration_choices:
        spec["duration_choices"] = duration_choices
    if mode_from_resolution:
        spec["toapis_mode_from_resolution"] = True
    if prompt_image_tokens:
        spec["toapis_prompt_image_tokens"] = True
    if default_price_per_second:
        spec["default_price_per_second"] = default_price_per_second
    return spec


def _toapis_video_model_specs(price_overrides: dict[str, float] | None = None) -> list[dict]:
    specs = [
        _toapis_spec(
            "doubao-seedance-1-5-pro",
            "ToAPIs Doubao SeeDance 1.5 Pro",
            min_duration=4,
            max_duration=12,
            max_ref_images=1,
            ref_image_payload="image_with_roles",
            ref_task_type="i2v",
            price_note=TOAPIS_UNKNOWN_PRICE_NOTE + " Batch video uses the selected storyboard image as the first frame.",
        ),
        _toapis_spec("doubao-seedance-1-0-pro-fast", "ToAPIs Doubao SeeDance 1.0 Pro Fast", min_duration=4, max_duration=10, max_ref_images=2, ref_task_type="i2v"),
        _toapis_spec("doubao-seedance-1-0-pro-quality", "ToAPIs Doubao SeeDance 1.0 Pro Quality", min_duration=4, max_duration=10, max_ref_images=2, ref_task_type="i2v"),
        _toapis_spec("gemini_omni_flash", "ToAPIs Gemini Omni Flash", min_duration=4, max_duration=6, max_ref_images=3),
        _toapis_spec("grok-video-1.5-preview", "ToAPIs Grok Video 1.5 Preview", min_duration=10, max_duration=15, duration_choices=[10, 15], min_ref_images=1, max_ref_images=1, ref_image_payload="images", duration_payload="seconds", default_price_per_second=2, price_note="Official docs price 10s at $0.10 and 15s at $0.15; ToAPIs credits use 1 USD = 200 credits, so this is 2 credits/s."),
        _toapis_spec("grok-video-3", "ToAPIs Grok Video 3", min_duration=6, max_duration=15, duration_choices=[6, 10, 15], max_ref_images=3, supported_aspect_ratios=["16:9", "9:16", "3:2", "2:3", "1:1"], supported_resolutions=["480p", "720p"], ref_image_payload="images", duration_payload="seconds"),
        _toapis_spec("happyhorse-1.0", "ToAPIs HappyHorse 1.0", min_duration=3, max_duration=15, max_ref_images=9, supported_resolutions=["720p", "1080p"]),
        _toapis_spec("kling-v2-6", "ToAPIs Kling v2.6", min_duration=5, max_duration=10, duration_choices=[5, 10], max_ref_images=3, supported_aspect_ratios=["16:9", "9:16", "1:1"], supported_resolutions=["720p", "1080p"], ref_image_payload="reference_images", mode_from_resolution=True),
        _toapis_spec("kling-3.0-turbo", "ToAPIs Kling 3.0 Turbo", min_duration=3, max_duration=15, max_ref_images=1, supported_aspect_ratios=["16:9", "9:16", "1:1"], supported_resolutions=["720p", "1080p"], ref_image_payload="reference_images"),
        _toapis_spec("kling-v3", "ToAPIs Kling v3", min_duration=3, max_duration=15, max_ref_images=3, supported_aspect_ratios=["16:9", "9:16", "1:1"], supported_resolutions=["720p", "1080p"], ref_image_payload="reference_images", mode_from_resolution=True),
        _toapis_spec("kling-v3-omni", "ToAPIs Kling v3 Omni", min_duration=5, max_duration=10, duration_choices=[5, 10], max_ref_images=3, supported_aspect_ratios=["16:9", "9:16", "1:1"], supported_resolutions=["720p", "1080p"], ref_image_payload="metadata_image_list", mode_from_resolution=True, prompt_image_tokens=True),
        _toapis_spec("kling-video-o1", "ToAPIs Kling Video O1", min_duration=5, max_duration=10, duration_choices=[5, 10], max_ref_images=3, supported_aspect_ratios=["16:9", "9:16", "1:1"], supported_resolutions=["720p", "1080p"], ref_image_payload="metadata_image_list", mode_from_resolution=True, prompt_image_tokens=True),
        _toapis_spec("MiniMax-Hailuo-2.3", "ToAPIs MiniMax Hailuo 2.3", min_duration=6, max_duration=10, duration_choices=[6, 10], max_ref_images=1, supported_resolutions=["768p", "1080p"], default_resolution="768p"),
        _toapis_spec("MiniMax-Hailuo-2.3-Fast", "ToAPIs MiniMax Hailuo 2.3 Fast", min_duration=6, max_duration=10, duration_choices=[6, 10], max_ref_images=1, supported_resolutions=["768p", "1080p"], default_resolution="768p"),
        _toapis_spec("MiniMax-Hailuo-02", "ToAPIs MiniMax Hailuo 02", min_duration=6, max_duration=10, duration_choices=[6, 10], max_ref_images=2, supported_resolutions=["768p", "1080p"], default_resolution="768p"),
        _toapis_spec("seedance-2", "ToAPIs Seedance 2", min_duration=4, max_duration=15, max_ref_images=9, supported_resolutions=["720p", "1080p"]),
        _toapis_spec("seedance-2-fast", "ToAPIs Seedance 2 Fast", min_duration=4, max_duration=10, max_ref_images=9, supported_resolutions=["720p"]),
        _toapis_spec("seedance-2-mini", "ToAPIs Seedance 2 Mini", min_duration=4, max_duration=10, max_ref_images=9, supported_resolutions=["720p"]),
        _toapis_spec("sora-2-official", "ToAPIs Azure Sora 2 Official", min_duration=4, max_duration=12, duration_choices=[4, 8, 12], max_ref_images=1),
        _toapis_spec("sora-2-vvip", "ToAPIs Sora 2 VVIP", min_duration=4, max_duration=12, duration_choices=[4, 8, 12], max_ref_images=3),
        _toapis_spec("Veo3.1-quality-official", "ToAPIs Veo 3.1 Quality Official", min_duration=4, max_duration=8, duration_choices=[4, 6, 8], max_ref_images=1, supported_resolutions=["720p", "1080p", "4k"], aspect_payload="size"),
        _toapis_spec("veo3.1-fast", "Veo 3.1 Fast", min_duration=8, max_duration=8, duration_choices=[8], max_ref_images=1, supported_resolutions=["720p", "1080p", "4k"]),
        _toapis_spec("veo3.1-lite", "Veo 3.1 Lite", min_duration=8, max_duration=8, duration_choices=[8], max_ref_images=1, supported_resolutions=["720p", "1080p", "4k"]),
        _toapis_spec("veo3.1-quality", "Veo 3.1 Quality", min_duration=8, max_duration=8, duration_choices=[8], max_ref_images=1, supported_resolutions=["720p", "1080p", "4k"]),
        _toapis_spec("toapis-viduq3-pro", "ToAPIs Vidu Q3 Pro", api_model="viduq3-pro", min_duration=3, max_duration=16, max_ref_images=1, supported_resolutions=["720p", "1080p"]),
        _toapis_spec("toapis-viduq3-turbo", "ToAPIs Vidu Q3 Turbo", api_model="viduq3-turbo", min_duration=3, max_duration=16, max_ref_images=1, supported_resolutions=["720p", "1080p"]),
        _toapis_spec("toapis-viduq3", "ToAPIs Vidu Q3 Reference", api_model="viduq3", min_duration=3, max_duration=16, min_ref_images=1, max_ref_images=7, supported_resolutions=["540p", "720p", "1080p"]),
        _toapis_spec("wan2.6", "ToAPIs Wan 2.6", min_duration=5, max_duration=10, duration_choices=[5, 10], max_ref_images=1, supported_resolutions=["720p", "1080p"], default_resolution="1080p"),
        _toapis_spec("wan2.6-flash", "ToAPIs Wan 2.6 Flash", min_duration=5, max_duration=10, duration_choices=[5, 10], min_ref_images=1, max_ref_images=1, supported_resolutions=["720p", "1080p"], default_resolution="1080p"),
    ]
    for spec in specs:
        price = _toapis_credit_price(spec, price_overrides)
        if price > 0:
            spec["price_per_second"] = price
            spec["price_status"] = "configured"
    return specs


def get_all_video_model_specs(toapis_credit_prices: dict[str, float] | None = None) -> list[dict]:
    """Return the full known model catalog, independent of configured API keys."""
    return [
        {"id": "seedance-2.0", "name": "Seedance 2.0", "provider": "jimeng",
         "supports_ref_video": True, "supports_ref_images": True, "min_duration": 4, "max_duration": 15,
         "max_ref_images": 9, "max_ref_videos": 3, "ref_video_duration_limit": 15.2,
         "supported_resolutions": ["720p", "1080p"], "default_resolution": "720p",
         "limit_note": "生成时长 4-15 秒；支持 720P/1080P；参考视频/高级视频编辑参考视频需 15.2 秒以内",
         "supported_modes": ["generate", "reference_video", "advanced_video", "motion_transfer"],
         "price_per_second": 1.0, "price_unit": "CNY", "price_resolution_multiplier_1080p": 2.25,
         "price_note": "官方按输出视频像素、帧率、时长折算 token 计费；1080P 约为 720P 的 2.25 倍"},
        {"id": "seedance-2.0-fast", "name": "Seedance 2.0 Fast", "provider": "jimeng",
         "supports_ref_video": True, "supports_ref_images": True, "min_duration": 4, "max_duration": 10,
         "max_ref_images": 9, "max_ref_videos": 3, "ref_video_duration_limit": 15.2,
         "supported_resolutions": ["720p"], "default_resolution": "720p",
         "limit_note": "生成时长 4-10 秒；Fast 仅开放 720P；参考视频/高级视频编辑参考视频需 15.2 秒以内",
         "supported_modes": ["generate", "reference_video", "advanced_video"],
         "price_per_second": 0.8, "price_unit": "CNY"},
        {"id": "seedance-1.5-pro", "name": "Seedance 1.5 Pro", "provider": "jimeng",
         "supports_ref_video": False, "supports_ref_images": True, "min_duration": 4, "max_duration": 12,
         "max_ref_images": 2,
         "supported_resolutions": ["720p"], "default_resolution": "720p",
         "limit_note": "生成时长 4-12 秒；支持 1 张首帧图或 2 张首尾帧图；不支持参考视频/普通多参考图；当前仅开放 720P",
         "supported_modes": ["generate"],
         "price_per_second": 0.3, "price_unit": "CNY"},
        {"id": "viduq3-pro", "name": "VIDU Q3 Pro", "provider": "vidu",
         "supports_ref_video": False, "supports_ref_images": True, "min_duration": 1, "max_duration": 16,
         "max_ref_images": 1,
         "supported_resolutions": ["720p"], "default_resolution": "720p",
         "supported_modes": ["generate"],
         "price_per_second": 0.95, "price_unit": "CNY"},
        {"id": "viduq3-turbo", "name": "VIDU Q3 Turbo", "provider": "vidu",
         "supports_ref_video": False, "supports_ref_images": True, "min_duration": 1, "max_duration": 16,
         "max_ref_images": 1,
         "supported_resolutions": ["720p"], "default_resolution": "720p",
         "supported_modes": ["generate"],
         "price_per_second": 0.45, "price_unit": "CNY"},
        {"id": "happyhorse-1.0-t2v", "name": "HappyHorse 1.0 文生视频", "provider": "happyhorse",
         "supports_ref_video": False, "supports_ref_images": False, "min_duration": 3, "max_duration": 15,
         "supported_resolutions": ["720p", "1080p"], "default_resolution": "720p",
         "limit_note": "生成时长 3-15 秒；不需要参考图/参考视频",
         "supported_modes": ["generate"],
         "price_per_second": 0.9, "price_unit": "CNY",
         "price_per_second_1080p": 1.6, "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒"},
        {"id": "happyhorse-1.0-i2v", "name": "HappyHorse 1.0 首帧图生视频", "provider": "happyhorse",
         "supports_ref_video": False, "supports_ref_images": True, "min_duration": 3, "max_duration": 15,
         "min_ref_images": 1, "max_ref_images": 1,
         "supported_resolutions": ["720p", "1080p"], "default_resolution": "720p",
         "limit_note": "生成时长 3-15 秒；必须且只能使用 1 张首帧参考图；不支持参考视频",
         "supported_modes": ["generate"],
         "price_per_second": 0.9, "price_unit": "CNY",
         "price_per_second_1080p": 1.6, "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒"},
        {"id": "happyhorse-1.0-r2v", "name": "HappyHorse 1.0 参考图生视频", "provider": "happyhorse",
         "supports_ref_video": False, "supports_ref_images": True, "min_duration": 3, "max_duration": 15,
         "min_ref_images": 1, "max_ref_images": 9,
         "supported_resolutions": ["720p", "1080p"], "default_resolution": "720p",
         "limit_note": "生成时长 3-15 秒；支持 1-9 张角色/场景参考图；不支持参考视频",
         "supported_modes": ["generate"],
         "price_per_second": 0.9, "price_unit": "CNY",
         "price_per_second_1080p": 1.6, "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒"},
        {"id": "happyhorse-1.0-video-edit", "name": "HappyHorse 1.0 视频编辑", "provider": "happyhorse",
         "supports_ref_video": True, "supports_ref_images": True, "min_duration": 3, "max_duration": 15,
         "max_ref_images": 5, "max_ref_videos": 1, "ref_video_duration_min": 3, "ref_video_duration_limit": 60,
         "supported_resolutions": ["720p", "1080p"], "default_resolution": "720p",
         "limit_note": "输出视频最长 15 秒；输入参考视频需 3-60 秒；最多 1 个参考视频，可叠加 0-5 张参考图",
         "supported_modes": ["reference_video", "advanced_video"],
         "price_per_second": 0.9, "price_unit": "CNY",
         "price_per_second_1080p": 1.6, "price_billing": "input_output",
         "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒；视频编辑按输入视频与输出视频分别计费"},
        *_toapis_video_model_specs(toapis_credit_prices),
    ]


def get_video_model_spec(model: str) -> dict:
    return next((item for item in get_all_video_model_specs() if item.get("id") == model), {})


def get_video_model_specs(provider_filter=None, toapis_credit_prices: dict[str, float] | None = None) -> list[dict]:
    """Return catalog specs, optionally filtered to configured providers."""
    if provider_filter is None:
        return get_all_video_model_specs(toapis_credit_prices=toapis_credit_prices)
    providers = {provider for provider in provider_filter if provider}
    return [
        item
        for item in get_all_video_model_specs(toapis_credit_prices=toapis_credit_prices)
        if item.get("provider") in providers
    ]
