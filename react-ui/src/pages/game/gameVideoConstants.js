export const AI_MODELS = [
  { id: 'doubao-seed-2-0-pro-260215', name: '火山 Doubao Seed 2.0 Pro' },
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash（实验）' },
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
]

export const REVERSE_MODELS = [
  { id: 'doubao-seed-2-0-pro-260215', name: '火山 Doubao Seed 2.0 Pro（推荐）' },
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash（实验）' },
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro（推荐）' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
]

export const TASK_POLL_INTERVAL_MS = 12000
export const TASK_POLL_HIDDEN_INTERVAL_MS = 60000
export const TASK_POLL_JITTER_MS = 2500
export const TASK_POLL_LIMIT = 200
export const SCENE_AUTOSAVE_DEBOUNCE_MS = 3500
export const REFERENCE_VIDEO_DURATION_LIMIT_SECONDS = 15.2
export const HAPPYHORSE_VIDEO_EDIT_MIN_SECONDS = 3
export const HAPPYHORSE_VIDEO_EDIT_MAX_SECONDS = 60
export const MAX_ADVANCED_REFERENCE_VIDEOS = 3
export const WAN_REFERENCE_VIDEO_MIN_SECONDS = 2
export const WAN_REFERENCE_VIDEO_MAX_SECONDS = 30

export const IMAGE_ASPECT_OPTIONS = [
  { id: '1:1', label: '1:1', width: 1024, height: 1024 },
  { id: '16:9', label: '16:9', width: 1280, height: 720 },
  { id: '9:16', label: '9:16', width: 720, height: 1280 },
  { id: '4:3', label: '4:3', width: 1152, height: 864 },
  { id: '3:4', label: '3:4', width: 864, height: 1152 },
]

export const VIDEO_RESOLUTION_OPTIONS = [
  { id: '720p', label: '720P 标准' },
  { id: '1080p', label: '1080P 高清' },
]

export const IMAGE_QUALITY_OPTIONS = [
  { id: '1K', label: '1K 基础' },
  { id: '2K', label: '2K 标准' },
  { id: '4K', label: '4K 超清' },
]

export const DEFAULT_IMAGE_ASPECT_RATIO = '1:1'

export const FALLBACK_VIDEO_MODELS = [
  {
    "id": "seedance-2.0",
    "name": "Seedance 2.0",
    "provider": "jimeng",
    "supports_ref_video": true,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 15,
    "max_ref_images": 9,
    "max_ref_videos": 3,
    "ref_video_duration_limit": 15.2,
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "生成时长 4-15 秒；支持 720P/1080P；参考视频/高级视频编辑参考视频需 15.2 秒以内",
    "supported_modes": [
      "generate",
      "reference_video",
      "advanced_video",
      "motion_transfer"
    ],
    "price_per_second": 1.0,
    "price_unit": "CNY",
    "price_resolution_multiplier_1080p": 2.25,
    "price_note": "官方按输出视频像素、帧率、时长折算 token 计费；1080P 约为 720P 的 2.25 倍"
  },
  {
    "id": "seedance-2.0-fast",
    "name": "Seedance 2.0 Fast",
    "provider": "jimeng",
    "supports_ref_video": true,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 10,
    "max_ref_images": 9,
    "max_ref_videos": 3,
    "ref_video_duration_limit": 15.2,
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "生成时长 4-10 秒；Fast 仅开放 720P；参考视频/高级视频编辑参考视频需 15.2 秒以内",
    "supported_modes": [
      "generate",
      "reference_video",
      "advanced_video"
    ],
    "price_per_second": 0.8,
    "price_unit": "CNY"
  },
  {
    "id": "seedance-1.5-pro",
    "name": "Seedance 1.5 Pro",
    "provider": "jimeng",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 12,
    "max_ref_images": 1,
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "生成时长 4-12 秒；支持 1 张首帧图或 2 张首尾帧图；不支持参考视频/普通多参考图；当前仅开放 720P",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0.3,
    "price_unit": "CNY"
  },
  {
    "id": "viduq3-pro",
    "name": "VIDU Q3 Pro",
    "provider": "vidu",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 1,
    "max_duration": 16,
    "max_ref_images": 1,
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0.95,
    "price_unit": "CNY"
  },
  {
    "id": "viduq3-turbo",
    "name": "VIDU Q3 Turbo",
    "provider": "vidu",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 1,
    "max_duration": 16,
    "max_ref_images": 1,
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0.45,
    "price_unit": "CNY"
  },
  {
    "id": "happyhorse-1.0-t2v",
    "name": "HappyHorse 1.0 文生视频",
    "provider": "happyhorse",
    "supports_ref_video": false,
    "supports_ref_images": false,
    "min_duration": 3,
    "max_duration": 15,
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "生成时长 3-15 秒；不需要参考图/参考视频",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0.9,
    "price_unit": "CNY",
    "price_per_second_1080p": 1.6,
    "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒"
  },
  {
    "id": "happyhorse-1.0-i2v",
    "name": "HappyHorse 1.0 首帧图生视频",
    "provider": "happyhorse",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 15,
    "min_ref_images": 1,
    "max_ref_images": 1,
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "生成时长 3-15 秒；必须且只能使用 1 张首帧参考图；不支持参考视频",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0.9,
    "price_unit": "CNY",
    "price_per_second_1080p": 1.6,
    "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒"
  },
  {
    "id": "happyhorse-1.0-r2v",
    "name": "HappyHorse 1.0 参考图生视频",
    "provider": "happyhorse",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 15,
    "min_ref_images": 1,
    "max_ref_images": 9,
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "生成时长 3-15 秒；支持 1-9 张角色/场景参考图；不支持参考视频",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0.9,
    "price_unit": "CNY",
    "price_per_second_1080p": 1.6,
    "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒"
  },
  {
    "id": "happyhorse-1.0-video-edit",
    "name": "HappyHorse 1.0 视频编辑",
    "provider": "happyhorse",
    "supports_ref_video": true,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 15,
    "max_ref_images": 5,
    "max_ref_videos": 1,
    "ref_video_duration_min": 3,
    "ref_video_duration_limit": 60,
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "输出视频最长 15 秒；输入参考视频需 3-60 秒；最多 1 个参考视频，可叠加 0-5 张参考图",
    "supported_modes": [
      "reference_video",
      "advanced_video"
    ],
    "price_per_second": 0.9,
    "price_unit": "CNY",
    "price_per_second_1080p": 1.6,
    "price_billing": "input_output",
    "price_note": "官方价格：720P 0.9元/秒，1080P 1.6元/秒；视频编辑按输入视频与输出视频分别计费"
  },
  {
    "id": "doubao-seedance-1-5-pro",
    "name": "ToAPIs Doubao SeeDance 1.5 Pro",
    "provider": "toapis",
    "api_model": "doubao-seedance-1-5-pro",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 12,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs Seedance 1.5 Pro：批量工作台使用当前分镜图作为首帧图输入；如需首尾帧请在专门支持首尾帧的流程中配置。",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_with_roles",
    "toapis_ref_task_type": "i2v",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "doubao-seedance-1-0-pro-fast",
    "name": "ToAPIs Doubao SeeDance 1.0 Pro Fast",
    "provider": "toapis",
    "api_model": "doubao-seedance-1-0-pro-fast",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 10,
    "max_ref_images": 2,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_ref_task_type": "i2v",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "doubao-seedance-1-0-pro-quality",
    "name": "ToAPIs Doubao SeeDance 1.0 Pro Quality",
    "provider": "toapis",
    "api_model": "doubao-seedance-1-0-pro-quality",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 10,
    "max_ref_images": 2,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_ref_task_type": "i2v",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "gemini_omni_flash",
    "name": "ToAPIs Gemini Omni Flash",
    "provider": "toapis",
    "api_model": "gemini_omni_flash",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 6,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "grok-video-1.5-preview",
    "name": "ToAPIs Grok Video 1.5 Preview",
    "provider": "toapis",
    "api_model": "grok-video-1.5-preview",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 10,
    "max_duration": 15,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 2.0,
    "price_unit": "credits",
    "price_status": "configured",
    "price_note": "Official docs price 10s at $0.10 and 15s at $0.15; ToAPIs credits use 1 USD = 200 credits, so this is 2 credits/s.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "images",
    "toapis_duration_payload": "seconds",
    "toapis_aspect_payload": "aspect_ratio",
    "min_ref_images": 1,
    "duration_choices": [
      10,
      15
    ],
    "default_price_per_second": 2
  },
  {
    "id": "grok-video-3",
    "name": "ToAPIs Grok Video 3",
    "provider": "toapis",
    "api_model": "grok-video-3",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 6,
    "max_duration": 15,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16",
      "3:2",
      "2:3",
      "1:1"
    ],
    "supported_resolutions": [
      "480p",
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "images",
    "toapis_duration_payload": "seconds",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      6,
      10,
      15
    ]
  },
  {
    "id": "happyhorse-1.0",
    "name": "ToAPIs HappyHorse 1.0",
    "provider": "toapis",
    "api_model": "happyhorse-1.0",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 15,
    "max_ref_images": 9,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "kling-v2-6",
    "name": "ToAPIs Kling v2.6",
    "provider": "toapis",
    "api_model": "kling-v2-6",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 5,
    "max_duration": 10,
    "max_ref_images": 3,
    "supported_aspect_ratios": [
      "16:9",
      "9:16",
      "1:1"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "reference_images",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      5,
      10
    ],
    "toapis_mode_from_resolution": true
  },
  {
    "id": "kling-3.0-turbo",
    "name": "ToAPIs Kling 3.0 Turbo",
    "provider": "toapis",
    "api_model": "kling-3.0-turbo",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 15,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16",
      "1:1"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "reference_images",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "kling-v3",
    "name": "ToAPIs Kling v3",
    "provider": "toapis",
    "api_model": "kling-v3",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 15,
    "max_ref_images": 3,
    "supported_aspect_ratios": [
      "16:9",
      "9:16",
      "1:1"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "reference_images",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "toapis_mode_from_resolution": true
  },
  {
    "id": "kling-v3-omni",
    "name": "ToAPIs Kling v3 Omni",
    "provider": "toapis",
    "api_model": "kling-v3-omni",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 5,
    "max_duration": 10,
    "max_ref_images": 3,
    "supported_aspect_ratios": [
      "16:9",
      "9:16",
      "1:1"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "metadata_image_list",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      5,
      10
    ],
    "toapis_mode_from_resolution": true,
    "toapis_prompt_image_tokens": true
  },
  {
    "id": "kling-video-o1",
    "name": "ToAPIs Kling Video O1",
    "provider": "toapis",
    "api_model": "kling-video-o1",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 5,
    "max_duration": 10,
    "max_ref_images": 3,
    "supported_aspect_ratios": [
      "16:9",
      "9:16",
      "1:1"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "metadata_image_list",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      5,
      10
    ],
    "toapis_mode_from_resolution": true,
    "toapis_prompt_image_tokens": true
  },
  {
    "id": "MiniMax-Hailuo-2.3",
    "name": "ToAPIs MiniMax Hailuo 2.3",
    "provider": "toapis",
    "api_model": "MiniMax-Hailuo-2.3",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 6,
    "max_duration": 10,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "768p",
      "1080p"
    ],
    "default_resolution": "768p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      6,
      10
    ]
  },
  {
    "id": "MiniMax-Hailuo-2.3-Fast",
    "name": "ToAPIs MiniMax Hailuo 2.3 Fast",
    "provider": "toapis",
    "api_model": "MiniMax-Hailuo-2.3-Fast",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 6,
    "max_duration": 10,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "768p",
      "1080p"
    ],
    "default_resolution": "768p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      6,
      10
    ]
  },
  {
    "id": "MiniMax-Hailuo-02",
    "name": "ToAPIs MiniMax Hailuo 02",
    "provider": "toapis",
    "api_model": "MiniMax-Hailuo-02",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 6,
    "max_duration": 10,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "768p",
      "1080p"
    ],
    "default_resolution": "768p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      6,
      10
    ]
  },
  {
    "id": "seedance-2",
    "name": "ToAPIs Seedance 2",
    "provider": "toapis",
    "api_model": "seedance-2",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 15,
    "max_ref_images": 9,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "seedance-2-fast",
    "name": "ToAPIs Seedance 2 Fast",
    "provider": "toapis",
    "api_model": "seedance-2-fast",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 10,
    "max_ref_images": 9,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "seedance-2-mini",
    "name": "ToAPIs Seedance 2 Mini",
    "provider": "toapis",
    "api_model": "seedance-2-mini",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 10,
    "max_ref_images": 9,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "sora-2-official",
    "name": "ToAPIs Azure Sora 2 Official",
    "provider": "toapis",
    "api_model": "sora-2-official",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 12,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      4,
      8,
      12
    ]
  },
  {
    "id": "sora-2-vvip",
    "name": "ToAPIs Sora 2 VVIP",
    "provider": "toapis",
    "api_model": "sora-2-vvip",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 12,
    "max_ref_images": 3,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      4,
      8,
      12
    ]
  },
  {
    "id": "Veo3.1-quality-official",
    "name": "ToAPIs Veo 3.1 Quality Official",
    "provider": "toapis",
    "api_model": "Veo3.1-quality-official",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 4,
    "max_duration": 8,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p",
      "4k"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "size",
    "duration_choices": [
      4,
      6,
      8
    ]
  },
  {
    "id": "veo3.1-fast",
    "name": "Veo 3.1 Fast",
    "provider": "toapis",
    "api_model": "veo3.1-fast",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 8,
    "max_duration": 8,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "toapis_resolution_payload": "metadata",
    "duration_choices": [
      8
    ]
  },
  {
    "id": "veo3.1-lite",
    "name": "Veo 3.1 Lite",
    "provider": "toapis",
    "api_model": "veo3.1-lite",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 8,
    "max_duration": 8,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "toapis_resolution_payload": "metadata",
    "duration_choices": [
      8
    ]
  },
  {
    "id": "veo3.1-quality",
    "name": "Veo 3.1 Quality",
    "provider": "toapis",
    "api_model": "veo3.1-quality",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 8,
    "max_duration": 8,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p",
      "4k"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "toapis_resolution_payload": "metadata",
    "duration_choices": [
      8
    ]
  },
  {
    "id": "toapis-viduq3-pro",
    "name": "ToAPIs Vidu Q3 Pro",
    "provider": "toapis",
    "api_model": "viduq3-pro",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 16,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "toapis-viduq3-turbo",
    "name": "ToAPIs Vidu Q3 Turbo",
    "provider": "toapis",
    "api_model": "viduq3-turbo",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 16,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio"
  },
  {
    "id": "toapis-viduq3",
    "name": "ToAPIs Vidu Q3 Reference",
    "provider": "toapis",
    "api_model": "viduq3",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 3,
    "max_duration": 16,
    "max_ref_images": 7,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "540p",
      "720p",
      "1080p"
    ],
    "default_resolution": "720p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "min_ref_images": 1
  },
  {
    "id": "wan2.6",
    "name": "ToAPIs Wan 2.6",
    "provider": "toapis",
    "api_model": "wan2.6",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 5,
    "max_duration": 10,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "1080p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "duration_choices": [
      5,
      10
    ]
  },
  {
    "id": "wan2.6-flash",
    "name": "ToAPIs Wan 2.6 Flash",
    "provider": "toapis",
    "api_model": "wan2.6-flash",
    "supports_ref_video": false,
    "supports_ref_images": true,
    "min_duration": 5,
    "max_duration": 10,
    "max_ref_images": 1,
    "supported_aspect_ratios": [
      "16:9",
      "9:16"
    ],
    "supported_resolutions": [
      "720p",
      "1080p"
    ],
    "default_resolution": "1080p",
    "limit_note": "ToAPIs async video model. Use public image URLs; exact billing is shown when credit price is configured.",
    "supported_modes": [
      "generate"
    ],
    "price_per_second": 0,
    "price_unit": "credits",
    "price_status": "unpriced",
    "price_note": "ToAPIs balance is tracked in credits. Public docs do not expose a stable credits-per-second price for this model; configure toapis_video_credit_prices as JSON to enable estimates.",
    "toapis_credits_per_usd": 200,
    "toapis_ref_image_payload": "image_urls",
    "toapis_duration_payload": "duration",
    "toapis_aspect_payload": "aspect_ratio",
    "min_ref_images": 1,
    "duration_choices": [
      5,
      10
    ]
  }
]
