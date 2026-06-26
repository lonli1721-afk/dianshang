from __future__ import annotations

from dataclasses import dataclass

from video_model_registry import get_video_model_spec


class VideoGenerationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class VideoGenerationValidationResult:
    model_spec: dict
    mode: str


def _nonempty(items: list[str] | None) -> list[str]:
    return [item for item in (items or []) if str(item or "").strip()]


def _normalize_resolution(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"720", "720p", "hd"}:
        return "720p"
    if raw in {"1080", "1080p", "fhd", "fullhd"}:
        return "1080p"
    return raw or "720p"


def infer_generation_mode(reference_video_url: str = "", advanced_reference_videos: list[str] | None = None) -> str:
    if _nonempty(advanced_reference_videos):
        return "advanced_video"
    if str(reference_video_url or "").strip():
        return "reference_video"
    return "generate"


def validate_generate_video_request(
    *,
    provider: str,
    model: str,
    duration: int,
    resolution: str,
    aspect_ratio: str = "",
    image_url: str = "",
    character_refs: list[str] | None = None,
    scene_refs: list[str] | None = None,
    reference_video_url: str = "",
    advanced_reference_videos: list[str] | None = None,
) -> VideoGenerationValidationResult:
    provider_id = str(provider or "").strip()
    model_id = str(model or "").strip()
    spec = get_video_model_spec(model_id)
    if not spec:
        raise VideoGenerationValidationError(f"当前不支持的视频模型：{model_id or '未指定模型'}。")
    if spec.get("provider") != provider_id:
        raise VideoGenerationValidationError(
            f"模型 {spec.get('name') or model_id} 属于 {spec.get('provider')}，不能使用 {provider_id or '未指定服务商'} 生成。"
        )

    char_refs = _nonempty(character_refs)
    scene_ref_items = _nonempty(scene_refs)
    advanced_videos = _nonempty(advanced_reference_videos)
    has_image_url = bool(str(image_url or "").strip())
    has_reference_video = bool(str(reference_video_url or "").strip())
    ref_image_count = len(char_refs) + len(scene_ref_items)
    total_image_inputs = ref_image_count + (1 if has_image_url else 0)
    ref_video_count = (1 if has_reference_video else 0) + len(advanced_videos)

    if model_id == "happyhorse-1.0-video-edit" and ref_video_count != 1:
        raise VideoGenerationValidationError("HappyHorse 视频编辑需要且仅支持 1 个参考视频。")

    mode = infer_generation_mode(reference_video_url, advanced_videos)
    supported_modes = set(spec.get("supported_modes") or [])
    if mode not in supported_modes:
        mode_label = {
            "generate": "标准生成",
            "reference_video": "参考视频生成",
            "advanced_video": "高级视频编辑",
        }.get(mode, mode)
        raise VideoGenerationValidationError(f"{spec.get('name') or model_id} 不支持{mode_label}，请切换合适的模型或生成模式。")

    supported_aspect_ratios = set(str(item) for item in (spec.get("supported_aspect_ratios") or []))
    requested_aspect_ratio = str(aspect_ratio or "").strip()
    if supported_aspect_ratios and requested_aspect_ratio and requested_aspect_ratio not in supported_aspect_ratios:
        allowed = "/".join(sorted(supported_aspect_ratios))
        raise VideoGenerationValidationError(
            f"{spec.get('name') or model_id} 只支持 {allowed} 画幅，请切换画幅后重试。"
        )

    try:
        requested_duration = int(duration)
    except (TypeError, ValueError):
        raise VideoGenerationValidationError("视频时长必须是数字。")
    min_duration = int(spec.get("min_duration") or 1)
    max_duration = int(spec.get("max_duration") or min_duration)
    if requested_duration < min_duration or requested_duration > max_duration:
        raise VideoGenerationValidationError(
            f"{spec.get('name') or model_id} 生成时长需为 {min_duration}-{max_duration} 秒，请调整后重试。"
        )

    supported_resolutions = [str(item).lower() for item in (spec.get("supported_resolutions") or [])]
    normalized_resolution = _normalize_resolution(resolution)
    if supported_resolutions and normalized_resolution not in supported_resolutions:
        allowed = "/".join(item.upper() for item in supported_resolutions)
        raise VideoGenerationValidationError(
            f"{spec.get('name') or model_id} 不支持 {str(resolution or '').upper() or '当前'} 清晰度，请选择 {allowed}。"
        )

    if spec.get("supports_ref_images") is False and total_image_inputs:
        raise VideoGenerationValidationError(f"{spec.get('name') or model_id} 不支持参考图，请移除参考图或切换模型。")
    if spec.get("supports_ref_video") is False and ref_video_count:
        raise VideoGenerationValidationError(f"{spec.get('name') or model_id} 不支持参考视频，请移除参考视频或切换模型。")

    max_ref_images = int(spec.get("max_ref_images") or 0)
    if max_ref_images > 0:
        counted_images = total_image_inputs if spec.get("provider") == "vidu" or model_id == "happyhorse-1.0-i2v" else ref_image_count
        if counted_images > max_ref_images:
            raise VideoGenerationValidationError(
                f"{spec.get('name') or model_id} 最多支持 {max_ref_images} 张参考图，请减少后重试。"
            )

    max_ref_videos = int(spec.get("max_ref_videos") or 0)
    if max_ref_videos > 0 and ref_video_count > max_ref_videos:
        raise VideoGenerationValidationError(
            f"{spec.get('name') or model_id} 最多支持 {max_ref_videos} 个参考视频，请减少后重试。"
        )

    if model_id == "happyhorse-1.0-i2v" and total_image_inputs < 1:
        raise VideoGenerationValidationError("HappyHorse 首帧图生视频需要至少 1 张参考图。")
    if model_id == "happyhorse-1.0-r2v" and ref_image_count < 1:
        raise VideoGenerationValidationError("HappyHorse 参考图生视频需要至少 1 张角色/场景参考图。")
    return VideoGenerationValidationResult(model_spec=spec, mode=mode)
