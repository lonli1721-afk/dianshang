import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Boxes,
  Clapperboard,
  FileVideo,
  Image as ImageIcon,
  ListChecks,
  Mic2,
  Package,
  Play,
  Plus,
  RefreshCw,
  Scissors,
  Sparkles,
  Trash2,
  Upload,
  Video,
  Wand2,
} from 'lucide-react'
import { api } from '../services/api'
import { assetUrl } from './image-toolbox/helpers'
import { useGameTaskPolling } from './game/useGameTaskPolling'
import { FALLBACK_VIDEO_MODELS } from './game/gameVideoConstants'

const DEFAULT_LANGUAGE_MODELS = [
  { id: 'doubao-seed-2-0-pro-260215', name: 'Doubao Seed 2.0 Pro', available: true },
  { id: 'doubao-seed-2-0-mini', name: 'Doubao Seed 2.0 Mini', available: false },
  { id: 'doubao-seed-2-0-lite', name: 'Doubao Seed 2.0 Lite', available: false },
]

const DEFAULT_IMAGE_MODELS = [
  { id: 'image2', name: 'Image2 产品还原', provider: 'toapis', available: true },
  { id: 'seedream-5.0', name: 'Seedream 5.0', provider: 'jimeng', available: true },
  { id: 'seedream-4.5', name: 'Seedream 4.5', provider: 'jimeng', available: true },
  { id: 'nanobanana', name: 'Nano Banana', provider: 'custom_image', available: false },
]

const IMAGE2_REFERENCE_LIMIT = 16

const BATCH_NATIVE_VIDEO_MODEL_IDS = new Set(['seedance-2.0', 'happyhorse-1.0-i2v', 'happyhorse-1.0-t2v'])
const DEFAULT_VIDEO_MODELS = FALLBACK_VIDEO_MODELS
  .filter(model => BATCH_NATIVE_VIDEO_MODEL_IDS.has(model.id) || model.provider === 'toapis')
  .map(model => ({ ...model, available: true }))

const ASPECT_OPTIONS = ['9:16', '16:9', '1:1', '4:3', '3:4']
const DURATION_OPTIONS = [4, 5, 6, 8, 10, 12, 15]
const DEFAULT_STORYBOARD_SCENE_COUNT = 6
const VEO_STORYBOARD_SCENE_COUNT = 4
const VEO_STORYBOARD_DURATION = 8
const WORKBENCH_DRAFT_STORAGE_KEY = 'ecommerce-batch-video-workbench-draft-v1'
const PRODUCT_MEMORY_STORAGE_KEY = 'ecommerce-batch-video-product-memory-v1'
const PRODUCT_MEMORY_CACHE_LIMIT = 80
const DEFAULT_STORYBOARD_CREATIVE_BRIEF = '请根据上面的卖点，为我写6段5s的电商广告视频，分镜图片和视频提示词都按 Seedance 风格生成。'
const VIDEO_SOUND_RULE = '【声音规则】生成单段视频时不要旁白、配音、人声或口播；不要唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点；只保留真实现场音效，例如脚步声、风声、水花声、材质与地面轻微摩擦声。'
const DEFAULT_VOICEOVER_TEXT = '让每一步，都更可靠。'
const TTS_VOICE_OPTIONS = [
  { id: '', label: '后台默认音色' },
  { id: 'zh_male_yunxi_moon_bigtts', label: '云希男声（清爽广告）' },
  { id: 'zh_female_qingxin_mars_bigtts', label: '清新女声' },
  { id: 'zh_female_wanwanxiaohe_moon_bigtts', label: '湾湾小何女声' },
  { id: 'custom', label: '自定义 voice_type' },
]

const PRODUCTION_MATRIX_ANGLES = [
  {
    id: 'trail_motion',
    label: '山野行进',
    imagePrompt: '清晨山路、林间逆光、脚步正在向前，产品自然处在运动节奏里，画面像户外品牌主视觉。',
    videoPrompt: '用连续脚步、贴地跟拍和自然呼吸感承载卖点，让产品在真实行进中显得可靠、有速度感。',
  },
  {
    id: 'material_closeup',
    label: '材质呼吸',
    imagePrompt: '产品关键材质、纹理、水珠、鞋底或包边被自然光扫过，微距高级但不说明书化。',
    videoPrompt: '用慢推、扫光、浅景深和材质声把卖点拍得有触感，细节服务画面气质而不是硬讲功能。',
  },
  {
    id: 'water_crossing',
    label: '溪流穿越',
    imagePrompt: '浅水、湿石、水花和逆光水雾中，产品随着脚步穿过画面，运动感自然、高级、清爽。',
    videoPrompt: '用踩水、掠过湿石、水珠飞起和镜头贴地跟随，让防滑、防水或轻便感自然发生在画面里。',
  },
  {
    id: 'lifestyle',
    label: '户外生活',
    imagePrompt: '营地、木栈道、晨雾、风和步伐形成自然生活方式画面，产品不摆拍但始终是视觉主角。',
    videoPrompt: '用出发、行走、停顿、看向远处等自然动作串联卖点，像品牌生活方式短片。',
  },
  {
    id: 'hero_low_angle',
    label: '低机位英雄',
    imagePrompt: '低机位贴近地面，产品占据画面主视觉，背景有山路、风、水花或尘土的动势。',
    videoPrompt: '用低机位跟拍、轻微手持和产品擦过镜头的运动感，让卖点藏在有力量的脚步里。',
  },
  {
    id: 'speed_sweep',
    label: '速度掠影',
    imagePrompt: '产品从自然光和户外背景中快速掠过，水珠、尘土或风带出运动速度，画面干净利落。',
    videoPrompt: '用横移、跟拍、轻微运动模糊和短暂停顿，让卖点通过速度、节奏和身体动作被感知。',
  },
]

const PRODUCTION_MATRIX_MOODS = [
  {
    id: 'hardcore',
    label: '硬朗户外',
    imagePrompt: '画面真实克制，山路、水雾、尘土和自然光让产品有专业户外品牌质感。',
    videoPrompt: '节奏干净有力量，动作真实但不做测试感，把卖点融进运动状态。',
  },
  {
    id: 'cinematic',
    label: '电影感',
    imagePrompt: '自然光影、浅景深、逆光轮廓、干净构图，画面有高级品牌广告片质感。',
    videoPrompt: '镜头运动平稳，光影层次丰富，氛围高级但产品信息清楚，像品牌主视觉短片。',
  },
  {
    id: 'handheld',
    label: '真实手持',
    imagePrompt: '轻微手持记录感，像真实用户现场拍摄，但构图专业、产品清晰。',
    videoPrompt: '保留轻微手持动势和即时反馈，强调真实体验和可信记录。',
  },
  {
    id: 'clean_ecommerce',
    label: '高级电商',
    imagePrompt: '背景简洁但有电影光影，产品突出、构图规整，像高端商品广告主视觉。',
    videoPrompt: '画面清爽，动作简洁，产品信息清楚，但整体仍然是高级运动广告片。',
  },
  {
    id: 'social_pop',
    label: '社媒爆款',
    imagePrompt: '开场抓眼、主体明确、动作干净利落，适合短视频信息流。',
    videoPrompt: '前段强钩子，中段快速展示卖点，节奏更短更明确。',
  },
]

const DEFAULT_PRODUCTION_MATRIX = {
  angleIds: ['trail_motion', 'material_closeup', 'water_crossing'],
  moodIds: ['hardcore', 'cinematic'],
  scenesPerCombination: 1,
  maxScenes: 18,
}

const DEFAULT_PRODUCT = {
  name: '',
  category: '',
  description: '',
  imageUrls: [],
  detailSheetUrl: '',
  detailSheetPrompt: '',
  detailSheetHistory: [],
}

function makeVersionItem(url, meta = {}) {
  const cleanUrl = String(url || '').trim()
  if (!cleanUrl) return null
  return {
    id: meta.id || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    url: cleanUrl,
    prompt: String(meta.prompt || ''),
    label: String(meta.label || ''),
    source: String(meta.source || ''),
    taskId: String(meta.taskId || ''),
    createdAt: meta.createdAt || new Date().toISOString(),
  }
}

function mergeVersionHistory(history, item, limit = 12) {
  const items = Array.isArray(history) ? history.filter(entry => entry?.url) : []
  if (!item?.url) return items.slice(0, limit)
  const next = [item, ...items.filter(entry => entry.url !== item.url)]
  return next.slice(0, limit)
}

function normalizeVersionItem(item) {
  if (!item) return null
  if (typeof item === 'string') return makeVersionItem(item)
  if (typeof item !== 'object') return null
  return makeVersionItem(item.url || item.image_url || item.video_url, item)
}

function normalizeVersionHistory(history, currentUrl = '') {
  const items = Array.isArray(history)
    ? history.map(normalizeVersionItem).filter(Boolean)
    : []
  if (currentUrl && !items.some(item => item.url === currentUrl)) {
    items.unshift(makeVersionItem(currentUrl, { source: 'current' }))
  }
  return items
}

function clampInteger(value, min, max, fallback) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.max(min, Math.min(max, Math.round(number)))
}

function clampNumber(value, min, max, fallback) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.max(min, Math.min(max, number))
}

function normalizeIdSelection(values, options, fallbackIds) {
  const allowed = new Set(options.map(item => item.id))
  const selected = Array.isArray(values)
    ? values.filter(id => allowed.has(id))
    : []
  return selected.length ? selected : fallbackIds.filter(id => allowed.has(id))
}

function normalizeProductionMatrix(raw) {
  const source = raw && typeof raw === 'object' ? raw : {}
  return {
    angleIds: normalizeIdSelection(source.angleIds, PRODUCTION_MATRIX_ANGLES, DEFAULT_PRODUCTION_MATRIX.angleIds),
    moodIds: normalizeIdSelection(source.moodIds, PRODUCTION_MATRIX_MOODS, DEFAULT_PRODUCTION_MATRIX.moodIds),
    scenesPerCombination: clampInteger(source.scenesPerCombination, 1, 3, DEFAULT_PRODUCTION_MATRIX.scenesPerCombination),
    maxScenes: clampInteger(source.maxScenes, 1, 60, DEFAULT_PRODUCTION_MATRIX.maxScenes),
  }
}

function parseStoryboardCreativeBrief(text) {
  const value = String(text || '')
  const countMatch = value.match(/(\d{1,2})\s*(?:段|条|个)\s*(?:分镜|镜头|视频|片段)?/)
    || value.match(/(?:分镜|镜头|视频|片段)\s*(\d{1,2})\s*(?:段|条|个)?/)
  const durationMatch = value.match(/(\d{1,2})\s*(?:s|S|秒)/)
  return {
    sceneCount: countMatch ? Number(countMatch[1]) : null,
    duration: durationMatch ? Number(durationMatch[1]) : null,
  }
}

function toggleSelectedId(values, id) {
  const list = Array.isArray(values) ? values : []
  if (list.includes(id)) {
    return list.length > 1 ? list.filter(item => item !== id) : list
  }
  return [...list, id]
}

function createDefaultDraft() {
  const productionMatrix = normalizeProductionMatrix(DEFAULT_PRODUCTION_MATRIX)
  return {
    product: { ...DEFAULT_PRODUCT, imageUrls: [] },
    languageModel: DEFAULT_LANGUAGE_MODELS[0].id,
    imageModel: DEFAULT_IMAGE_MODELS[0].id,
    videoModel: DEFAULT_VIDEO_MODELS[0].id,
    videoResolution: '720p',
    aspectRatio: '9:16',
    duration: 5,
    variantCount: DEFAULT_STORYBOARD_SCENE_COUNT,
    liveVideo: null,
    transcript: '',
    manualSellingPoints: '',
    sellingPoints: [],
    storyboardCreativeBrief: DEFAULT_STORYBOARD_CREATIVE_BRIEF,
    storyboardReferences: [],
    productionMatrix,
    scenes: [],
    batchResult: null,
    finalVideo: null,
    finalClips: [],
    ttsVoiceType: '',
    ttsCustomVoiceType: '',
    ttsSpeedRatio: 1,
    bgmEnabled: true,
    bgmUrl: '',
    bgmName: '',
    bgmVolume: 0.45,
    productPosterUrl: '',
    productPosterPrompt: '',
    productPosterHistory: [],
  }
}

function buildWorkbenchDraftSnapshot({
  product,
  languageModel,
  imageModel,
  videoModel,
  videoResolution,
  aspectRatio,
  duration,
  variantCount,
  liveVideo,
  transcript,
  manualSellingPoints,
  sellingPoints,
  storyboardCreativeBrief,
  storyboardReferences,
  productionMatrix,
  scenes,
  batchResult,
  finalVideo,
  finalClips,
  ttsVoiceType,
  ttsCustomVoiceType,
  ttsSpeedRatio,
  bgmEnabled,
  bgmUrl,
  bgmName,
  bgmVolume,
  productPosterUrl,
  productPosterPrompt,
  productPosterHistory,
}) {
  return {
    product,
    languageModel,
    imageModel,
    videoModel,
    videoResolution,
    aspectRatio,
    duration,
    variantCount,
    liveVideo,
    transcript,
    manualSellingPoints,
    sellingPoints,
    storyboardCreativeBrief,
    storyboardReferences,
    productionMatrix,
    scenes,
    batchResult,
    finalVideo,
    finalClips,
    ttsVoiceType,
    ttsCustomVoiceType,
    ttsSpeedRatio,
    bgmEnabled,
    bgmUrl,
    bgmName,
    bgmVolume,
    productPosterUrl,
    productPosterPrompt,
    productPosterHistory,
  }
}

function readMediaUrl(result) {
  if (!result) return ''
  if (typeof result === 'string') return result
  if (result.url) return result.url
  if (result.image_url) return result.image_url
  if (result.videoUrl) return result.videoUrl
  if (result.video_url) return result.video_url
  if (Array.isArray(result.images) && result.images[0]?.url) return result.images[0].url
  if (Array.isArray(result.videos) && result.videos[0]?.url) return result.videos[0].url
  return ''
}

function displayError(error) {
  const raw = error?.message || String(error || '')
  try {
    const parsed = JSON.parse(raw)
    return parsed?.detail || parsed?.message || parsed?._error || raw
  } catch {
    return raw
  }
}

function isCompletedTaskStatus(status) {
  return ['completed', 'succeeded', 'success'].includes(String(status || '').toLowerCase())
}

function isProcessingTaskStatus(status) {
  return ['processing', 'generating', 'queued', 'pending', 'running', 'video_generating'].includes(String(status || '').toLowerCase())
}

function normalizeProgressValue(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  const ratio = number > 1 ? number / 100 : number
  return Math.max(0, Math.min(1, ratio))
}

function estimateVideoProgress(scene) {
  const direct = normalizeProgressValue(scene?.videoProgress ?? scene?.progress)
  if (direct != null) return direct
  if (!isProcessingTaskStatus(scene?.status)) return 0
  const startedAt = Number(scene?.videoStartedAt || 0)
  if (!startedAt) return 0.08
  const elapsedSeconds = Math.max(0, (Date.now() - startedAt) / 1000)
  return Math.max(0.08, Math.min(0.92, elapsedSeconds / 180))
}

function formatElapsedSeconds(startedAt) {
  const start = Number(startedAt || 0)
  if (!start) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}m ${String(rest).padStart(2, '0')}s`
}

function videoStatusText(scene) {
  const status = String(scene?.status || '').toLowerCase()
  if (status === 'queued' || status === 'pending') return '排队中'
  if (status === 'running' || status === 'processing' || status === 'generating' || status === 'video_generating') return '生成中'
  if (status === 'completed' || status === 'success' || status === 'succeeded') return '已完成'
  if (status === 'failed') return '生成失败'
  return '等待生成'
}

function isRetryableVideoResultError(error) {
  const text = displayError(error)
  return (
    text.includes('未返回视频地址')
    || text.includes('上游未返回')
    || text.includes('结果视频保存到本地失败')
    || text.includes('任务已完成但未返回视频地址')
  )
}

function videoSlotText(scene) {
  if (scene?.taskId && isProcessingTaskStatus(scene.status)) return '视频生成中，完成后会自动显示'
  if (scene?.taskId && isRetryableVideoResultError(scene.error)) return '已完成但未取回视频地址，可重新拉取结果'
  return '生成视频后显示在这里'
}

function VideoProgress({ scene }) {
  if (!isProcessingTaskStatus(scene?.status)) return null
  const progress = estimateVideoProgress(scene)
  const percent = Math.max(1, Math.round(progress * 100))
  const elapsed = formatElapsedSeconds(scene.videoStartedAt)
  return (
    <div className="batch-video-progress">
      <div className="batch-video-progress-head">
        <strong>{videoStatusText(scene)}</strong>
        <span>{percent}%{elapsed ? ` · ${elapsed}` : ''}</span>
      </div>
      <div className="batch-video-progress-track" aria-label={`视频生成进度 ${percent}%`}>
        <span style={{ width: `${percent}%` }} />
      </div>
      <small>{scene.videoProgressMessage || (scene.taskId ? `任务 ${scene.taskId}` : '正在提交生成任务')}</small>
    </div>
  )
}

function splitLines(text) {
  return String(text || '')
    .split(/\n|；|;/)
    .map(item => item.trim())
    .filter(Boolean)
}

function stripVoiceoverPromptBlocks(text) {
  return String(text || '')
    .replace(/【旁白】[\s\S]*?(?=【|$)/g, ' ')
    .replace(/旁白(?:内容)?[:：]\s*[“"']?[^。；\n”"']+[”"']?(?:[。；\n]|$)/g, ' ')
    .replace(/加入一条[^。；\n]*(?:旁白|配音|口播|人声)[^。；\n]*(?:[。；\n]|$)/g, ' ')
    .replace(/声音只能由真实现场音效和一条普通话广告旁白组成[^。；\n]*(?:[。；\n]|$)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function extractVoiceoverText(text, fallback = '') {
  const value = String(text || '')
  const quoted = value.match(/【旁白】[\s\S]*?[“"]([^”"]{4,80})[”"]/)
    || value.match(/旁白(?:内容)?[:：]\s*[“"]([^”"]{4,80})[”"]/)
  if (quoted?.[1]) return quoted[1].trim()
  const plain = value.match(/【旁白】\s*([^【\n。；]{4,80})/)
    || value.match(/旁白(?:内容)?[:：]\s*([^。；\n]{4,80})/)
  return (plain?.[1] || fallback || '').trim()
}

function buildDefaultVoiceover(scene, index = 0) {
  if (scene?.referenceMode === 'product_detail' || scene?.reference_mode === 'product_detail') {
    const productName = scene?.productName || scene?.product_name || ''
    return productName || ''
  }
  const point = scene?.selling_point || scene?.sellingPoint || scene?.hook || scene?.title || ''
  const cleanPoint = String(point || '').replace(/^\d+[.、]\s*/, '').split(/[：:·]/).pop()?.trim()
  if (cleanPoint) return `${cleanPoint}，随每一步自然发生。`
  return index === 0 ? DEFAULT_VOICEOVER_TEXT : `第 ${index + 1} 个场景，让产品优势自然被看见。`
}

function normalizeClipTime(value) {
  if (value === '' || value == null) return ''
  const number = Number(value)
  if (!Number.isFinite(number)) return ''
  return Math.max(0, Number(number.toFixed(2)))
}

function videoVersionOptionsForScene(scene) {
  if (!scene) return []
  return normalizeVersionHistory(scene.videoHistory || scene.video_history, scene.video_url)
}

function createFinalClipFromScene(scene, index = 0, version = null) {
  const selectedVersion = version?.url ? version : videoVersionOptionsForScene(scene)[0]
  if (!selectedVersion?.url) return null
  const voiceoverText = scene.voiceover_text || scene.voiceoverText || scene.voiceover || buildDefaultVoiceover(scene, index)
  return {
    id: `clip_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    sceneId: scene.id || `scene_${index}`,
    title: scene.title || `分镜 ${index + 1}`,
    videoUrl: selectedVersion.url,
    sourceLabel: selectedVersion.label || selectedVersion.source || '',
    startTime: 0,
    endTime: '',
    voiceoverText,
    subtitle: voiceoverText,
  }
}

function normalizeFinalClip(clip, index = 0, scenes = []) {
  if (!clip || typeof clip !== 'object') return null
  const sceneId = String(clip.sceneId || clip.scene_id || '')
  const scene = scenes.find(item => item.id === sceneId) || scenes[index] || {}
  const videoUrl = String(clip.videoUrl || clip.video_url || clip.url || '').trim()
    || String(scene.video_url || '').trim()
  const hasVoiceoverValue = Object.prototype.hasOwnProperty.call(clip, 'voiceoverText')
    || Object.prototype.hasOwnProperty.call(clip, 'voiceover_text')
    || Object.prototype.hasOwnProperty.call(clip, 'subtitle')
  const voiceoverText = hasVoiceoverValue
    ? String(clip.voiceoverText ?? clip.voiceover_text ?? clip.subtitle ?? '').trim()
    : (String(scene.voiceover_text || '').trim() || buildDefaultVoiceover(scene, index))
  const startTime = normalizeClipTime(clip.startTime ?? clip.start_time)
  const endTime = normalizeClipTime(clip.endTime ?? clip.end_time)
  return {
    id: String(clip.id || `clip_${Date.now()}_${index}`),
    sceneId: sceneId || scene.id || '',
    title: String(clip.title || scene.title || `片段 ${index + 1}`),
    videoUrl,
    sourceLabel: String(clip.sourceLabel || clip.source_label || ''),
    startTime,
    endTime: endTime !== '' && startTime !== '' && endTime <= startTime ? '' : endTime,
    voiceoverText,
    subtitle: hasVoiceoverValue ? voiceoverText : String(clip.subtitle || voiceoverText),
  }
}

function buildDefaultFinalClips(scenes) {
  return (Array.isArray(scenes) ? scenes : [])
    .map((scene, index) => createFinalClipFromScene(scene, index))
    .filter(Boolean)
}

function modelLabel(model) {
  const suffix = model.available === false ? '（待接入）' : ''
  const price = videoModelPriceText(model)
  return `${model.name || model.id}${suffix}${price ? ` · ${price}` : ''}`
}

function providerForModel(modelId, models, fallback) {
  return models.find(item => item.id === modelId)?.provider || fallback
}

function isUnsupportedModel(modelId, models) {
  const model = models.find(item => item.id === modelId)
  return model?.available === false
}

function isVeoModel(modelId) {
  return String(modelId || '').startsWith('veo3.1-')
}

function isFixedEightSecondModel(model) {
  return Number(model?.min_duration || 0) === VEO_STORYBOARD_DURATION
    && Number(model?.max_duration || 0) === VEO_STORYBOARD_DURATION
}

function priceUnitLabel(unit) {
  const normalized = String(unit || '').toLowerCase()
  if (normalized === 'credits') return '积分'
  if (normalized === 'cny') return '元'
  return unit || ''
}

function videoModelPriceText(model) {
  if (!model) return ''
  const unit = priceUnitLabel(model.price_unit)
  const price = Number(model.price_per_second || 0)
  if (!price) {
    return model.price_unit === 'credits' ? '积分价未配置' : ''
  }
  return `${Number.isInteger(price) ? price : Number(price.toFixed(2))}${unit}/秒`
}

function videoModelRequestedDuration(model, fallbackDuration) {
  const min = Number(model?.min_duration || 0)
  const max = Number(model?.max_duration || 0)
  if (min > 0 && min === max) return min
  const choices = Array.isArray(model?.duration_choices) ? model.duration_choices.map(Number).filter(Boolean) : []
  if (choices.length) {
    return choices.includes(Number(fallbackDuration)) ? Number(fallbackDuration) : choices[0]
  }
  return Number(fallbackDuration || model?.max_duration || 5)
}

function videoModelResolutionOptions(model) {
  const options = Array.isArray(model?.supported_resolutions)
    ? model.supported_resolutions.map(item => String(item || '').trim()).filter(Boolean)
    : []
  return options.length ? options : ['720p']
}

function estimateVideoModelCost(model, fallbackDuration) {
  const price = Number(model?.price_per_second || 0)
  const priceUnit = String(model?.price_unit || '').toLowerCase()
  const pricePerSecondCny = Number(model?.estimated_price_per_second_cny || 0) || (priceUnit === 'cny' ? price : 0)
  if (!price) return null
  const seconds = videoModelRequestedDuration(model, fallbackDuration)
  return {
    amount: Number((price * seconds).toFixed(2)),
    amountCny: pricePerSecondCny > 0 ? Number((pricePerSecondCny * seconds).toFixed(2)) : 0,
    pricePerSecondCny,
    seconds,
    unit: priceUnitLabel(model.price_unit),
  }
}

function formatCurrencyCny(amount) {
  const number = Number(amount || 0)
  if (!number) return ''
  return `¥${Number.isInteger(number) ? number : number.toFixed(2)}`
}

function storyboardDefaultsForVideoModel(modelId, models = DEFAULT_VIDEO_MODELS) {
  const model = models.find(item => item.id === modelId)
  return isFixedEightSecondModel(model) || isVeoModel(modelId)
    ? { count: VEO_STORYBOARD_SCENE_COUNT, duration: VEO_STORYBOARD_DURATION }
    : { count: DEFAULT_STORYBOARD_SCENE_COUNT, duration: 5 }
}

function normalizeVeoAspectRatio(value) {
  return value === '16:9' || value === '9:16' ? value : '9:16'
}

function sanitizeStoryboardPromptText(text) {
  const staleVoiceoverBlocks = [
    /【声音规则】[^。]*。?/g,
    /声音规则[:：][^。]*。?/g,
    /【旁白】[\s\S]*?(?=【|$)/g,
    /旁白(?:内容)?[:：]\s*[“"']?[^。；\n”"']+[”"']?(?:[。；\n]|$)/g,
    /【声音限制】[^。]*(?:背景音乐|BGM|bgm|配乐|音乐节奏|轻音乐|鼓点|现场音效|旁白)[^。]*。?/g,
    /【声音限制】不要生成[^。]*(?:旁白|配音|语音音轨)[^。]*。?/g,
    /不要生成[^。；]*(?:旁白|配音|语音音轨)[^。；]*(?:[。；]|$)/g,
    /不要出现[^。；]*(?:说话的人|主播|口播)[^。；]*(?:[。；]|$)/g,
    /只保留真实现场环境音[^。；]*(?:[。；]|$)/g,
    /不要(?:生成|出现|加入|使用|有)?[^。；]*(?:背景音乐|BGM|bgm|配乐|音乐节奏|轻音乐|鼓点)[^。；]*(?:[。；]|$)/g,
  ]
  const baseText = staleVoiceoverBlocks.reduce(
    (value, pattern) => value.replace(pattern, ''),
    stripVoiceoverPromptBlocks(text),
  )
  const replacements = {
    不出现主播: '',
    禁止主播: '',
    无人物主播: '',
    主播: '产品实测动作',
    配音: '',
    人声解说: '',
    口播: '',
    主播声音: '',
    BGM: '现场音效',
    bgm: '现场音效',
    背景音乐: '现场音效',
    配乐: '现场音效',
    轻音乐节奏: '现场音效',
    轻音乐: '现场音效',
    音乐节奏: '现场音效',
    低频户外广告鼓点: '现场音效',
    低频鼓点: '现场音效',
    鼓点: '现场音效',
    直播间: '户外自然环境',
    直播带货: '户外功能广告',
    带货: '功能展示',
    真人讲解: '产品细节展示',
    手机下单: '产品细节定格',
    购物车: '产品细节',
    购物界面: '产品细节',
    购买按钮: '产品细节',
    购买画面: '产品定格画面',
    点击下单: '产品定格',
    价格促销: '卖点',
    促销文案: '卖点',
    促销: '卖点',
    价格: '卖点',
    CTA: '卖点',
  }
  return Object.entries(replacements).reduce(
    (value, [source, target]) => value.replaceAll(source, target),
    baseText,
  ).replace(/\s+/g, ' ').trim()
}

const STORYBOARD_LEGACY_TERMS = [
  '新旧',
  '旧鞋',
  '旧鞋底',
  '磨损差异',
  '并排摆放',
  '湿滑瓷砖',
  '瓷砖',
  '实验室',
  '硬测评',
  '测评',
  '防滑挑战',
  '耐磨挑战',
  '功能挑战',
  '功能测试',
  '测试画面',
  '证明画面',
  '证据画面',
  '痛点反转',
  '反差画面',
]

function legacyNeutralText(text) {
  return String(text || '').replace(
    /(?:不|不要|不能|禁止|避免|杜绝|拒绝)[^。；\n]*(?:对比|反差|痛点|证明|证据|测试|挑战|旧鞋|新旧|瓷砖|实验室|测评)[^。；\n]*(?:[。；\n]|$)/g,
    ' ',
  )
}

function hasLegacyStoryboardLogic(text) {
  const neutral = legacyNeutralText(text)
  return STORYBOARD_LEGACY_TERMS.some(term => neutral.includes(term))
}

function buildAdFilmImagePrompt(scene, index) {
  const point = scene?.selling_point || scene?.sellingPoint || scene?.title || `卖点 ${index + 1}`
  return [
    `【首帧分镜 ${index + 1}】高级运动户外品牌广告大片，围绕“${point}”设计同一段视频的首帧。`,
    '场景为真实山路、湿石、浅水、林间自然光或户外行进环境，产品是英雄主体，低机位或贴地近景，脚步正在自然向前。',
    '【穿着状态】如果画面包含脚步、行走、奔跑、踩水、转向、贴地跟拍等穿着使用动作，首帧图片必须有人穿着当前产品，出现真人脚部/下肢与产品的真实穿着关系；不要生成空鞋、孤立产品或静物摆拍。',
    '画面用运动动作、自然光影、水雾、尘土或材质微距承载卖点，不做对比、不做测评式演示、不做说明书展示。',
    '产品外观完全以参考图为准，外观细节不在文字里二次发挥。',
  ].join(' ')
}

function buildAdFilmVideoPrompt(scene, index) {
  const point = scene?.selling_point || scene?.sellingPoint || scene?.title || `卖点 ${index + 1}`
  return [
    '【技术参数】9:16，8秒，24fps，高级运动户外品牌广告大片，真实自然光，浅景深。',
    '【参考素材】@图片1就是本分镜首帧，负责整段8秒的场景、构图、光线和动作起点；整段必须保持同一产品、同一户外品牌广告气质，不切换到测评或实验化场景。',
    `【视频目标】围绕“${point}”，只拍当前这双鞋在户外运动中的状态，让卖点通过脚步、转向、水花、碎石、风声、材质细节和身体动作自然被感知。`,
    '【时间戳分镜】0-8秒：一个连贯的高级户外广告镜头，低机位贴地或手持跟随脚步进入，湿石、浅水、尘土或林间光影掠过；镜头可以从动作近景自然推进到产品英雄近景、材质微距或鞋底/轮廓样式镜头，但不要切换成第二个场景，结尾收束回产品本身的样式、轮廓、材质和广告主视觉。',
    '【音效】只允许真实现场音效，例如脚步声、风声、水花声、材质与地面轻微摩擦声。',
    '【声音限制】生成阶段不要旁白、配音、人声、口播、唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点。',
    '【禁止项】不要字幕、屏幕文字、价格、二维码、水印、主播画面、直播带货口播；不要对比、测评式演示、道具验证、实验化场景或硬性证明画面。',
  ].join(' ')
}

function buildProductDetailEndingScene(product, aspectRatio = '9:16', duration = 8) {
  const productName = product?.name?.trim() || '产品'
  const category = product?.category?.trim() || '户外运动产品'
  const baseRules = [
    `产品：${productName}，类目：${category}。`,
    '参考图只使用当前最终版 Image2 产品完整形态还原图，产品外观由参考图锁定。',
    '画面必须是产品本身，不要人穿着，不要真人脚、腿、走路、奔跑、踩水或使用场景动作。',
    '不要分镜图，不要重新设计产品，不要改变轮廓、比例、材质、配色、logo/文字位置、鞋底结构和关键细节。',
  ].join(' ')
  const imagePrompt = [
    '【产品细节收尾】',
    baseRules,
    '如果需要首帧图片，只生成产品本体的高级广告静物/英雄图：产品清晰完整，材质、鞋面、鞋底、包边、logo 区域和纹理可见；背景可以是干净棚拍或克制户外材质台面，但主体必须是产品本身。',
  ].join(' ')
  const videoPrompt = [
    `【技术参数】${aspectRatio}，${duration}秒，24fps，高级运动户外品牌广告产品细节收尾镜头。`,
    '【参考素材】@图片1 是当前最终版 Image2 产品完整形态还原图，也是唯一产品参考；不要使用分镜图。',
    baseRules,
    '【画面目标】只拍产品本身的细节和质感，用微距、慢推、环绕、扫光、浅景深表现鞋面材质、鞋底纹路、包边结构、logo 区域、轮廓比例、水珠或微尘质感，像广告片最后一段产品细节 hero shot。',
    `【时间戳分镜】0-${duration}秒：产品静置或轻微转台/镜头运动，先从材质微距进入，再缓慢推进到完整轮廓或英雄近景；结尾稳定停在产品本身的样式和细节上，方便后面自然过渡到产品海报。`,
    '【音效】只保留极轻微真实材质声、环境风声或镜头氛围声；不要人声，不要脚步声。',
    '【声音限制】生成阶段不要旁白、配音、人声、口播、唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点。',
    '【禁止项】不要人穿着、不要走路、不要真人身体部位、不要脚步动作、不要字幕、价格、二维码、水印、主播画面、促销大字、对比测试或说明书演示。',
  ].join(' ')
  return normalizeScene({
    id: `product_detail_ending_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    title: '产品细节收尾镜头',
    selling_point: '产品细节',
    hook: '产品本身的材质、轮廓和关键细节',
    image_prompt: imagePrompt,
    video_prompt: videoPrompt,
    voiceover_text: productName,
    productName,
    shot_notes: '使用最终版 Image2 产品还原图作为唯一参考；不生成分镜图，不出现人穿着。',
    referenceMode: 'product_detail',
    status: 'draft',
    error: '',
  }, 0)
}

function sanitizeStoryboardVideoPromptText(text) {
  const cleaned = sanitizeStoryboardPromptText(stripVoiceoverPromptBlocks(text))
  const soundRule = VIDEO_SOUND_RULE
  return cleaned && !cleaned.includes(soundRule)
    ? `${cleaned} ${soundRule}`
    : cleaned
}

function buildProductPayload(product) {
  return {
    name: product.name.trim(),
    category: product.category.trim(),
    description: product.description.trim(),
    image_urls: product.imageUrls.map(item => item.url),
    detail_sheet_url: product.detailSheetUrl || '',
  }
}

function normalizeScene(scene, index) {
  const storyboardUrl = scene.storyboard_image_url || scene.storyboardImageUrl || ''
  const videoUrl = scene.video_url || scene.videoUrl || ''
  const rawVideoPrompt = scene.video_prompt || scene.videoPrompt || ''
  const imagePrompt = sanitizeStoryboardPromptText(scene.image_prompt || scene.imagePrompt || '')
  const videoPrompt = sanitizeStoryboardVideoPromptText(rawVideoPrompt)
  const shouldRewritePrompt = hasLegacyStoryboardLogic(imagePrompt) || hasLegacyStoryboardLogic(videoPrompt)
  const referenceMode = String(scene.referenceMode || scene.reference_mode || '')
  const voiceoverText = String(scene.voiceover_text || scene.voiceoverText || scene.voiceover || scene.narration || '').trim()
    || extractVoiceoverText(rawVideoPrompt, buildDefaultVoiceover(scene, index))
  return {
    id: scene.id || `scene_${Date.now()}_${index}`,
    title: scene.title || `分镜 ${index + 1}`,
    selling_point: scene.selling_point || scene.sellingPoint || '',
    hook: scene.hook || '',
    image_prompt: shouldRewritePrompt ? buildAdFilmImagePrompt(scene, index) : imagePrompt,
    video_prompt: shouldRewritePrompt ? buildAdFilmVideoPrompt(scene, index) : videoPrompt,
    referenceMode,
    voiceover_text: voiceoverText,
    shot_notes: scene.shot_notes || scene.shotNotes || '',
    storyboard_image_url: storyboardUrl,
    storyboardImageHistory: normalizeVersionHistory(scene.storyboardImageHistory || scene.storyboard_image_history, storyboardUrl),
    video_url: videoUrl,
    videoHistory: normalizeVersionHistory(scene.videoHistory || scene.video_history, videoUrl),
    status: scene.status || 'draft',
    error: scene.error || '',
    taskId: scene.taskId || '',
    videoProgress: normalizeProgressValue(scene.videoProgress ?? scene.video_progress),
    videoProgressMessage: String(scene.videoProgressMessage || scene.video_progress_message || ''),
    videoStartedAt: Number(scene.videoStartedAt || scene.video_started_at || 0),
  }
}

function normalizeMediaItem(item) {
  if (!item) return null
  if (typeof item === 'string') {
    const url = item.trim()
    return url ? { url, name: '' } : null
  }
  if (typeof item !== 'object') return null
  const url = String(item.url || item.image_url || item.video_url || '').trim()
  if (!url) return null
  return {
    url,
    name: String(item.name || item.file_name || ''),
    durationSeconds: item.durationSeconds ?? item.duration_seconds,
  }
}

function uniqueMediaUrls(urls) {
  const seen = new Set()
  return (urls || [])
    .map(url => String(url || '').trim())
    .filter(url => {
      if (!url || seen.has(url)) return false
      seen.add(url)
      return true
    })
}

function collectVideoReferenceImages({ scene }) {
  if (scene?.referenceMode === 'product_detail' || scene?.reference_mode === 'product_detail') {
    return []
  }
  return uniqueMediaUrls([scene?.storyboard_image_url]).slice(0, 1)
}

function normalizeProductDraft(product) {
  const raw = product && typeof product === 'object' ? product : {}
  return {
    ...DEFAULT_PRODUCT,
    name: String(raw.name || ''),
    category: String(raw.category || ''),
    description: String(raw.description || ''),
    imageUrls: Array.isArray(raw.imageUrls)
      ? raw.imageUrls.map(normalizeMediaItem).filter(Boolean)
      : [],
    detailSheetUrl: String(raw.detailSheetUrl || raw.detail_sheet_url || ''),
    detailSheetPrompt: String(raw.detailSheetPrompt || raw.detail_sheet_prompt || ''),
    detailSheetHistory: normalizeVersionHistory(raw.detailSheetHistory || raw.detail_sheet_history, raw.detailSheetUrl || raw.detail_sheet_url || ''),
  }
}

function normalizeSellingPoint(point) {
  const raw = point && typeof point === 'object' ? point : {}
  return {
    ...raw,
    title: String(raw.title || ''),
    description: String(raw.description || ''),
    evidence: String(raw.evidence || ''),
    source: String(raw.source || 'manual'),
  }
}

function normalizeDraft(rawDraft) {
  const fallback = createDefaultDraft()
  if (!rawDraft || typeof rawDraft !== 'object') return fallback
  const nextDuration = Number(rawDraft.duration)
  const nextVariantCount = Number(rawDraft.variantCount)
  const videoModel = typeof rawDraft.videoModel === 'string' ? rawDraft.videoModel : fallback.videoModel
  const savedResolution = String(rawDraft.videoResolution || rawDraft.resolution || fallback.videoResolution)
  const storyboardDefaults = storyboardDefaultsForVideoModel(videoModel)
  const normalizedScenes = Array.isArray(rawDraft.scenes)
    ? rawDraft.scenes.map((scene, index) => normalizeScene(scene || {}, index))
    : []
  const normalizedFinalClips = Array.isArray(rawDraft.finalClips)
    ? rawDraft.finalClips.map((clip, index) => normalizeFinalClip(clip || {}, index, normalizedScenes)).filter(Boolean)
    : []
  const rawTtsVoiceType = typeof rawDraft.ttsVoiceType === 'string' ? rawDraft.ttsVoiceType : fallback.ttsVoiceType
  const ttsVoiceType = TTS_VOICE_OPTIONS.some(item => item.id === rawTtsVoiceType) ? rawTtsVoiceType : 'custom'
  const ttsSpeedRatio = Number(rawDraft.ttsSpeedRatio)
  const bgmUrl = typeof rawDraft.bgmUrl === 'string' ? rawDraft.bgmUrl : ''
  const bgmVolume = Number(rawDraft.bgmVolume)
  const normalizedBgmVolume = Number.isFinite(bgmVolume) ? Math.max(0, Math.min(1, bgmVolume)) : fallback.bgmVolume
  return {
    ...fallback,
    updatedAt: Number(rawDraft.updatedAt || 0),
    product: normalizeProductDraft(rawDraft.product),
    languageModel: typeof rawDraft.languageModel === 'string' ? rawDraft.languageModel : fallback.languageModel,
    imageModel: typeof rawDraft.imageModel === 'string' ? rawDraft.imageModel : fallback.imageModel,
    videoModel,
    videoResolution: savedResolution,
    aspectRatio: ASPECT_OPTIONS.includes(rawDraft.aspectRatio) ? rawDraft.aspectRatio : fallback.aspectRatio,
    duration: (isVeoModel(videoModel) || storyboardDefaults.duration === VEO_STORYBOARD_DURATION)
      ? VEO_STORYBOARD_DURATION
      : DURATION_OPTIONS.includes(nextDuration) ? nextDuration : storyboardDefaults.duration,
    variantCount: Number.isFinite(nextVariantCount)
      ? Math.max(storyboardDefaults.count, Math.min(12, Math.round(nextVariantCount)))
      : storyboardDefaults.count,
    liveVideo: normalizeMediaItem(rawDraft.liveVideo),
    transcript: typeof rawDraft.transcript === 'string' ? rawDraft.transcript : '',
    manualSellingPoints: typeof rawDraft.manualSellingPoints === 'string' ? rawDraft.manualSellingPoints : '',
    sellingPoints: Array.isArray(rawDraft.sellingPoints)
      ? rawDraft.sellingPoints.map(normalizeSellingPoint)
      : [],
    storyboardCreativeBrief: typeof rawDraft.storyboardCreativeBrief === 'string'
      ? rawDraft.storyboardCreativeBrief
      : fallback.storyboardCreativeBrief,
    storyboardReferences: Array.isArray(rawDraft.storyboardReferences)
      ? rawDraft.storyboardReferences.map(normalizeMediaItem).filter(Boolean)
      : [],
    productionMatrix: normalizeProductionMatrix(rawDraft.productionMatrix),
    scenes: normalizedScenes,
    batchResult: rawDraft.batchResult && typeof rawDraft.batchResult === 'object' ? rawDraft.batchResult : null,
    finalVideo: rawDraft.finalVideo && typeof rawDraft.finalVideo === 'object' ? rawDraft.finalVideo : null,
    finalClips: normalizedFinalClips,
    ttsVoiceType,
    ttsCustomVoiceType: typeof rawDraft.ttsCustomVoiceType === 'string'
      ? rawDraft.ttsCustomVoiceType
      : (ttsVoiceType === 'custom' ? rawTtsVoiceType : ''),
    ttsSpeedRatio: Number.isFinite(ttsSpeedRatio) ? Math.max(0.6, Math.min(1.4, ttsSpeedRatio)) : fallback.ttsSpeedRatio,
    bgmEnabled: typeof rawDraft.bgmEnabled === 'boolean' ? rawDraft.bgmEnabled : fallback.bgmEnabled,
    bgmUrl,
    bgmName: typeof rawDraft.bgmName === 'string' ? rawDraft.bgmName : '',
    bgmVolume: bgmUrl && normalizedBgmVolume <= 0.2 ? fallback.bgmVolume : normalizedBgmVolume,
    productPosterUrl: typeof rawDraft.productPosterUrl === 'string' ? rawDraft.productPosterUrl : '',
    productPosterPrompt: typeof rawDraft.productPosterPrompt === 'string' ? rawDraft.productPosterPrompt : '',
    productPosterHistory: normalizeVersionHistory(rawDraft.productPosterHistory, rawDraft.productPosterUrl),
  }
}

function loadWorkbenchDraft() {
  if (typeof window === 'undefined') return createDefaultDraft()
  try {
    const raw = window.localStorage.getItem(WORKBENCH_DRAFT_STORAGE_KEY)
    return raw ? normalizeDraft(JSON.parse(raw)) : createDefaultDraft()
  } catch {
    return createDefaultDraft()
  }
}

function saveWorkbenchDraft(draft) {
  if (typeof window === 'undefined') return
  const nextDraft = {
    ...draft,
    updatedAt: Date.now(),
  }
  try {
    window.localStorage.setItem(
      WORKBENCH_DRAFT_STORAGE_KEY,
      JSON.stringify(nextDraft),
    )
  } catch {
    // Ignore storage quota and private-mode failures; the page can still be used normally.
  }
  return nextDraft
}

function normalizeProductMemoryName(name) {
  return String(name || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

function loadLocalProductMemories() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(PRODUCT_MEMORY_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function saveLocalProductMemory(name, memory) {
  if (typeof window === 'undefined') return null
  const nameKey = normalizeProductMemoryName(name)
  if (!nameKey || !productMemoryHasContent(memory)) return null
  const memories = loadLocalProductMemories()
  const nextMemory = {
    ...memory,
    productName: memory.productName || name,
    updatedAt: Date.now(),
  }
  const items = Object.entries({ ...memories, [nameKey]: nextMemory })
    .filter(([, value]) => value && typeof value === 'object')
    .sort(([, a], [, b]) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0))
    .slice(0, PRODUCT_MEMORY_CACHE_LIMIT)
  const nextMemories = Object.fromEntries(items)
  try {
    window.localStorage.setItem(PRODUCT_MEMORY_STORAGE_KEY, JSON.stringify(nextMemories))
  } catch {
    // Backend memory remains the source of truth when browser storage is unavailable.
  }
  return nextMemory
}

function loadLocalProductMemory(name) {
  const memory = loadLocalProductMemories()[normalizeProductMemoryName(name)]
  return memory && typeof memory === 'object' ? memory : null
}

function buildProductMemorySnapshot({
  product,
  liveVideo,
  transcript,
  manualSellingPoints,
  sellingPoints,
}) {
  const normalizedProduct = normalizeProductDraft(product)
  return {
    productName: normalizedProduct.name,
    product: normalizedProduct,
    liveVideo: normalizeMediaItem(liveVideo),
    transcript: String(transcript || ''),
    manualSellingPoints: String(manualSellingPoints || ''),
    sellingPoints: Array.isArray(sellingPoints)
      ? sellingPoints.map(normalizeSellingPoint).filter(point => point.title || point.description || point.evidence)
      : [],
  }
}

function productMemoryHasContent(memory) {
  const product = normalizeProductDraft(memory?.product)
  return Boolean(
    product.imageUrls.length
    || product.detailSheetUrl
    || memory?.liveVideo?.url
    || String(memory?.transcript || '').trim()
    || String(memory?.manualSellingPoints || '').trim()
    || (Array.isArray(memory?.sellingPoints) && memory.sellingPoints.length)
  )
}

function productMemorySignature(memory) {
  return JSON.stringify(memory || {})
}

function rememberedFieldsSignature({
  product,
  liveVideo,
  transcript,
  manualSellingPoints,
  sellingPoints,
}) {
  const normalizedProduct = normalizeProductDraft(product)
  return JSON.stringify({
    productImages: normalizedProduct.imageUrls.map(item => item.url),
    detailSheetUrl: normalizedProduct.detailSheetUrl,
    liveVideoUrl: normalizeMediaItem(liveVideo)?.url || '',
    transcript: String(transcript || ''),
    manualSellingPoints: String(manualSellingPoints || ''),
    sellingPoints: (Array.isArray(sellingPoints) ? sellingPoints : []).map(point => ({
      title: String(point?.title || ''),
      description: String(point?.description || ''),
      evidence: String(point?.evidence || ''),
    })),
  })
}

function StatusNotice({ notice }) {
  if (!notice) return null
  return (
    <div className={`batch-video-notice ${notice.type || 'info'}`}>
      <AlertCircle size={16} />
      <span>{notice.text}</span>
    </div>
  )
}

function ModelSelect({ label, value, onChange, models }) {
  return (
    <label className="batch-video-field">
      <span>{label}</span>
      <select value={value} onChange={event => onChange(event.target.value)}>
        {models.map(model => (
          <option key={model.id} value={model.id}>{modelLabel(model)}</option>
        ))}
      </select>
    </label>
  )
}

function VersionStrip({ title, versions, activeUrl, type = 'image', onSelect }) {
  const items = Array.isArray(versions) ? versions.filter(item => item?.url) : []
  if (!items.length) return null
  return (
    <div className="batch-video-version-strip">
      <div className="batch-video-version-strip-head">
        <strong>{title}</strong>
        <span>{items.length} 个版本</span>
      </div>
      <div className="batch-video-version-list">
        {items.map((item, index) => (
          <button
            type="button"
            key={item.id || `${item.url}-${index}`}
            className={`batch-video-version-card ${item.url === activeUrl ? 'is-selected' : ''}`}
            onClick={() => onSelect(item)}
            title={item.label || `版本 ${index + 1}`}
          >
            {type === 'video' ? (
              <video src={assetUrl(item.url)} muted playsInline preload="metadata" />
            ) : (
              <img src={assetUrl(item.url)} alt={item.label || `版本 ${index + 1}`} />
            )}
            <span>{item.url === activeUrl ? '最终' : `v${index + 1}`}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function BatchVideoWorkbenchPage() {
  const initialDraft = useMemo(() => loadWorkbenchDraft(), [])
  const [product, setProduct] = useState(() => initialDraft.product)
  const [languageModels, setLanguageModels] = useState(DEFAULT_LANGUAGE_MODELS)
  const [imageModels, setImageModels] = useState(DEFAULT_IMAGE_MODELS)
  const [videoModels, setVideoModels] = useState(DEFAULT_VIDEO_MODELS)
  const [asrInfo, setAsrInfo] = useState(null)
  const [languageModel, setLanguageModel] = useState(() => initialDraft.languageModel)
  const [imageModel, setImageModel] = useState(() => initialDraft.imageModel)
  const [videoModel, setVideoModel] = useState(() => initialDraft.videoModel)
  const [videoResolution, setVideoResolution] = useState(() => initialDraft.videoResolution)
  const [aspectRatio, setAspectRatio] = useState(() => initialDraft.aspectRatio)
  const [duration, setDuration] = useState(() => initialDraft.duration)
  const [variantCount, setVariantCount] = useState(() => Math.max(storyboardDefaultsForVideoModel(initialDraft.videoModel).count, initialDraft.variantCount))
  const [liveVideo, setLiveVideo] = useState(() => initialDraft.liveVideo)
  const [transcript, setTranscript] = useState(() => initialDraft.transcript)
  const [manualSellingPoints, setManualSellingPoints] = useState(() => initialDraft.manualSellingPoints)
  const [sellingPoints, setSellingPoints] = useState(() => initialDraft.sellingPoints)
  const [storyboardCreativeBrief, setStoryboardCreativeBrief] = useState(() => initialDraft.storyboardCreativeBrief)
  const [storyboardReferences, setStoryboardReferences] = useState(() => initialDraft.storyboardReferences)
  const [productionMatrix, setProductionMatrix] = useState(() => initialDraft.productionMatrix)
  const [scenes, setScenes] = useState(() => initialDraft.scenes)
  const [batchResult, setBatchResult] = useState(() => initialDraft.batchResult)
  const [finalVideo, setFinalVideo] = useState(() => initialDraft.finalVideo || null)
  const [finalClips, setFinalClips] = useState(() => initialDraft.finalClips || [])
  const [ttsVoiceType, setTtsVoiceType] = useState(() => initialDraft.ttsVoiceType || '')
  const [ttsCustomVoiceType, setTtsCustomVoiceType] = useState(() => initialDraft.ttsCustomVoiceType || '')
  const [ttsSpeedRatio, setTtsSpeedRatio] = useState(() => initialDraft.ttsSpeedRatio || 1)
  const [bgmEnabled, setBgmEnabled] = useState(() => initialDraft.bgmEnabled !== false)
  const [bgmUrl, setBgmUrl] = useState(() => initialDraft.bgmUrl || '')
  const [bgmName, setBgmName] = useState(() => initialDraft.bgmName || '')
  const [bgmVolume, setBgmVolume] = useState(() => initialDraft.bgmVolume ?? 0.45)
  const [productPosterUrl, setProductPosterUrl] = useState(() => initialDraft.productPosterUrl || '')
  const [productPosterPrompt, setProductPosterPrompt] = useState(() => initialDraft.productPosterPrompt || '')
  const [productPosterHistory, setProductPosterHistory] = useState(() => initialDraft.productPosterHistory || [])
  const [draftHydrated, setDraftHydrated] = useState(false)
  const [productMemoryStatus, setProductMemoryStatus] = useState({ state: 'idle', text: '' })
  const [productMemoryReadyTick, setProductMemoryReadyTick] = useState(0)
  const [notice, setNotice] = useState(null)
  const [loadingTasks, setLoadingTasks] = useState({})
  const [, setProgressTick] = useState(0)

  const productPayload = useMemo(() => buildProductPayload(product), [product])
  const productMemoryNameKey = useMemo(() => normalizeProductMemoryName(product.name), [product.name])
  const selectedVideoModel = useMemo(
    () => videoModels.find(item => item.id === videoModel) || DEFAULT_VIDEO_MODELS.find(item => item.id === videoModel),
    [videoModel, videoModels],
  )
  const videoResolutionOptions = useMemo(() => videoModelResolutionOptions(selectedVideoModel), [selectedVideoModel])
  const storyboardDefaults = useMemo(() => storyboardDefaultsForVideoModel(videoModel, videoModels), [videoModel, videoModels])
  const veoStoryboardMode = isFixedEightSecondModel(selectedVideoModel) || isVeoModel(videoModel)
  const requestedVideoDuration = videoModelRequestedDuration(selectedVideoModel, duration)
  const videoCostEstimate = estimateVideoModelCost(selectedVideoModel, duration)
  const storyboardBriefPlan = useMemo(() => parseStoryboardCreativeBrief(storyboardCreativeBrief), [storyboardCreativeBrief])
  const matrixSourcePoints = useMemo(() => {
    const generated = sellingPoints.filter(point => (point.title || point.description || '').trim())
    if (generated.length) return generated
    return splitLines(manualSellingPoints).map(item => ({ title: item, description: item, evidence: '', source: 'manual' }))
  }, [manualSellingPoints, sellingPoints])
  const matrixSellingPointCount = matrixSourcePoints.length
  const matrixDraftCount = Math.min(
    productionMatrix.maxScenes,
    matrixSellingPointCount
      * productionMatrix.angleIds.length
      * productionMatrix.moodIds.length
      * productionMatrix.scenesPerCombination,
  )
  const matrixCostEstimate = videoCostEstimate && matrixDraftCount > 0
    ? {
      amount: Number((videoCostEstimate.amount * matrixDraftCount).toFixed(2)),
      amountCny: videoCostEstimate.amountCny > 0 ? Number((videoCostEstimate.amountCny * matrixDraftCount).toFixed(2)) : 0,
      unit: videoCostEstimate.unit,
    }
    : null
  const previousVeoStoryboardModeRef = useRef(veoStoryboardMode)
  const storyboardRegenerateIndexRef = useRef(0)
  const draftHydratedRef = useRef(false)
  const draftSaveTimerRef = useRef(null)
  const productMemoryFetchRef = useRef({ nameKey: '', requestId: 0 })
  const productMemorySaveTimerRef = useRef(null)
  const productMemoryLastSavedRef = useRef('')
  const productMemoryApplyRef = useRef({ nameKey: '', signature: '' })
  const productMemoryPreviousNameKeyRef = useRef(productMemoryNameKey)
  const productMemorySaveBaselineRef = useRef({ nameKey: productMemoryNameKey, signature: '' })
  const hasProcessingVideo = scenes.some(scene => isProcessingTaskStatus(scene.status))

  const { registerTaskPolling } = useGameTaskPolling({
    intervalMs: 6000,
    hiddenIntervalMs: 30000,
    onPollingError: () => setNotice({ type: 'warning', text: '视频任务状态轮询失败，请稍后刷新状态。' }),
  })

  const updateProduct = (key, value) => {
    setProduct(prev => ({ ...prev, [key]: value }))
  }

  const applyProductMemory = useCallback((memory, { replace = false } = {}) => {
    if (!memory || typeof memory !== 'object') return false
    const memoryProduct = normalizeProductDraft(memory.product)
    let changed = false
    setProduct(prev => {
      const next = { ...prev }
      if (replace || (!next.category && memoryProduct.category)) {
        next.category = memoryProduct.category
        changed = true
      }
      if (replace || (!next.description && memoryProduct.description)) {
        next.description = memoryProduct.description
        changed = true
      }
      if (replace || !Array.isArray(next.imageUrls) || !next.imageUrls.length) {
        if (memoryProduct.imageUrls.length) {
          next.imageUrls = memoryProduct.imageUrls
          changed = true
        } else if (replace && next.imageUrls?.length) {
          next.imageUrls = []
          changed = true
        }
      }
      if (replace || (!next.detailSheetUrl && memoryProduct.detailSheetUrl)) {
        next.detailSheetUrl = memoryProduct.detailSheetUrl
        next.detailSheetPrompt = memoryProduct.detailSheetPrompt || ''
        next.detailSheetHistory = memoryProduct.detailSheetHistory
        changed = true
      } else if ((!next.detailSheetHistory || !next.detailSheetHistory.length) && memoryProduct.detailSheetHistory.length) {
        next.detailSheetHistory = memoryProduct.detailSheetHistory
        changed = true
      }
      return changed ? next : prev
    })
    const memoryLiveVideo = normalizeMediaItem(memory.liveVideo)
    if (replace || (!liveVideo && memoryLiveVideo)) {
      setLiveVideo(memoryLiveVideo)
      changed = true
    }
    if (replace || (!String(transcript || '').trim() && String(memory.transcript || '').trim())) {
      setTranscript(String(memory.transcript || ''))
      changed = true
    }
    if (replace || (!String(manualSellingPoints || '').trim() && String(memory.manualSellingPoints || '').trim())) {
      setManualSellingPoints(String(memory.manualSellingPoints || ''))
      changed = true
    }
    if (replace || (!sellingPoints.length && Array.isArray(memory.sellingPoints) && memory.sellingPoints.length)) {
      setSellingPoints(Array.isArray(memory.sellingPoints) ? memory.sellingPoints.map(normalizeSellingPoint) : [])
      changed = true
    }
    return changed
  }, [liveVideo, manualSellingPoints, sellingPoints.length, transcript])

  const applyDraftToState = useCallback((draft) => {
    const nextDraft = normalizeDraft(draft)
    setProduct(nextDraft.product)
    setLanguageModel(nextDraft.languageModel)
    setImageModel(nextDraft.imageModel)
    setVideoModel(nextDraft.videoModel)
    setVideoResolution(nextDraft.videoResolution)
    setAspectRatio(nextDraft.aspectRatio)
    setDuration(nextDraft.duration)
    setVariantCount(nextDraft.variantCount)
    setLiveVideo(nextDraft.liveVideo)
    setTranscript(nextDraft.transcript)
    setManualSellingPoints(nextDraft.manualSellingPoints)
    setSellingPoints(nextDraft.sellingPoints)
    setStoryboardCreativeBrief(nextDraft.storyboardCreativeBrief)
    setStoryboardReferences(nextDraft.storyboardReferences)
    setProductionMatrix(nextDraft.productionMatrix)
    setScenes(nextDraft.scenes)
    setBatchResult(nextDraft.batchResult)
    setFinalVideo(nextDraft.finalVideo)
    setFinalClips(nextDraft.finalClips)
    setTtsVoiceType(nextDraft.ttsVoiceType)
    setTtsCustomVoiceType(nextDraft.ttsCustomVoiceType)
    setTtsSpeedRatio(nextDraft.ttsSpeedRatio)
    setBgmEnabled(nextDraft.bgmEnabled)
    setBgmUrl(nextDraft.bgmUrl)
    setBgmName(nextDraft.bgmName)
    setBgmVolume(nextDraft.bgmVolume)
    setProductPosterUrl(nextDraft.productPosterUrl)
    setProductPosterPrompt(nextDraft.productPosterPrompt)
    setProductPosterHistory(nextDraft.productPosterHistory)
  }, [])

  const updateScene = useCallback((sceneId, patch) => {
    setScenes(prev => prev.map(scene => (scene.id === sceneId ? { ...scene, ...patch } : scene)))
  }, [])

  const updateSceneWith = useCallback((sceneId, updater) => {
    setScenes(prev => prev.map(scene => (
      scene.id === sceneId ? { ...scene, ...updater(scene) } : scene
    )))
  }, [])

  const selectDetailSheetVersion = useCallback((version) => {
    if (!version?.url) return
    setProduct(prev => ({
      ...prev,
      detailSheetUrl: version.url,
      detailSheetPrompt: version.prompt || prev.detailSheetPrompt || '',
      detailSheetHistory: mergeVersionHistory(prev.detailSheetHistory, version),
    }))
  }, [])

  const selectStoryboardVersion = useCallback((sceneId, version) => {
    if (!version?.url) return
    updateScene(sceneId, {
      storyboard_image_url: version.url,
      storyboardImageHistory: mergeVersionHistory(
        scenes.find(item => item.id === sceneId)?.storyboardImageHistory,
        version,
      ),
      status: 'storyboard_ready',
      error: '',
    })
  }, [scenes, updateScene])

  const selectVideoVersion = useCallback((sceneId, version) => {
    if (!version?.url) return
    updateScene(sceneId, {
      video_url: version.url,
      videoHistory: mergeVersionHistory(
        scenes.find(item => item.id === sceneId)?.videoHistory,
        version,
      ),
      status: 'completed',
      error: '',
    })
  }, [scenes, updateScene])

  const rebuildFinalClipsFromScenes = useCallback(() => {
    const clips = buildDefaultFinalClips(scenes)
    setFinalClips(clips)
    setNotice(clips.length
      ? { type: 'success', text: `已按当前最终视频生成 ${clips.length} 条剪辑片段，可继续截取和排序。` }
      : { type: 'warning', text: '当前还没有可用视频，先生成或选择视频版本。' })
  }, [scenes])

  const appendFinalClipFromScene = useCallback((scene, version = null) => {
    const index = scenes.findIndex(item => item.id === scene.id)
    const clip = createFinalClipFromScene(scene, Math.max(0, index), version)
    if (!clip) {
      setNotice({ type: 'warning', text: '这个分镜还没有可用视频，先生成或选择一个视频版本。' })
      return
    }
    setFinalClips(prev => [...prev, clip])
    setNotice({ type: 'success', text: '已加入剪辑表，可在完整视频区域截取片段。' })
  }, [scenes])

  const updateFinalClip = useCallback((clipId, patch) => {
    setFinalClips(prev => prev.map(clip => (clip.id === clipId ? normalizeFinalClip({ ...clip, ...patch }, 0, scenes) : clip)).filter(Boolean))
  }, [scenes])

  const removeFinalClip = useCallback((clipId) => {
    setFinalClips(prev => prev.filter(clip => clip.id !== clipId))
  }, [])

  const moveFinalClip = useCallback((clipId, direction) => {
    setFinalClips(prev => {
      const index = prev.findIndex(clip => clip.id === clipId)
      const nextIndex = index + direction
      if (index < 0 || nextIndex < 0 || nextIndex >= prev.length) return prev
      const next = [...prev]
      const [item] = next.splice(index, 1)
      next.splice(nextIndex, 0, item)
      return next
    })
  }, [])

  const updateFinalClipScene = useCallback((clipId, nextSceneId) => {
    const nextScene = scenes.find(scene => scene.id === nextSceneId)
    if (!nextScene) return
    const nextClip = createFinalClipFromScene(nextScene, scenes.findIndex(scene => scene.id === nextSceneId))
    if (!nextClip) {
      updateFinalClip(clipId, {
        sceneId: nextSceneId,
        title: nextScene.title,
        videoUrl: '',
        voiceoverText: nextScene.voiceover_text || buildDefaultVoiceover(nextScene),
        subtitle: nextScene.voiceover_text || buildDefaultVoiceover(nextScene),
      })
      return
    }
    updateFinalClip(clipId, {
      sceneId: nextSceneId,
      title: nextClip.title,
      videoUrl: nextClip.videoUrl,
      sourceLabel: nextClip.sourceLabel,
      voiceoverText: nextClip.voiceoverText,
      subtitle: nextClip.subtitle,
    })
  }, [scenes, updateFinalClip])

  const updateSellingPoint = useCallback((index, patch) => {
    setSellingPoints(prev => prev.map((point, itemIndex) => (
      itemIndex === index ? { ...point, ...patch } : point
    )))
  }, [])

  const removeSellingPoint = useCallback((index) => {
    setSellingPoints(prev => prev.filter((_, itemIndex) => itemIndex !== index))
  }, [])

  const updateProductionMatrix = useCallback((patch) => {
    setProductionMatrix(prev => normalizeProductionMatrix({ ...prev, ...patch }))
  }, [])

  const toggleMatrixAngle = useCallback((id) => {
    setProductionMatrix(prev => normalizeProductionMatrix({ ...prev, angleIds: toggleSelectedId(prev.angleIds, id) }))
  }, [])

  const toggleMatrixMood = useCallback((id) => {
    setProductionMatrix(prev => normalizeProductionMatrix({ ...prev, moodIds: toggleSelectedId(prev.moodIds, id) }))
  }, [])

  const startLoading = useCallback((taskKey) => {
    setLoadingTasks(prev => ({ ...prev, [taskKey]: true }))
  }, [])

  const finishLoading = useCallback((taskKey) => {
    setLoadingTasks(prev => {
      if (!prev[taskKey]) return prev
      const next = { ...prev }
      delete next[taskKey]
      return next
    })
  }, [])

  const isLoading = useCallback((taskKey) => Boolean(loadingTasks[taskKey]), [loadingTasks])

  const registerSceneVideoPolling = useCallback((scene, prompt = '') => {
    const taskId = scene?.taskId
    const sceneId = scene?.id
    if (!taskId || !sceneId) return
    registerTaskPolling(taskId, updates => {
      const nextVideoUrl = updates.videoUrl || updates.video_url || ''
      const nextProgress = normalizeProgressValue(updates.progress)
      const isDone = nextVideoUrl || isCompletedTaskStatus(updates.status)
      const isFailed = String(updates.status || '').toLowerCase() === 'failed'
      updateSceneWith(sceneId, currentScene => ({
        status: updates.status || 'processing',
        video_url: nextVideoUrl,
        videoHistory: nextVideoUrl
          ? mergeVersionHistory(currentScene.videoHistory, makeVersionItem(nextVideoUrl, {
            prompt: prompt || currentScene.video_prompt || '',
            source: videoModel,
            taskId,
            label: `视频 ${new Date().toLocaleTimeString()}`,
          }))
          : currentScene.videoHistory,
        error: updates.error || '',
        taskId: updates.taskId ?? taskId,
        videoProgress: isDone || isFailed ? null : (nextProgress ?? currentScene.videoProgress ?? 0.08),
        videoProgressMessage: isDone || isFailed ? '' : (updates.message || currentScene.videoProgressMessage || '正在同步视频生成状态'),
        videoStartedAt: isDone || isFailed ? 0 : (currentScene.videoStartedAt || Date.now()),
      }))
    })
  }, [registerTaskPolling, updateSceneWith, videoModel])

  const handleClearDraft = useCallback(() => {
    const emptyDraft = createDefaultDraft()
    draftHydratedRef.current = true
    setDraftHydrated(true)
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(WORKBENCH_DRAFT_STORAGE_KEY)
      } catch {
        // Ignore storage failures.
      }
    }
    applyDraftToState(emptyDraft)
    setLoadingTasks({})
    api.put('/api/batch-video/draft', { draft: { ...emptyDraft, updatedAt: Date.now() } }, { timeout: 20_000 }).catch(() => {})
    setNotice({ type: 'success', text: '草稿已清空。' })
  }, [applyDraftToState])

  useEffect(() => {
    api.get('/api/batch-video/models')
      .then(data => {
        const nextLanguage = data.language_models?.length ? data.language_models : DEFAULT_LANGUAGE_MODELS
        const nextImages = data.image_models?.length ? data.image_models : DEFAULT_IMAGE_MODELS
        const nextVideos = data.video_models?.length ? data.video_models : DEFAULT_VIDEO_MODELS
        setLanguageModels(nextLanguage)
        setImageModels(nextImages)
        setVideoModels(nextVideos)
        setLanguageModel(prev => nextLanguage.some(item => item.id === prev) ? prev : nextLanguage[0].id)
        setImageModel(prev => nextImages.some(item => item.id === prev) ? prev : nextImages[0].id)
        setVideoModel(prev => nextVideos.some(item => item.id === prev) ? prev : nextVideos[0].id)
        setAsrInfo(data.asr || null)
      })
      .catch(() => {
        setNotice({ type: 'warning', text: '模型列表读取失败，已使用默认模型选项。' })
      })
  }, [])

  useEffect(() => {
    let cancelled = false
    api.get('/api/batch-video/draft', { timeout: 20_000 })
      .then(data => {
        if (cancelled) return
        const remoteDraft = data?.draft
        if (remoteDraft && typeof remoteDraft === 'object') {
          const localUpdatedAt = Number(initialDraft.updatedAt || 0)
          const remoteUpdatedAt = Number(remoteDraft.updatedAt || data.updatedAt || 0)
          if (remoteUpdatedAt > localUpdatedAt) {
            applyDraftToState(remoteDraft)
            saveWorkbenchDraft(remoteDraft)
          } else if (localUpdatedAt > remoteUpdatedAt) {
            api.put('/api/batch-video/draft', { draft: initialDraft }, { timeout: 20_000 }).catch(() => {})
          }
        } else if (Number(initialDraft.updatedAt || 0) > 0) {
          api.put('/api/batch-video/draft', { draft: initialDraft }, { timeout: 20_000 }).catch(() => {})
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) {
          draftHydratedRef.current = true
          setDraftHydrated(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [applyDraftToState, initialDraft.updatedAt])

  useEffect(() => {
    if (!draftHydrated) return undefined
    const name = product.name.trim()
    const nameKey = productMemoryNameKey
    if (!nameKey) {
      setProductMemoryStatus({ state: 'idle', text: '' })
      return undefined
    }
    const requestId = (productMemoryFetchRef.current.requestId || 0) + 1
    productMemoryFetchRef.current = { nameKey, requestId, pending: true }
    setProductMemoryStatus({ state: 'checking', text: '正在查找这个产品的历史记忆...' })
    const timer = window.setTimeout(() => {
      const previousNameKey = productMemoryPreviousNameKeyRef.current
      const shouldReplaceProductContent = Boolean(previousNameKey && previousNameKey !== nameKey)
      productMemoryPreviousNameKeyRef.current = nameKey
      const applyRememberedMemory = (memory, statusText) => {
        if (!productMemoryHasContent(memory)) return false
        const memorySnapshot = buildProductMemorySnapshot({
          product: memory.product,
          liveVideo: memory.liveVideo,
          transcript: memory.transcript,
          manualSellingPoints: memory.manualSellingPoints,
          sellingPoints: memory.sellingPoints,
        })
        const signature = productMemorySignature(memorySnapshot)
        if (productMemoryApplyRef.current.nameKey !== nameKey || productMemoryApplyRef.current.signature !== signature) {
          applyProductMemory(memory, { replace: shouldReplaceProductContent })
          productMemoryApplyRef.current = { nameKey, signature }
        }
        productMemoryLastSavedRef.current = signature
        productMemorySaveBaselineRef.current = { nameKey, signature }
        setProductMemoryStatus({ state: 'loaded', text: statusText })
        return true
      }
      api.get(`/api/batch-video/product-memory?product_name=${encodeURIComponent(name)}`, { timeout: 20_000 })
        .then(data => {
          const currentFetch = productMemoryFetchRef.current
          if (currentFetch.requestId !== requestId || currentFetch.nameKey !== nameKey) return
          const memory = data?.memory
          if (data?.found && productMemoryHasContent(memory)) {
            const memorySnapshot = buildProductMemorySnapshot({
              product: memory.product,
              liveVideo: memory.liveVideo,
              transcript: memory.transcript,
              manualSellingPoints: memory.manualSellingPoints,
              sellingPoints: memory.sellingPoints,
            })
            const signature = productMemorySignature(memorySnapshot)
            if (productMemoryApplyRef.current.nameKey !== nameKey || productMemoryApplyRef.current.signature !== signature) {
              applyProductMemory(memory, { replace: shouldReplaceProductContent })
              productMemoryApplyRef.current = { nameKey, signature }
            }
            productMemoryLastSavedRef.current = signature
            productMemorySaveBaselineRef.current = { nameKey, signature }
            setProductMemoryStatus({ state: 'loaded', text: '已载入这个产品之前保存的还原图、转写和卖点。' })
            return
          }
          if (applyRememberedMemory(loadLocalProductMemory(name), '已从本机浏览器记忆里找回这个产品的上次内容。')) {
            return
          }
          productMemoryLastSavedRef.current = ''
          productMemorySaveBaselineRef.current = { nameKey, signature: '' }
          productMemoryApplyRef.current = { nameKey, signature: '' }
          if (shouldReplaceProductContent) {
            setProduct(prev => ({
              ...prev,
              category: '',
              description: '',
              imageUrls: [],
              detailSheetUrl: '',
              detailSheetPrompt: '',
              detailSheetHistory: [],
            }))
            setLiveVideo(null)
            setTranscript('')
            setManualSellingPoints('')
            setSellingPoints([])
          }
          setProductMemoryStatus({ state: 'empty', text: '这个产品还没有历史记忆；重新上传或生成后会自动保存。' })
        })
        .catch(() => {
          const currentFetch = productMemoryFetchRef.current
          if (currentFetch.requestId === requestId && currentFetch.nameKey === nameKey) {
            if (applyRememberedMemory(loadLocalProductMemory(name), '后端产品记忆读取失败，已从本机浏览器记忆找回。')) {
              return
            }
            setProductMemoryStatus({ state: 'error', text: '产品记忆读取失败，本次仍可继续生成。' })
          }
        })
        .finally(() => {
          const currentFetch = productMemoryFetchRef.current
        if (currentFetch.requestId === requestId && currentFetch.nameKey === nameKey) {
          productMemoryFetchRef.current = { ...currentFetch, pending: false }
          setProductMemoryReadyTick(tick => tick + 1)
        }
      })
    }, 550)
    return () => window.clearTimeout(timer)
  }, [applyProductMemory, draftHydrated, product.name, productMemoryNameKey])

  useEffect(() => {
    const wasVeoStoryboardMode = previousVeoStoryboardModeRef.current
    if (veoStoryboardMode) {
      setDuration(VEO_STORYBOARD_DURATION)
      setVariantCount(VEO_STORYBOARD_SCENE_COUNT)
    } else if (wasVeoStoryboardMode) {
      setDuration(storyboardDefaults.duration)
      setVariantCount(storyboardDefaults.count)
    } else {
      setVariantCount(prev => Math.max(storyboardDefaults.count, prev))
    }
    previousVeoStoryboardModeRef.current = veoStoryboardMode
  }, [storyboardDefaults.count, storyboardDefaults.duration, veoStoryboardMode])

  useEffect(() => {
    if (!videoResolutionOptions.includes(videoResolution)) {
      setVideoResolution(videoResolutionOptions[0] || '720p')
    }
  }, [videoResolution, videoResolutionOptions])

  useEffect(() => {
    if (!selectedVideoModel || veoStoryboardMode) return
    const choices = Array.isArray(selectedVideoModel.duration_choices)
      ? selectedVideoModel.duration_choices.map(Number).filter(Boolean)
      : []
    if (choices.length && !choices.includes(Number(duration))) {
      setDuration(choices[0])
      return
    }
    const min = Number(selectedVideoModel.min_duration || 0)
    const max = Number(selectedVideoModel.max_duration || 0)
    if (min > 0 && Number(duration) < min) setDuration(min)
    if (max > 0 && Number(duration) > max) setDuration(max)
  }, [duration, selectedVideoModel, veoStoryboardMode])

  useEffect(() => {
    if (!hasProcessingVideo) return undefined
    const timer = window.setInterval(() => setProgressTick(tick => tick + 1), 1000)
    return () => window.clearInterval(timer)
  }, [hasProcessingVideo])

  useEffect(() => {
    scenes.forEach(scene => {
      if (scene.taskId && !scene.video_url && isProcessingTaskStatus(scene.status)) {
        if (!scene.videoProgressMessage || scene.videoProgressMessage.includes('等待模型生成')) {
          updateScene(scene.id, { videoProgressMessage: '正在同步服务商生成结果' })
        }
        registerSceneVideoPolling(scene, scene.video_prompt)
      }
    })
  }, [registerSceneVideoPolling, scenes, updateScene])

  useEffect(() => {
    const savedDraft = saveWorkbenchDraft(buildWorkbenchDraftSnapshot({
      product,
      languageModel,
      imageModel,
      videoModel,
      videoResolution,
      aspectRatio,
      duration,
      variantCount,
      liveVideo,
      transcript,
      manualSellingPoints,
      sellingPoints,
      storyboardCreativeBrief,
      storyboardReferences,
      productionMatrix,
      scenes,
      batchResult,
      finalVideo,
      finalClips,
      ttsVoiceType,
      ttsCustomVoiceType,
      ttsSpeedRatio,
      bgmEnabled,
      bgmUrl,
      bgmName,
      bgmVolume,
      productPosterUrl,
      productPosterPrompt,
      productPosterHistory,
    }))
    if (!draftHydratedRef.current || !savedDraft) return undefined
    if (draftSaveTimerRef.current) {
      window.clearTimeout(draftSaveTimerRef.current)
    }
    draftSaveTimerRef.current = window.setTimeout(() => {
      api.put('/api/batch-video/draft', { draft: savedDraft }, { timeout: 20_000 }).catch(() => {})
    }, 800)
    return () => {
      if (draftSaveTimerRef.current) {
        window.clearTimeout(draftSaveTimerRef.current)
        draftSaveTimerRef.current = null
      }
    }
  }, [
    aspectRatio,
    batchResult,
    bgmEnabled,
    bgmName,
    bgmUrl,
    bgmVolume,
    duration,
    finalClips,
    finalVideo,
    imageModel,
    languageModel,
    liveVideo,
    manualSellingPoints,
    product,
    productPosterHistory,
    productPosterPrompt,
    productPosterUrl,
    productionMatrix,
    scenes,
    sellingPoints,
    storyboardCreativeBrief,
    storyboardReferences,
    transcript,
    ttsCustomVoiceType,
    ttsSpeedRatio,
    ttsVoiceType,
    variantCount,
    videoModel,
    videoResolution,
  ])

  useEffect(() => {
    if (!draftHydratedRef.current || !productMemoryNameKey) return undefined
    const currentFetch = productMemoryFetchRef.current
    if (currentFetch?.nameKey === productMemoryNameKey && currentFetch?.pending) return undefined
    const memory = buildProductMemorySnapshot({
      product,
      liveVideo,
      transcript,
      manualSellingPoints,
      sellingPoints,
    })
    if (!productMemoryHasContent(memory)) return undefined
    const signature = productMemorySignature(memory)
    if (signature === productMemoryLastSavedRef.current) return undefined
    if (
      productMemorySaveBaselineRef.current.nameKey === productMemoryNameKey
      && productMemorySaveBaselineRef.current.signature === signature
    ) {
      productMemoryLastSavedRef.current = signature
      return undefined
    }
    if (productMemorySaveTimerRef.current) {
      window.clearTimeout(productMemorySaveTimerRef.current)
    }
    saveLocalProductMemory(product.name, memory)
    setProductMemoryStatus({ state: 'saving', text: '正在保存这个产品的记忆...' })
    productMemorySaveTimerRef.current = window.setTimeout(() => {
      api.put('/api/batch-video/product-memory', {
        product_name: product.name,
        memory,
      }, { timeout: 20_000 })
        .then(result => {
          if (normalizeProductMemoryName(product.name) !== productMemoryNameKey) return
          productMemoryLastSavedRef.current = signature
          productMemorySaveBaselineRef.current = { nameKey: productMemoryNameKey, signature }
          setProductMemoryStatus({
            state: 'saved',
            text: result?.updatedAt ? '这个产品的还原图、转写和卖点已保存。' : '产品记忆已保存。',
          })
        })
        .catch(() => {
          if (normalizeProductMemoryName(product.name) === productMemoryNameKey) {
            setProductMemoryStatus({ state: 'error', text: '产品记忆保存失败，本次草稿仍已保存。' })
          }
        })
    }, 1000)
    return () => {
      if (productMemorySaveTimerRef.current) {
        window.clearTimeout(productMemorySaveTimerRef.current)
        productMemorySaveTimerRef.current = null
      }
    }
  }, [
    liveVideo,
    manualSellingPoints,
    product,
    productMemoryNameKey,
    productMemoryReadyTick,
    sellingPoints,
    transcript,
  ])

  async function uploadFiles(files, acceptPrefix) {
    const accepted = Array.from(files || []).filter(file => !acceptPrefix || file.type.startsWith(acceptPrefix))
    if (!accepted.length) return []
    const uploaded = []
    for (const file of accepted) {
      const result = await api.upload('/api/game/upload', file)
      uploaded.push({
        url: readMediaUrl(result),
        name: file.name,
        durationSeconds: result.duration_seconds,
      })
    }
    return uploaded.filter(item => item.url)
  }

  async function handleBgmUpload(files) {
    const file = Array.from(files || [])[0]
    if (!file) return
    const isAudioFile = file.type.startsWith('audio/') || /\.(mp3|wav|m4a|aac|flac|ogg|webm|mp4)$/i.test(file.name || '')
    if (!isAudioFile) {
      setNotice({ type: 'warning', text: '请上传 mp3、wav、m4a、aac、flac、ogg 等音频文件。' })
      return
    }
    startLoading('bgm-upload')
    setNotice(null)
    try {
      const result = await api.upload('/api/files/upload', file, { category: 'bgm' })
      const url = readMediaUrl(result)
      if (!url) {
        setNotice({ type: 'error', text: 'BGM 上传成功但没有返回音频地址，请重新上传。' })
        return
      }
      setBgmUrl(url)
      setBgmName(file.name || result.filename || '自定义 BGM')
      setBgmVolume(prev => Math.max(0.45, clampNumber(prev, 0, 1, 0.45)))
      setBgmEnabled(true)
      setNotice({ type: 'success', text: 'BGM 已上传，合成时会按完整视频时长自动循环或裁剪。' })
    } catch (error) {
      setNotice({ type: 'error', text: `BGM 上传失败：${displayError(error)}` })
    } finally {
      finishLoading('bgm-upload')
    }
  }

  function clearBgmUpload() {
    setBgmUrl('')
    setBgmName('')
    setNotice({ type: 'success', text: '已移除自定义 BGM，合成时将使用默认鼓点 BGM。' })
  }

  function selectProductPosterVersion(version) {
    if (!version?.url) return
    setProductPosterUrl(version.url)
    setProductPosterPrompt(version.prompt || productPosterPrompt || '')
    setProductPosterHistory(prev => mergeVersionHistory(prev, version))
  }

  function clearProductPoster() {
    setProductPosterUrl('')
    setProductPosterPrompt('')
    setNotice({ type: 'success', text: '已移除收尾产品海报，合成时不会追加结尾海报。' })
  }

  async function handleProductImages(files) {
    startLoading('product-images')
    setNotice(null)
    try {
      const uploaded = await uploadFiles(files, 'image/')
      if (!uploaded.length) {
        setNotice({ type: 'warning', text: '请选择图片文件。' })
        return
      }
      setProduct(prev => ({ ...prev, imageUrls: [...prev.imageUrls, ...uploaded].slice(0, 12) }))
    } catch (error) {
      setNotice({ type: 'error', text: `产品图片上传失败：${displayError(error)}` })
    } finally {
      finishLoading('product-images')
    }
  }

  async function handleStoryboardReferenceImages(files) {
    startLoading('storyboard-references')
    setNotice(null)
    try {
      const uploaded = await uploadFiles(files, 'image/')
      if (!uploaded.length) {
        setNotice({ type: 'warning', text: '请选择分镜参考图。' })
        return
      }
      setStoryboardReferences(prev => [...prev, ...uploaded].slice(0, 12))
    } catch (error) {
      setNotice({ type: 'error', text: `分镜参考图上传失败：${displayError(error)}` })
    } finally {
      finishLoading('storyboard-references')
    }
  }

  async function handleGenerateProductDetailSheet() {
    if (!product.imageUrls.length) {
      setNotice({ type: 'warning', text: '请先上传产品参考图。' })
      return
    }
    startLoading('product-detail-sheet')
    setNotice(null)
    try {
      const plan = await api.post('/api/batch-video/product-reconstruction', {
        product: productPayload,
        image_model: 'image2',
        aspect_ratio: '16:9',
      })
      if (plan.status !== 'ready') {
        setNotice({ type: 'warning', text: plan.message || '产品详情表提示词未生成。' })
        return
      }
      const result = await api.post('/api/game/generate_image', {
        project_id: '',
        prompt: plan.prompt,
        provider: plan.provider || 'toapis',
        model: plan.image_model || 'image2',
        aspect_ratio: '16:9',
        asset_type: 'product_detail_sheet',
        reference_urls: (plan.reference_urls || product.imageUrls.map(item => item.url)).slice(0, IMAGE2_REFERENCE_LIMIT),
        prompt_optimize_mode: 'standard',
        image_quality: '2K',
        output_format: 'png',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回产品详情表图片地址')
      const version = makeVersionItem(imageUrl, {
        prompt: plan.prompt || '',
        source: plan.image_model || 'image2',
        label: `Image2 ${new Date().toLocaleTimeString()}`,
      })
      setProduct(prev => ({
        ...prev,
        detailSheetUrl: imageUrl,
        detailSheetPrompt: plan.prompt || '',
        detailSheetHistory: mergeVersionHistory(prev.detailSheetHistory, version),
      }))
      setNotice({ type: 'success', text: '产品完整形态详情表已生成，后续分镜和视频会优先参考这张图。' })
    } catch (error) {
      setNotice({ type: 'error', text: `产品完整形态还原失败：${displayError(error)}` })
    } finally {
      finishLoading('product-detail-sheet')
    }
  }

  async function handleGenerateProductPoster() {
    const productReferences = product.detailSheetUrl ? [product.detailSheetUrl] : product.imageUrls.map(item => item.url)
    if (!productReferences.length) {
      setNotice({ type: 'warning', text: '请先上传产品图，或先用 Image2 还原并选择最终版产品图。' })
      return
    }
    startLoading('product-poster')
    setNotice(null)
    try {
      const plan = await api.post('/api/batch-video/product-poster', {
        product: productPayload,
        selling_points: sellingPoints,
        image_model: 'image2',
        aspect_ratio: aspectRatio,
      })
      if (plan.status !== 'ready') {
        setNotice({ type: 'warning', text: plan.message || '产品收尾海报提示词未生成。' })
        return
      }
      const result = await api.post('/api/game/generate_image', {
        project_id: '',
        prompt: plan.prompt,
        provider: plan.provider || 'toapis',
        model: plan.image_model || 'image2',
        aspect_ratio: plan.aspect_ratio || aspectRatio,
        asset_type: 'product_final_poster',
        reference_urls: (plan.reference_urls || productReferences).slice(0, IMAGE2_REFERENCE_LIMIT),
        prompt_optimize_mode: 'standard',
        image_quality: '2K',
        output_format: 'png',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回产品海报图片地址')
      const version = makeVersionItem(imageUrl, {
        prompt: plan.prompt || '',
        source: plan.image_model || 'image2',
        label: `收尾海报 ${new Date().toLocaleTimeString()}`,
      })
      setProductPosterUrl(imageUrl)
      setProductPosterPrompt(plan.prompt || '')
      setProductPosterHistory(prev => mergeVersionHistory(prev, version))
      setNotice({ type: 'success', text: '产品收尾海报已生成，拼接时会追加到成片末尾，停留时长跟随产品名旁白。' })
    } catch (error) {
      setNotice({ type: 'error', text: `产品收尾海报生成失败：${displayError(error)}` })
    } finally {
      finishLoading('product-poster')
    }
  }

  async function handleLiveVideo(files) {
    startLoading('live-video')
    setNotice(null)
    try {
      const uploaded = await uploadFiles(files, 'video/')
      if (!uploaded.length) {
        setNotice({ type: 'warning', text: '请选择直播视频文件。' })
        return
      }
      setLiveVideo(uploaded[0])
    } catch (error) {
      setNotice({ type: 'error', text: `直播视频上传失败：${displayError(error)}` })
    } finally {
      finishLoading('live-video')
    }
  }

  async function handleTranscribe() {
    if (!liveVideo?.url) {
      setNotice({ type: 'warning', text: '请先上传直播视频。' })
      return
    }
    startLoading('transcribe')
    setNotice(null)
    try {
      const result = await api.post('/api/batch-video/transcribe', {
        product: productPayload,
        live_video_url: liveVideo.url,
        asr_provider: 'volcengine_streaming_asr_2_0',
      })
      if (result.transcript) setTranscript(result.transcript)
      const warningStatuses = ['needs_config', 'adapter_pending', 'needs_video', 'unsupported_source']
      const errorStatuses = ['failed']
      setNotice({
        type: errorStatuses.includes(result.status)
          ? 'error'
          : warningStatuses.includes(result.status) ? 'warning' : 'success',
        text: result.message || '直播转写已完成。',
      })
    } catch (error) {
      setNotice({ type: 'error', text: `直播转写失败：${displayError(error)}` })
    } finally {
      finishLoading('transcribe')
    }
  }

  async function handleSellingPoints() {
    startLoading('selling-points')
    setNotice(null)
    try {
      const result = await api.post('/api/batch-video/selling-points', {
        product: productPayload,
        transcript_text: transcript,
        manual_selling_points: splitLines(manualSellingPoints),
        language_model: languageModel,
      })
      setSellingPoints(result.selling_points || [])
      const warning = result.warnings?.[0]
      const successText = result.mode === 'doubao_seed_2_0_pro'
        ? '豆包 Seed 2.0 Pro 已根据直播转写整理卖点。'
        : '卖点已整理完成。'
      setNotice({
        type: warning ? 'warning' : 'success',
        text: warning || successText,
      })
    } catch (error) {
      setNotice({ type: 'error', text: `卖点整理失败：${displayError(error)}` })
    } finally {
      finishLoading('selling-points')
    }
  }

  async function handleStoryboardPlan() {
    if (!product.name.trim()) {
      setNotice({ type: 'warning', text: '请先填写产品名称。' })
      return
    }
    startLoading('storyboard')
    setNotice(null)
    try {
      const veoMode = isVeoModel(videoModel)
      const briefPlan = parseStoryboardCreativeBrief(storyboardCreativeBrief)
      const briefDuration = DURATION_OPTIONS.includes(Number(briefPlan.duration)) ? Number(briefPlan.duration) : null
      const briefSceneCount = Number.isFinite(Number(briefPlan.sceneCount))
        ? Math.max(1, Math.min(12, Number(briefPlan.sceneCount)))
        : null
      const storyboardDuration = veoMode ? VEO_STORYBOARD_DURATION : (briefDuration || duration)
      const storyboardCount = veoMode
        ? VEO_STORYBOARD_SCENE_COUNT
        : (briefSceneCount || Math.max(DEFAULT_STORYBOARD_SCENE_COUNT, variantCount))
      storyboardRegenerateIndexRef.current += 1
      const regenerateIndex = storyboardRegenerateIndexRef.current
      const creativeSeed = `${Date.now()}-${regenerateIndex}-${Math.random().toString(36).slice(2, 10)}`
      const result = await api.post('/api/batch-video/storyboard-plan', {
        product: productPayload,
        selling_points: sellingPoints,
        storyboard_reference_urls: storyboardReferences.map(item => item.url),
        creative_brief: storyboardCreativeBrief,
        language_model: languageModel,
        image_model: imageModel,
        video_model: videoModel,
        aspect_ratio: veoMode ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio,
        duration: storyboardDuration,
        variant_count: storyboardCount,
        creative_seed: creativeSeed,
        regenerate_index: regenerateIndex,
      })
      setScenes((result.scenes || []).map(normalizeScene))
      setBatchResult(null)
      setFinalVideo(null)
      setFinalClips([])
      const warning = result.warnings?.[0]
      const info = result.warnings?.[1]
      const routeText = result.creative_route?.name ? `创意路线：${result.creative_route.name}。` : ''
      setNotice({
        type: warning ? 'warning' : 'success',
        text: warning ? `${warning}${routeText ? ` ${routeText}` : ''}` : routeText + (info || '分镜计划已生成。'),
      })
    } catch (error) {
      setNotice({ type: 'error', text: `分镜计划生成失败：${displayError(error)}` })
    } finally {
      finishLoading('storyboard')
    }
  }

  function buildMatrixScene(point, angle, mood, combinationIndex, variantIndex, totalCount) {
    const productName = product.name.trim() || '产品'
    const category = product.category.trim() || '电商产品'
    const pointTitle = point.title || `卖点 ${combinationIndex + 1}`
    const pointDescription = point.description || pointTitle
    const evidence = point.evidence ? `直播依据：${point.evidence}` : ''
    const variantText = variantIndex > 0 ? `变体 ${variantIndex + 1}` : ''
    const title = `${pointTitle} · ${angle.label} · ${mood.label}${variantText ? ` · ${variantText}` : ''}`
    const hook = `${pointTitle}，${angle.label}呈现`
    const sceneAnchor = `${angle.label}、${mood.label}的真实户外运动场景`
    const sharedRules = [
      `产品：${productName}，类目：${category}。`,
      `核心卖点：${pointTitle}。${pointDescription}`,
      evidence,
      '产品外观完全以当前参考图锁定，外观细节不在文字里二次发挥；必须保持同一件产品的结构、比例、材质和关键细节一致。',
      product.detailSheetUrl ? '优先参考产品完整形态还原图，所有镜头中的产品必须与该图一致。' : '优先参考已上传产品图，不能重新设计产品。',
      '不要出现价格、二维码、购买按钮、直播主播、夸张促销大字或无关品牌；不要出现对比、测评式演示、道具验证、实验化场景或硬性证明画面。',
    ].filter(Boolean).join(' ')
    const imagePrompt = [
      `【矩阵分镜 ${combinationIndex + 1}/${totalCount}】${sharedRules}`,
      '【用途】生成首帧图片 @图片1，用于后续视频生成的首帧/构图参考。',
      `【场景锚点】${sceneAnchor}，作为整段 ${requestedVideoDuration} 秒视频的首帧、场景、光线和动作起点；镜头后续只在同一场景内自然推进到同一产品的英雄近景、材质微距或产品样式收束。`,
      '【穿着状态】如果该分镜包含脚步、行走、奔跑、踩水、转向、贴地跟拍等穿着使用动作，首帧图片必须有人穿着当前产品，出现真人脚部/下肢与产品的真实穿着关系；不要生成空鞋、孤立产品或静物摆拍。',
      `角度：${angle.label}。${angle.imagePrompt}`,
      `感觉：${mood.label}。${mood.imagePrompt}`,
      '输出一张适合后续视频生成的首帧/分镜图，主体清晰，构图稳定，产品不能被遮挡；画面只体现当前产品在运动户外场景中的质感。',
    ].join(' ')
    const videoPrompt = [
      `【技术参数】${aspectRatio}，${requestedVideoDuration}秒，24fps，高级运动户外品牌广告大片，中文自然语言提示词。`,
      `【参考素材】@图片1为本分镜首帧、构图、场景、光线和动作起点，负责整段 ${requestedVideoDuration} 秒的同一广告场景；镜头只在同一场景内自然推进到同一产品的英雄近景、材质微距或产品样式收束，产品外观以产品参考图/产品完整形态还原图为准，外观细节不在文字里二次发挥。`,
      `【视频目标】围绕“${pointTitle}”制作 ${angle.label} × ${mood.label} 的运动户外品牌广告片段，只拍当前这件产品在户外运动中的状态。`,
      sharedRules,
      `镜头角度：${angle.videoPrompt}`,
      `画面感觉：${mood.videoPrompt}`,
      `卖点表达：让“${pointTitle}”自然体现在运动动作、脚步状态、材质质感、光影和环境互动里，不用字幕或对比讲解。`,
      `【时间戳分镜】0-${requestedVideoDuration}秒：一个完整连贯的单场景户外广告镜头，低机位或手持跟随产品进入画面，脚步、转向、踩水、越过碎石或奔走动作自然展开，卖点在运动状态里出现；镜头可在同一场景内推进到产品英雄近景、材质微距、轮廓、鞋底或水珠细节，结尾收束回产品本身的样式、轮廓、材质和广告主视觉。`,
      '产品必须始终清晰可辨，不能变形、换款或混入其他产品。',
      '【音效】只写真实现场音效，例如脚步声、风声、水花声、材质摩擦声，必须与画面动作同步。',
      '【声音限制】生成阶段不要旁白、配音、人声、口播、唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点。',
      '【禁止项】不要字幕、屏幕文字、价格、二维码、水印、主播画面或直播带货口播；不要对比、测评式演示、道具验证、实验化场景或硬性证明画面。',
    ].join(' ')
    return normalizeScene({
      id: `matrix_${Date.now()}_${combinationIndex}_${variantIndex}_${Math.random().toString(36).slice(2, 7)}`,
      title,
      selling_point: pointTitle,
      hook,
      image_prompt: imagePrompt,
      video_prompt: videoPrompt,
      voiceover_text: buildDefaultVoiceover({ selling_point: pointTitle, hook }, combinationIndex),
      shot_notes: `${angle.label} / ${mood.label} / ${pointTitle}`,
      status: 'draft',
      error: '',
    }, combinationIndex)
  }

  function createMatrixScenes() {
    const points = matrixSourcePoints
    if (!points.length) return []
    const angles = PRODUCTION_MATRIX_ANGLES.filter(item => productionMatrix.angleIds.includes(item.id))
    const moods = PRODUCTION_MATRIX_MOODS.filter(item => productionMatrix.moodIds.includes(item.id))
    const totalPossible = points.length * angles.length * moods.length * productionMatrix.scenesPerCombination
    const totalCount = Math.min(totalPossible, productionMatrix.maxScenes)
    const nextScenes = []
    outer:
    for (const point of points) {
      for (const angle of angles) {
        for (const mood of moods) {
          for (let variantIndex = 0; variantIndex < productionMatrix.scenesPerCombination; variantIndex += 1) {
            nextScenes.push(buildMatrixScene(point, angle, mood, nextScenes.length, variantIndex, totalCount))
            if (nextScenes.length >= productionMatrix.maxScenes) break outer
          }
        }
      }
    }
    return nextScenes
  }

  function handleGenerateMatrixScenes(mode = 'replace') {
    if (!product.name.trim()) {
      setNotice({ type: 'warning', text: '请先填写产品名称，再生成批量生产矩阵。' })
      return
    }
    const matrixScenes = createMatrixScenes()
    if (!matrixScenes.length) {
      setNotice({ type: 'warning', text: '请先整理卖点，或在手动卖点里至少填写一条。' })
      return
    }
    setScenes(prev => mode === 'append' ? [...prev, ...matrixScenes] : matrixScenes)
    setBatchResult(null)
    setFinalVideo(null)
    if (mode !== 'append') setFinalClips([])
    setNotice({
      type: 'success',
      text: `已${mode === 'append' ? '追加' : '生成'} ${matrixScenes.length} 条矩阵分镜草稿，可继续批量生成分镜图和视频。`,
    })
  }

  function handleAppendProductDetailEndingScene() {
    if (!product.detailSheetUrl) {
      setNotice({ type: 'warning', text: '请先在 Image2 还原历史里选择最终版产品还原图。' })
      return
    }
    const nextScene = buildProductDetailEndingScene(product, isVeoModel(videoModel) ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio, requestedVideoDuration)
    setScenes(prev => {
      const withoutOld = prev.filter(scene => scene.referenceMode !== 'product_detail')
      return [...withoutOld, nextScene]
    })
    setFinalVideo(null)
    setFinalClips([])
    setNotice({ type: 'success', text: '已在分镜最后追加产品细节收尾镜头：将直接用最终版产品还原图生成视频，不需要分镜图。' })
  }

  async function handleStoryboardUpload(sceneId, files) {
    const taskKey = `storyboard-upload-${sceneId}`
    startLoading(taskKey)
    setNotice(null)
    try {
      const uploaded = await uploadFiles(files, 'image/')
      if (!uploaded.length) return
      const version = makeVersionItem(uploaded[0].url, {
        source: 'upload',
        label: uploaded[0].name || '上传分镜图',
      })
      updateScene(sceneId, {
        storyboard_image_url: uploaded[0].url,
        storyboardImageHistory: mergeVersionHistory(
          scenes.find(item => item.id === sceneId)?.storyboardImageHistory,
          version,
        ),
        status: 'storyboard_ready',
        error: '',
      })
    } catch (error) {
      setNotice({ type: 'error', text: `分镜图上传失败：${displayError(error)}` })
    } finally {
      finishLoading(taskKey)
    }
  }

  async function handleGenerateStoryboardImage(scene) {
    if (isUnsupportedModel(imageModel, imageModels)) {
      setNotice({ type: 'warning', text: '当前图片模型还没有接入适配器，请切换 Seedream 或先上传分镜图。' })
      return
    }
    const productReferences = product.detailSheetUrl ? [product.detailSheetUrl] : []
    if (!productReferences.length) {
      setNotice({ type: 'warning', text: '请先在 Image2 还原历史里选择最终版产品还原图，再生成分镜图。' })
      return
    }
    const taskKey = `image-${scene.id}`
    startLoading(taskKey)
    updateScene(scene.id, { status: 'image_generating', error: '' })
    try {
      const provider = providerForModel(imageModel, imageModels, 'jimeng')
      const referencePrompt = [
        '【参考】@产品参考图 只使用当前选中的最终版 Image2 产品完整形态还原图作为唯一参考图；产品外观由参考图锁定，外观细节不在文字里二次发挥，保持同一个产品的轮廓、材质、结构、鞋面/鞋底/扣具/纹理等关键细节。',
        '不要改变产品品类，不要自行改款，不要添加无关配件。',
        sanitizeStoryboardPromptText(scene.image_prompt),
      ].filter(Boolean).join(' ')
      const result = await api.post('/api/game/generate_image', {
        project_id: '',
        prompt: referencePrompt,
        provider,
        model: imageModel,
        aspect_ratio: aspectRatio,
        asset_type: 'scene',
        reference_urls: productReferences,
        prompt_optimize_mode: 'standard',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回图片地址')
      const version = makeVersionItem(imageUrl, {
        prompt: referencePrompt,
        source: imageModel,
        label: `分镜图 ${new Date().toLocaleTimeString()}`,
      })
      updateScene(scene.id, {
        storyboard_image_url: imageUrl,
        storyboardImageHistory: mergeVersionHistory(scene.storyboardImageHistory, version),
        status: 'storyboard_ready',
      })
    } catch (error) {
      updateScene(scene.id, { status: 'failed', error: displayError(error) })
      setNotice({ type: 'error', text: `分镜图生成失败：${displayError(error)}` })
    } finally {
      finishLoading(taskKey)
    }
  }

  async function handleGenerateVideo(scene) {
    if (isUnsupportedModel(videoModel, videoModels)) {
      setNotice({ type: 'warning', text: '当前视频模型还没有接入适配器，请切换 Seedance/HappyHorse 后生成。' })
      return
    }
    const selectedModel = videoModels.find(item => item.id === videoModel)
    const provider = providerForModel(videoModel, videoModels, 'jimeng')
    const isProductDetailEnding = scene.referenceMode === 'product_detail'
    if (isProductDetailEnding && !product.detailSheetUrl) {
      setNotice({ type: 'warning', text: '请先在 Image2 还原历史里选择最终版产品还原图，再生成产品细节收尾视频。' })
      return
    }
    if (!isProductDetailEnding && !scene.storyboard_image_url) {
      setNotice({ type: 'warning', text: '请先生成或上传当前分镜图，分镜图才会作为生成视频的参考图。' })
      return
    }
    const taskKey = `video-${scene.id}`
    startLoading(taskKey)
    updateScene(scene.id, {
      status: 'video_generating',
      error: '',
      taskId: '',
      videoProgress: 0.05,
      videoProgressMessage: '正在提交视频生成任务',
      videoStartedAt: Date.now(),
    })
    try {
      const refImages = isProductDetailEnding ? [product.detailSheetUrl] : collectVideoReferenceImages({ scene })
      const seedanceFirstFrameControl = videoModel === 'doubao-seedance-1-5-pro'
        ? `【首帧控制】Seedance 1.5 Pro 已把当前${isProductDetailEnding ? '产品还原图' : '分镜图'}作为 image_with_roles.first_frame 输入；第一秒必须从这张图延续，不允许重画成另一双鞋。`
        : ''
      const productIdentityLock = [
        `【产品身份锁定】@图片1/第 1 张参考图就是唯一真实产品身份；视频只能拍这双鞋${isProductDetailEnding ? '本身的产品细节' : '运动'}，不能生成另一双鞋。`,
        '必须保持首帧里所有高辨识度外观特征：鞋身轮廓、鞋底齿形、中底包边、侧面大面积品牌字母/图形、鞋带、鞋眼、鞋帮高度、材质纹理和整体比例。',
        '不要泛化成普通黑灰跑鞋，不要换品牌标识、不要换鞋底结构、不要把高辨识度撞色区域改掉；如果模型难以稳定跟随，宁可减少脚步幅度和镜头运动，也要保住同一双鞋。',
      ].join(' ')
      const referenceVideoPrompt = [
        seedanceFirstFrameControl,
        productIdentityLock,
        isProductDetailEnding
          ? '【视频参考图】第 1 张参考图就是当前最终版 Image2 产品完整形态还原图；本条视频不要使用分镜图，不要出现人穿着、走路、脚步或真人身体部位，只拍产品本身的材质、轮廓、鞋底、包边、logo 区域和关键细节。'
          : provider === 'toapis'
          ? '【视频参考图】第 1 张参考图就是当前选中的最终版分镜图，视频必须以这张分镜图作为首帧、构图、场景、光线、产品外观和动作起点，不要再参考原始产品图或产品还原图。'
          : '【视频参考图】@图片1 就是当前选中的最终版分镜图，请以它作为首帧、构图、场景、光线、产品外观和动作起点。',
        isProductDetailEnding
          ? '必须保持产品还原图里的产品外观、材质、结构、比例、鞋面/鞋底/扣具/纹理等关键细节一致，不要重新设计产品，不要自行改款。'
          : '必须保持分镜图里的产品外观、材质、结构、比例、鞋面/鞋底/扣具/纹理等关键细节一致，不要重新设计产品，不要自行改款。',
        isProductDetailEnding
          ? '【广告大片要求】这是最后一段视频细节收尾镜头，画面只体现产品本身：微距扫光、慢推、环绕、鞋面材质、鞋底纹理、包边结构、logo 区域和轮廓比例；不要人穿着，不要走路，不要动作使用场景。'
          : '【广告大片要求】延续分镜图的同一个户外场景，不要做普通商品展示、说明书式功能演示、对比、痛点反转或测试感画面；卖点要通过运动动作、户外环境、材质质感和光影自然体现。',
        isProductDetailEnding
          ? '【镜头质感】高级运动户外品牌产品 hero shot，浅景深、自然扫光、材质微距、轻微镜头推进和稳定收束，最后停在产品本身的样式和细节上，方便过渡到海报。'
          : '【镜头质感】使用低机位英雄跟拍、逆光轮廓、浅景深、慢动作水花/尘土/水雾、材质微距和自然脚步节奏，让产品像高级运动户外品牌广告主角。',
        isProductDetailEnding
          ? '【声音限制】生成阶段不要旁白、配音、人声、口播、唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点；只保留极轻微材质声、风声或环境氛围声，不要脚步声。'
          : '【声音限制】生成阶段不要旁白、配音、人声、口播、唱歌、吟唱、Rap、歌词化表达或音乐化念白；不要背景音乐、BGM、配乐、音乐节奏或鼓点；只保留脚步、风声、水花、材质与地面轻微摩擦等真实现场音效。',
        isProductDetailEnding
          ? '【禁止项】不要人穿着、不要走路、不要真人脚或腿、不要踩水奔跑、不要字幕、价格、二维码、水印、主播画面、促销大字、对比测试或说明书演示。'
          : '【禁止测试结构】不要对比、测评式演示、道具验证、实验化场景或硬性证明画面。',
        sanitizeStoryboardVideoPromptText(scene.video_prompt),
      ].filter(Boolean).join(' ')
      const firstFrameOnly = videoModel === 'happyhorse-1.0-i2v' || videoModel.startsWith('vidu')
      const referenceImageMode = provider === 'toapis'
      const requestDuration = videoModelRequestedDuration(selectedModel, duration)
      const requestAspectRatio = referenceImageMode ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio
      const body = {
        project_id: '',
        prompt: referenceVideoPrompt,
        provider,
        model: videoModel,
        duration: requestDuration,
        aspect_ratio: requestAspectRatio,
        resolution: videoResolution,
        image_url: firstFrameOnly || referenceImageMode ? (refImages[0] || '') : '',
        character_refs: [],
        scene_refs: firstFrameOnly || referenceImageMode ? [] : refImages,
        reference_video_url: '',
        advanced_reference_videos: [],
        generate_audio: false,
      }
      const result = await api.post('/api/game/generate_video', body)
      const videoUrl = readMediaUrl(result)
      if (videoUrl) {
        const version = makeVersionItem(videoUrl, {
          prompt: referenceVideoPrompt,
          source: videoModel,
          label: `视频 ${new Date().toLocaleTimeString()}`,
        })
        updateScene(scene.id, {
          status: 'completed',
          video_url: videoUrl,
          videoHistory: mergeVersionHistory(scene.videoHistory, version),
          taskId: '',
          videoProgress: null,
          videoProgressMessage: '',
          videoStartedAt: 0,
          error: '',
        })
      } else if (result.task_id) {
        updateScene(scene.id, {
          status: 'processing',
          taskId: result.task_id,
          error: '',
          videoProgress: 0.08,
          videoProgressMessage: '任务已提交，正在等待模型生成',
        })
        registerTaskPolling(result.task_id, updates => {
          const nextVideoUrl = updates.videoUrl || updates.video_url || ''
          const nextProgress = normalizeProgressValue(updates.progress)
          const isDone = nextVideoUrl || isCompletedTaskStatus(updates.status)
          const isFailed = String(updates.status || '').toLowerCase() === 'failed'
          updateSceneWith(scene.id, currentScene => ({
            status: updates.status || 'processing',
            video_url: nextVideoUrl,
            videoHistory: nextVideoUrl
              ? mergeVersionHistory(currentScene.videoHistory, makeVersionItem(nextVideoUrl, {
                prompt: referenceVideoPrompt,
                source: videoModel,
                taskId: result.task_id,
                label: `视频 ${new Date().toLocaleTimeString()}`,
              }))
              : currentScene.videoHistory,
            error: updates.error || '',
            taskId: updates.taskId ?? result.task_id,
            videoProgress: isDone || isFailed ? null : (nextProgress ?? currentScene.videoProgress),
            videoProgressMessage: isDone || isFailed ? '' : (updates.message || currentScene.videoProgressMessage),
            videoStartedAt: isDone || isFailed ? 0 : currentScene.videoStartedAt,
          }))
        })
      } else {
        updateScene(scene.id, {
          status: 'processing',
          error: '',
          taskId: '',
          videoProgress: 0.08,
          videoProgressMessage: '模型已接收请求，正在等待返回任务 ID',
        })
      }
    } catch (error) {
      updateScene(scene.id, {
        status: 'failed',
        error: displayError(error),
        taskId: '',
        videoProgress: null,
        videoProgressMessage: '',
        videoStartedAt: 0,
      })
      setNotice({ type: 'error', text: `视频生成失败：${displayError(error)}` })
    } finally {
      finishLoading(taskKey)
    }
  }

  async function handleRetryVideoResult(scene) {
    if (!scene?.taskId) {
      setNotice({ type: 'warning', text: '缺少任务 ID，无法重新拉取视频结果。' })
      return
    }
    const taskKey = `video-retry-${scene.id}`
    startLoading(taskKey)
    setNotice(null)
    updateScene(scene.id, {
      status: 'processing',
      error: '正在重新拉取视频结果...',
      videoProgress: scene.videoProgress ?? 0.12,
      videoProgressMessage: '正在重新拉取视频结果',
      videoStartedAt: scene.videoStartedAt || Date.now(),
    })
    try {
      const result = await api.post(`/api/game/tasks/${encodeURIComponent(scene.taskId)}/retry-cache`, {})
      const status = String(result?.status || '').toLowerCase()
      const videoUrl = readMediaUrl(result)
      const taskId = result?.task_id || scene.taskId
      if (isCompletedTaskStatus(status) && videoUrl) {
        const version = makeVersionItem(videoUrl, {
          source: videoModel,
          taskId,
          label: `视频 ${new Date().toLocaleTimeString()}`,
        })
        updateScene(scene.id, {
          status: 'completed',
          video_url: videoUrl,
          videoHistory: mergeVersionHistory(scene.videoHistory, version),
          taskId: '',
          videoProgress: null,
          videoProgressMessage: '',
          videoStartedAt: 0,
          error: '',
        })
        setNotice({ type: 'success', text: '视频结果已取回，可以预览了。' })
        return
      }
      if (isProcessingTaskStatus(status)) {
        updateScene(scene.id, {
          status: 'processing',
          taskId,
          error: '',
          videoProgress: normalizeProgressValue(result?.progress) ?? scene.videoProgress ?? 0.12,
          videoProgressMessage: result?.message || '任务仍在处理中',
          videoStartedAt: scene.videoStartedAt || Date.now(),
        })
        registerTaskPolling(taskId, updates => {
          const nextVideoUrl = updates.videoUrl || updates.video_url || ''
          const nextProgress = normalizeProgressValue(updates.progress)
          const isDone = nextVideoUrl || isCompletedTaskStatus(updates.status)
          const isFailed = String(updates.status || '').toLowerCase() === 'failed'
          updateSceneWith(scene.id, currentScene => ({
            status: updates.status || 'processing',
            video_url: nextVideoUrl,
            videoHistory: nextVideoUrl
              ? mergeVersionHistory(currentScene.videoHistory, makeVersionItem(nextVideoUrl, {
                source: videoModel,
                taskId,
                label: `视频 ${new Date().toLocaleTimeString()}`,
              }))
              : currentScene.videoHistory,
            error: updates.error || '',
            taskId: updates.taskId ?? taskId,
            videoProgress: isDone || isFailed ? null : (nextProgress ?? currentScene.videoProgress),
            videoProgressMessage: isDone || isFailed ? '' : (updates.message || currentScene.videoProgressMessage),
            videoStartedAt: isDone || isFailed ? 0 : currentScene.videoStartedAt,
          }))
        })
        return
      }
      updateScene(scene.id, {
        status: 'failed',
        taskId,
        error: displayError(result?.error || result?.message || '重新拉取视频结果失败，请重新生成。'),
        videoProgress: null,
        videoProgressMessage: '',
        videoStartedAt: 0,
      })
    } catch (error) {
      updateScene(scene.id, {
        status: 'failed',
        taskId: scene.taskId,
        error: displayError(error),
        videoProgress: null,
        videoProgressMessage: '',
        videoStartedAt: 0,
      })
      setNotice({ type: 'error', text: `重新拉取视频结果失败：${displayError(error)}` })
    } finally {
      finishLoading(taskKey)
    }
  }

  async function handleSubmitBatch() {
    if (!scenes.length) {
      setNotice({ type: 'warning', text: '请先生成分镜计划。' })
      return
    }
    startLoading('submit')
    setNotice(null)
    try {
      const veoMode = isVeoModel(videoModel)
      const result = await api.post('/api/batch-video/submit', {
        product: productPayload,
        scenes,
        image_model: imageModel,
        video_model: videoModel,
        aspect_ratio: veoMode ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio,
        duration: veoMode ? 8 : duration,
        resolution: videoResolution,
      })
      setBatchResult(result)
      setNotice({ type: 'success', text: result.message || '批量任务已整理完成。' })
    } catch (error) {
      setNotice({ type: 'error', text: `批量任务整理失败：${displayError(error)}` })
    } finally {
      finishLoading('submit')
    }
  }

  async function handleComposeFinalVideo() {
    const usableFinalClips = finalClips.filter(clip => clip.videoUrl)
    const defaultFinalClips = buildDefaultFinalClips(scenes)
    const sourceClips = usableFinalClips.length ? finalClips : defaultFinalClips
    const segments = sourceClips
      .map((clip, index) => {
        const scene = scenes.find(item => item.id === clip.sceneId) || {}
        const hasClipVoiceover = Object.prototype.hasOwnProperty.call(clip, 'voiceoverText')
          || Object.prototype.hasOwnProperty.call(clip, 'subtitle')
        const voiceoverText = hasClipVoiceover
          ? String(clip.voiceoverText ?? clip.subtitle ?? '').trim()
          : String(scene.voiceover_text || '').trim()
        return {
          scene_id: clip.sceneId || scene.id || `clip_${index + 1}`,
          title: clip.title || scene.title || `片段 ${index + 1}`,
          reference_mode: scene.referenceMode || scene.reference_mode || '',
          video_url: clip.videoUrl,
          start_time: clip.startTime === '' ? 0 : Number(clip.startTime || 0),
          end_time: clip.endTime === '' ? null : Number(clip.endTime),
          subtitle: voiceoverText,
          voiceover_text: voiceoverText,
        }
      })
      .filter(segment => segment.video_url)
    if (!segments.length) {
      setNotice({ type: 'warning', text: '请先为分镜选择最终视频版本，再合成完整视频。' })
      return
    }
    if (!productPosterUrl) {
      setNotice({ type: 'warning', text: '请先在“收尾产品海报”区域生成或选择海报，再拼接完整视频。' })
      return
    }
    if (!finalClips.length || (!usableFinalClips.length && defaultFinalClips.length)) {
      setFinalClips(sourceClips)
      setNotice({ type: 'warning', text: '还没有剪辑表，已先按当前最终视频自动生成剪辑片段。' })
    } else if (segments.length < finalClips.length) {
      setNotice({ type: 'warning', text: `还有 ${finalClips.length - segments.length} 个剪辑片段未选择视频，已先合成可用片段。` })
    } else {
      setNotice(null)
    }
    startLoading('compose-final-video')
    try {
      const selectedTtsVoiceType = ttsVoiceType === 'custom' ? ttsCustomVoiceType.trim() : ttsVoiceType
      const selectedBgmVolume = clampNumber(bgmVolume, 0, 1, 0.45)
      const result = await api.post('/api/batch-video/compose-final-video', {
        segments,
        product_name: product.name || '',
        aspect_ratio: isVeoModel(videoModel) ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio,
        subtitle_enabled: true,
        voiceover_enabled: true,
        keep_original_audio: true,
        bgm_enabled: bgmEnabled,
        bgm_url: bgmEnabled ? bgmUrl : '',
        original_audio_volume: 0.78,
        voiceover_volume: 1,
        bgm_volume: selectedBgmVolume,
        poster_image_url: productPosterUrl || '',
        poster_duration: 0,
        tts_provider: 'doubao_speech_2_0',
        tts_voice_type: selectedTtsVoiceType,
        tts_speed_ratio: Number(ttsSpeedRatio) || 1,
        output_name: product.name || 'batch_final_video',
      })
      if (result.status !== 'completed' || !result.video_url) {
        setNotice({ type: result.status === 'needs_video' ? 'warning' : 'error', text: result.message || '完整视频合成失败。' })
        return
      }
      setFinalVideo(result)
      setNotice({
        type: result.voiceover_error ? 'warning' : 'success',
        text: result.message || (result.voiceover_generated ? '完整视频已合成，并已加入豆包语音合成 2.0 旁白。' : '完整视频已合成。'),
      })
    } catch (error) {
      setNotice({ type: 'error', text: `完整视频合成失败：${displayError(error)}` })
    } finally {
      finishLoading('compose-final-video')
    }
  }

  const hasSceneVideos = scenes.some(scene => scene.video_url)
  const hasUsableFinalClips = finalClips.some(clip => clip.videoUrl)
  const canComposeFinalVideo = hasSceneVideos || hasUsableFinalClips

  return (
    <div className="batch-video-workbench">
      <header className="batch-video-header">
        <div>
          <div className="batch-video-kicker"><Boxes size={16} /> 电商素材平台</div>
          <h1><Clapperboard size={30} /> 批量生成视频工作台</h1>
        </div>
        <div className="batch-video-actions">
          <ModelSelect label="语言模型" value={languageModel} onChange={setLanguageModel} models={languageModels} />
          <ModelSelect label="图片模型" value={imageModel} onChange={setImageModel} models={imageModels} />
          <ModelSelect label="视频模型" value={videoModel} onChange={setVideoModel} models={videoModels} />
          <button
            type="button"
            className="batch-video-button ghost batch-video-draft-clear"
            onClick={handleClearDraft}
          >
            <Trash2 size={15} />
            清空草稿
          </button>
        </div>
      </header>

      <StatusNotice notice={notice} />

      <div className="batch-video-grid">
        <section className="batch-video-panel product-panel">
          <div className="batch-video-panel-title">
            <Package size={18} />
            <h2>产品输入</h2>
          </div>
          <div className="batch-video-form-grid">
            <label className="batch-video-field">
              <span>产品名称</span>
              <input
                value={product.name}
                onChange={event => updateProduct('name', event.target.value)}
                placeholder="例如：户外折叠露营椅"
              />
            </label>
            <label className="batch-video-field">
              <span>类目</span>
              <input
                value={product.category}
                onChange={event => updateProduct('category', event.target.value)}
                placeholder="例如：家居 / 服饰 / 户外"
              />
            </label>
          </div>
          {product.name.trim() && productMemoryStatus.text && (
            <div className={`batch-video-product-memory ${productMemoryStatus.state || 'idle'}`}>
              <RefreshCw size={13} className={productMemoryStatus.state === 'checking' || productMemoryStatus.state === 'saving' ? 'spin' : ''} />
              <span>{productMemoryStatus.text}</span>
            </div>
          )}
          <label className="batch-video-field">
            <span>产品说明</span>
            <textarea
              value={product.description}
              onChange={event => updateProduct('description', event.target.value)}
              placeholder="可填写材质、功能、适用人群、价格带等"
              rows={4}
            />
          </label>
          <label className="batch-video-upload-zone">
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={event => {
                void handleProductImages(event.target.files)
                event.target.value = ''
              }}
            />
            <Upload size={18} />
            <span>{isLoading('product-images') ? '上传中...' : '上传产品图片'}</span>
          </label>
          {product.imageUrls.length > 0 && (
            <div className="batch-video-thumb-grid">
              {product.imageUrls.map((image, index) => (
                <div className="batch-video-thumb" key={`${image.url}-${index}`}>
                  <img src={assetUrl(image.url)} alt={image.name || `产品图 ${index + 1}`} />
                  <button
                    type="button"
                    title="移除"
                    onClick={() => setProduct(prev => ({
                      ...prev,
                      imageUrls: prev.imageUrls.filter((_, itemIndex) => itemIndex !== index),
                    }))}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="batch-video-product-reconstruction">
            <div className="batch-video-product-reconstruction-head">
              <div>
                <strong>产品完整形态详情表</strong>
                <span>按八宫格生成正视图、左侧视图、右侧视图、俯视图、仰视图和细节特写</span>
              </div>
              <button
                type="button"
                className="batch-video-button primary"
                onClick={handleGenerateProductDetailSheet}
                disabled={isLoading('product-detail-sheet') || !product.imageUrls.length}
              >
                <ImageIcon size={15} />
                {isLoading('product-detail-sheet') ? '还原中...' : 'Image2 还原'}
              </button>
            </div>
            {product.detailSheetUrl ? (
              <div className="batch-video-product-sheet">
                <img src={assetUrl(product.detailSheetUrl)} alt="产品完整形态详情表" />
                <button
                  type="button"
                  className="batch-video-button ghost"
                  onClick={() => setProduct(prev => ({ ...prev, detailSheetUrl: '', detailSheetPrompt: '' }))}
                >
                  <Trash2 size={14} />
                  清除详情表
                </button>
              </div>
            ) : (
              <div className="batch-video-product-sheet-empty">
                <ImageIcon size={22} />
                <span>上传多张产品参考图后生成统一产品形态</span>
              </div>
            )}
            <VersionStrip
              title="Image2 还原历史"
              versions={product.detailSheetHistory}
              activeUrl={product.detailSheetUrl}
              onSelect={selectDetailSheetVersion}
            />
          </div>
        </section>

        <section className="batch-video-panel transcript-panel">
          <div className="batch-video-panel-title">
            <Mic2 size={18} />
            <h2>直播转写与卖点</h2>
          </div>
          <div className="batch-video-inline">
            <label className="batch-video-upload-zone compact">
              <input
                type="file"
                accept="video/*"
                onChange={event => {
                  void handleLiveVideo(event.target.files)
                  event.target.value = ''
                }}
              />
              <FileVideo size={17} />
              <span>{isLoading('live-video') ? '上传中...' : '上传直播视频'}</span>
            </label>
            <button
              type="button"
              className="batch-video-button ghost"
              onClick={handleTranscribe}
              disabled={isLoading('transcribe')}
            >
              <Mic2 size={16} />
              {isLoading('transcribe') ? '转写中' : '豆包 ASR 转写'}
            </button>
          </div>
          {asrInfo && (
            <div className={`batch-video-asr-status ${asrInfo.configured || asrInfo.available ? 'ready' : 'missing'}`}>
              <Mic2 size={14} />
              <span>
                {asrInfo.configured || asrInfo.available
                  ? '豆包语音 ASR 已配置'
                  : `豆包语音 ASR 待配置：系统设置或电商素材 API 设置中填写 API Key`}
              </span>
            </div>
          )}
          {liveVideo && (
            <div className="batch-video-file-line">
              <Video size={15} />
              <span>{liveVideo.name}</span>
            </div>
          )}
          <label className="batch-video-field">
            <span>直播转写文本</span>
            <textarea
              value={transcript}
              onChange={event => setTranscript(event.target.value)}
              placeholder="可以粘贴直播口播转写文本"
              rows={6}
            />
          </label>
          <label className="batch-video-field">
            <span>手动卖点</span>
            <textarea
              value={manualSellingPoints}
              onChange={event => setManualSellingPoints(event.target.value)}
              placeholder="一行一个卖点；留空则根据直播文本生成草稿"
              rows={4}
            />
          </label>
          <button
            type="button"
            className="batch-video-button primary"
            onClick={handleSellingPoints}
            disabled={isLoading('selling-points')}
          >
            <Sparkles size={16} />
            {isLoading('selling-points') ? '整理中' : '生成/整理卖点'}
          </button>
          <div className="batch-video-selling-points">
            {sellingPoints.length ? sellingPoints.map((point, index) => (
              <div className="batch-video-selling-point-card" key={`${point.title || 'point'}-${index}`}>
                <div className="batch-video-selling-point-head">
                  <span>{index + 1}</span>
                  <input
                    value={point.title || ''}
                    onChange={event => updateSellingPoint(index, { title: event.target.value })}
                    aria-label={`卖点 ${index + 1} 标题`}
                  />
                  <button type="button" title="删除卖点" onClick={() => removeSellingPoint(index)}>
                    <Trash2 size={15} />
                  </button>
                </div>
                <label className="batch-video-field">
                  <span>说明</span>
                  <textarea
                    value={point.description || ''}
                    onChange={event => updateSellingPoint(index, { description: event.target.value })}
                    rows={2}
                  />
                </label>
                <label className="batch-video-field">
                  <span>直播依据</span>
                  <textarea
                    value={point.evidence || ''}
                    onChange={event => updateSellingPoint(index, { evidence: event.target.value })}
                    rows={2}
                  />
                </label>
              </div>
            )) : (
              <div className="batch-video-selling-points-empty">暂无卖点</div>
            )}
          </div>
        </section>
      </div>

      <section className="batch-video-panel matrix-panel">
        <div className="batch-video-panel-title">
          <Boxes size={18} />
          <h2>批量生产矩阵</h2>
        </div>
        <div className="batch-video-matrix-grid">
          <div className="batch-video-matrix-block">
            <div className="batch-video-matrix-block-head">
              <strong>卖点来源</strong>
              <span>{matrixSellingPointCount || 0} 个卖点</span>
            </div>
            <div className="batch-video-matrix-source">
              {matrixSellingPointCount ? (
                matrixSourcePoints.slice(0, 6).map((point, index) => (
                  <span key={`${point.title || 'point'}-${index}`}>{point.title || point.description || `卖点 ${index + 1}`}</span>
                ))
              ) : (
                <span className="muted">先整理卖点或填写手动卖点</span>
              )}
            </div>
          </div>
          <div className="batch-video-matrix-block">
            <div className="batch-video-matrix-block-head">
              <strong>角度</strong>
              <span>{productionMatrix.angleIds.length} 个</span>
            </div>
            <div className="batch-video-chip-grid">
              {PRODUCTION_MATRIX_ANGLES.map(angle => (
                <button
                  type="button"
                  key={angle.id}
                  className={`batch-video-chip ${productionMatrix.angleIds.includes(angle.id) ? 'is-selected' : ''}`}
                  onClick={() => toggleMatrixAngle(angle.id)}
                  title={angle.videoPrompt}
                >
                  {angle.label}
                </button>
              ))}
            </div>
          </div>
          <div className="batch-video-matrix-block">
            <div className="batch-video-matrix-block-head">
              <strong>感觉</strong>
              <span>{productionMatrix.moodIds.length} 个</span>
            </div>
            <div className="batch-video-chip-grid compact">
              {PRODUCTION_MATRIX_MOODS.map(mood => (
                <button
                  type="button"
                  key={mood.id}
                  className={`batch-video-chip ${productionMatrix.moodIds.includes(mood.id) ? 'is-selected' : ''}`}
                  onClick={() => toggleMatrixMood(mood.id)}
                  title={mood.videoPrompt}
                >
                  {mood.label}
                </button>
              ))}
            </div>
          </div>
          <div className="batch-video-matrix-block controls">
            <label className="batch-video-field compact-field">
              <span>每组条数</span>
              <input
                type="number"
                min="1"
                max="3"
                value={productionMatrix.scenesPerCombination}
                onChange={event => updateProductionMatrix({ scenesPerCombination: event.target.value })}
              />
            </label>
            <label className="batch-video-field compact-field">
              <span>最多分镜</span>
              <input
                type="number"
                min="1"
                max="60"
                value={productionMatrix.maxScenes}
                onChange={event => updateProductionMatrix({ maxScenes: event.target.value })}
              />
            </label>
          </div>
        </div>
        <div className="batch-video-matrix-summary">
          <span>预计生成 <strong>{matrixDraftCount}</strong> 条分镜草稿</span>
          {matrixCostEstimate ? (
            <span>
              视频预算约 <strong>{matrixCostEstimate.amount}{matrixCostEstimate.unit}</strong>
              {matrixCostEstimate.amountCny > 0 ? ` / ${formatCurrencyCny(matrixCostEstimate.amountCny)} 人民币` : ''}
            </span>
          ) : (
            <span>选择视频模型并配置单价后显示预算</span>
          )}
          <div className="batch-video-matrix-actions">
            <button
              type="button"
              className="batch-video-button primary"
              onClick={() => handleGenerateMatrixScenes('replace')}
              disabled={!matrixDraftCount}
            >
              <Wand2 size={16} />
              生成矩阵草稿
            </button>
            <button
              type="button"
              className="batch-video-button ghost"
              onClick={() => handleGenerateMatrixScenes('append')}
              disabled={!matrixDraftCount}
            >
              <Plus size={16} />
              追加到现有分镜
            </button>
          </div>
        </div>
      </section>

      <section className="batch-video-panel storyboard-panel">
        <div className="batch-video-panel-title">
          <ListChecks size={18} />
          <h2>场景与分镜</h2>
        </div>
        <div className="batch-video-creative-brief">
          <label className="batch-video-field">
            <span>创作需求</span>
            <textarea
              value={storyboardCreativeBrief}
              onChange={event => setStoryboardCreativeBrief(event.target.value)}
              placeholder="例如：请根据上面的卖点，为我写6段5s的电商广告视频，画面要像户外品牌广告大片。"
              rows={3}
            />
          </label>
          <div className="batch-video-brief-meta">
            <span>Seedance 风格</span>
            {storyboardBriefPlan.sceneCount ? <span>{storyboardBriefPlan.sceneCount} 段</span> : null}
            {storyboardBriefPlan.duration ? <span>{storyboardBriefPlan.duration} 秒/段</span> : null}
            <span>图片首帧 + 视频分镜</span>
          </div>
        </div>
        <div className="batch-video-toolbar">
          <label className="batch-video-field compact-field">
            <span>画幅</span>
            <select value={aspectRatio} onChange={event => setAspectRatio(event.target.value)}>
              {ASPECT_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="batch-video-field compact-field">
            <span>清晰度</span>
            <select value={videoResolution} onChange={event => setVideoResolution(event.target.value)}>
              {videoResolutionOptions.map(option => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="batch-video-field compact-field">
            <span>时长</span>
            <select
              value={duration}
              onChange={event => setDuration(Number(event.target.value))}
              disabled={veoStoryboardMode}
            >
              {DURATION_OPTIONS
                .filter(option => {
                  const choices = Array.isArray(selectedVideoModel?.duration_choices)
                    ? selectedVideoModel.duration_choices.map(Number).filter(Boolean)
                    : []
                  if (choices.length) return choices.includes(option)
                  const min = Number(selectedVideoModel?.min_duration || 0)
                  const max = Number(selectedVideoModel?.max_duration || 0)
                  return (!min || option >= min) && (!max || option <= max)
                })
                .map(option => <option key={option} value={option}>{option} 秒</option>)}
            </select>
          </label>
          <label className="batch-video-field compact-field">
            <span>分镜数</span>
            <input
              type="number"
              min={storyboardDefaults.count}
              max="12"
              value={variantCount}
              disabled={veoStoryboardMode}
              onChange={event => setVariantCount(Math.max(storyboardDefaults.count, Number(event.target.value) || storyboardDefaults.count))}
            />
          </label>
          <button
            type="button"
            className="batch-video-button primary"
            onClick={handleStoryboardPlan}
            disabled={isLoading('storyboard')}
          >
            <Wand2 size={16} />
            {isLoading('storyboard') ? '生成中' : veoStoryboardMode ? '生成广告大片分镜' : '生成分镜计划'}
          </button>
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={() => setScenes(prev => [...prev, normalizeScene({}, prev.length)])}
          >
            <Plus size={16} />
            新增分镜
          </button>
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={handleAppendProductDetailEndingScene}
            disabled={!product.detailSheetUrl}
          >
            <Package size={16} />
            追加产品细节收尾镜头
          </button>
        </div>
        <div className="batch-video-cost-hint">
          <span>{selectedVideoModel?.name || videoModel}</span>
          <strong>{videoModelPriceText(selectedVideoModel) || '未标价'}</strong>
          {videoCostEstimate ? (
            <>
              <span>单条 {videoCostEstimate.seconds} 秒约 {videoCostEstimate.amount}{videoCostEstimate.unit}</span>
              {videoCostEstimate.amountCny > 0 ? (
                <strong>约 {formatCurrencyCny(videoCostEstimate.amountCny)} 人民币</strong>
              ) : (
                <span>人民币预估需配置积分单价</span>
              )}
            </>
          ) : (
            <span>单条视频费用需在设置页配置后显示</span>
          )}
        </div>

        <div className="batch-video-storyboard-reference-panel">
          <div className="batch-video-storyboard-reference-head">
            <div>
              <strong>创作参考图</strong>
              <span>仅用于生成分镜文案时参考构图、场景、光线和广告质感；生成分镜图时只上传当前最终版 Image2 产品还原图</span>
            </div>
            <label className="batch-video-button ghost file-button">
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={event => {
                  void handleStoryboardReferenceImages(event.target.files)
                  event.target.value = ''
                }}
              />
              <Upload size={15} />
              {isLoading('storyboard-references') ? '上传中...' : '上传创作参考'}
            </label>
          </div>
          {storyboardReferences.length > 0 && (
            <div className="batch-video-thumb-grid storyboard-reference-grid">
              {storyboardReferences.map((image, index) => (
                <div className="batch-video-thumb" key={`${image.url}-${index}`}>
                  <img src={assetUrl(image.url)} alt={image.name || `分镜参考图 ${index + 1}`} />
                  <button
                    type="button"
                    title="移除"
                    onClick={() => setStoryboardReferences(prev => prev.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="batch-video-scene-list">
          {scenes.length === 0 ? (
            <div className="batch-video-empty">
              <Clapperboard size={34} />
              <span>暂无分镜</span>
            </div>
          ) : scenes.map((scene, index) => {
            const isProductDetailEnding = scene.referenceMode === 'product_detail'
            const sceneVideoRefs = collectVideoReferenceImages({
              scene,
            })
            return (
            <article className="batch-video-scene-card" key={scene.id}>
              <div className="batch-video-scene-head">
                <div>
                  <span className="batch-video-scene-index">#{index + 1}</span>
                  <input
                    value={scene.title}
                    onChange={event => updateScene(scene.id, { title: event.target.value })}
                    aria-label="分镜标题"
                  />
                </div>
                <button
                  type="button"
                  title="删除分镜"
                  onClick={() => {
                    setScenes(prev => prev.filter(item => item.id !== scene.id))
                    setFinalClips(prev => prev.filter(clip => clip.sceneId !== scene.id))
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="batch-video-scene-body">
                <div className="batch-video-preview">
                  {isProductDetailEnding && product.detailSheetUrl ? (
                    <img src={assetUrl(product.detailSheetUrl)} alt="产品细节收尾参考图" />
                  ) : scene.storyboard_image_url ? (
                    <img src={assetUrl(scene.storyboard_image_url)} alt={scene.title} />
                  ) : (
                    <div className="batch-video-preview-empty">
                      <ImageIcon size={24} />
                      <span>分镜图</span>
                    </div>
                  )}
                  {scene.video_url && (
                    <video src={assetUrl(scene.video_url)} controls />
                  )}
                  {!scene.video_url && (
                    <div className={`batch-video-video-empty ${isProcessingTaskStatus(scene.status) ? 'processing' : ''}`}>
                      <Video size={22} />
                      <span>{videoSlotText(scene)}</span>
                      <VideoProgress scene={scene} />
                    </div>
                  )}
                </div>
                <div className="batch-video-scene-fields">
                  <label className="batch-video-field">
                    <span>卖点钩子 / 镜头目标</span>
                    <input
                      value={scene.hook}
                      onChange={event => updateScene(scene.id, { hook: event.target.value })}
                    />
                  </label>
                  <label className="batch-video-field">
                    <span>图片提示词</span>
                    <textarea
                      value={scene.image_prompt}
                      onChange={event => updateScene(scene.id, { image_prompt: event.target.value })}
                      rows={4}
                    />
                  </label>
                  <label className="batch-video-field">
                    <span>视频提示词（不含旁白）</span>
                    <textarea
                      value={scene.video_prompt}
                      onChange={event => updateScene(scene.id, { video_prompt: event.target.value })}
                      rows={4}
                    />
                  </label>
                  <label className="batch-video-field">
                    <span>旁白文案（最终配音/字幕）</span>
                    <textarea
                      value={scene.voiceover_text}
                      onChange={event => updateScene(scene.id, { voiceover_text: event.target.value })}
                      rows={2}
                    />
                  </label>
                  <label className="batch-video-field">
                    <span>镜头备注</span>
                    <input
                      value={scene.shot_notes}
                      onChange={event => updateScene(scene.id, { shot_notes: event.target.value })}
                    />
                  </label>
                </div>
              </div>
              <div className="batch-video-reference-hint">
                {isProductDetailEnding
                  ? `生成视频将直接使用当前最终版 Image2 产品还原图作为唯一参考图，不需要分镜图，也不要人穿着走路画面。`
                  : sceneVideoRefs.length
                  ? `生成视频将使用当前最终版分镜图作为唯一参考图。`
                  : `请先生成或上传分镜图，分镜图才会作为生成视频的参考图。`}
              </div>
              <VersionStrip
                title="分镜图历史"
                versions={scene.storyboardImageHistory}
                activeUrl={scene.storyboard_image_url}
                onSelect={version => selectStoryboardVersion(scene.id, version)}
              />
              <VersionStrip
                title="视频历史"
                versions={scene.videoHistory}
                activeUrl={scene.video_url}
                type="video"
                onSelect={version => selectVideoVersion(scene.id, version)}
              />
              {scene.error && <div className="batch-video-scene-error">{scene.error}</div>}
              {scene.taskId && <div className="batch-video-task-id">任务 ID：{scene.taskId}</div>}
              <div className="batch-video-scene-actions">
                <label className="batch-video-button ghost file-button">
                  <input
                    type="file"
                    accept="image/*"
                    disabled={isProductDetailEnding}
                    onChange={event => {
                      void handleStoryboardUpload(scene.id, event.target.files)
                      event.target.value = ''
                    }}
                  />
                  <Upload size={15} />
                  {isProductDetailEnding ? '不需上传分镜图' : '上传分镜图'}
                </label>
                <button
                  type="button"
                  className="batch-video-button ghost"
                  onClick={() => handleGenerateStoryboardImage(scene)}
                  disabled={isLoading(`image-${scene.id}`) || isProductDetailEnding}
                >
                  <ImageIcon size={15} />
                  {isProductDetailEnding ? '无需分镜图' : isLoading(`image-${scene.id}`) ? '生成中' : '生成分镜图'}
                </button>
                <button
                  type="button"
                  className="batch-video-button primary"
                  onClick={() => handleGenerateVideo(scene)}
                  disabled={isLoading(`video-${scene.id}`)}
                >
                  <Play size={15} />
                  {isLoading(`video-${scene.id}`) ? '提交中' : '生成视频'}
                </button>
                <button
                  type="button"
                  className="batch-video-button ghost"
                  onClick={() => appendFinalClipFromScene(scene)}
                  disabled={!scene.video_url}
                >
                  <Scissors size={15} />
                  加入剪辑
                </button>
                {scene.taskId && isRetryableVideoResultError(scene.error) && (
                  <button
                    type="button"
                    className="batch-video-button ghost"
                    onClick={() => handleRetryVideoResult(scene)}
                    disabled={isLoading(`video-retry-${scene.id}`)}
                  >
                    <RefreshCw size={15} />
                    {isLoading(`video-retry-${scene.id}`) ? '拉取中' : '重新拉取结果'}
                  </button>
                )}
              </div>
            </article>
          )})}
        </div>
      </section>

      <section className="batch-video-panel final-panel">
        <div className="batch-video-panel-title">
          <Scissors size={18} />
          <h2>完整视频</h2>
        </div>
        <div className="batch-video-tts-toolbar">
          <label className="batch-video-field">
            <span>旁白音色</span>
            <select value={ttsVoiceType} onChange={event => setTtsVoiceType(event.target.value)}>
              {TTS_VOICE_OPTIONS.map(option => (
                <option key={option.id || 'default'} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>
          {ttsVoiceType === 'custom' && (
            <label className="batch-video-field">
              <span>自定义 voice_type</span>
              <input
                value={ttsCustomVoiceType}
                onChange={event => setTtsCustomVoiceType(event.target.value)}
                placeholder="粘贴豆包语音控制台里的音色 ID"
              />
            </label>
          )}
          <label className="batch-video-field compact-field">
            <span>语速</span>
            <input
              type="number"
              min="0.6"
              max="1.4"
              step="0.05"
              value={ttsSpeedRatio}
              onChange={event => setTtsSpeedRatio(event.target.value)}
            />
          </label>
        </div>
        <div className="batch-video-bgm-toolbar">
          <label className="batch-video-audio-toggle">
            <input
              type="checkbox"
              checked={bgmEnabled}
              onChange={event => setBgmEnabled(event.target.checked)}
            />
            <span>加入 BGM</span>
          </label>
          <label className="batch-video-button ghost file-button">
            <Upload size={16} />
            {isLoading('bgm-upload') ? '上传中' : bgmUrl ? '更换 BGM' : '上传 BGM'}
            <input
              type="file"
              accept="audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg,.webm,.mp4"
              disabled={isLoading('bgm-upload')}
              onChange={event => {
                handleBgmUpload(event.target.files)
                event.target.value = ''
              }}
            />
          </label>
          <label className="batch-video-field batch-video-bgm-volume">
            <span>BGM 音量 {Math.round(clampNumber(bgmVolume, 0, 1, 0.45) * 100)}%</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={bgmVolume}
              disabled={!bgmEnabled}
              onChange={event => setBgmVolume(event.target.value)}
            />
          </label>
          <span className="batch-video-audio-hint">{bgmUrl ? '自定义音频按成片时长铺满' : '未上传时使用默认鼓点'}</span>
          {bgmUrl && (
            <button type="button" className="batch-video-button ghost" onClick={clearBgmUpload}>
              <Trash2 size={16} />
              移除
            </button>
          )}
          {bgmUrl && (
            <div className="batch-video-bgm-current">
              <strong>{bgmName || '自定义 BGM'}</strong>
              <audio src={assetUrl(bgmUrl)} controls preload="metadata" />
            </div>
          )}
        </div>
        <div className="batch-video-poster-panel">
          <div className="batch-video-poster-head">
            <div>
              <strong>收尾产品海报</strong>
              <span>拼接时追加到结尾，停留时长跟随产品名旁白</span>
            </div>
            <div className="batch-video-poster-actions">
              <button
                type="button"
                className="batch-video-button ghost"
                onClick={handleGenerateProductPoster}
                disabled={isLoading('product-poster') || (!product.detailSheetUrl && !product.imageUrls.length)}
              >
                <ImageIcon size={16} />
                {isLoading('product-poster') ? '生成中' : productPosterUrl ? '重新生成海报' : 'Image2 制作海报'}
              </button>
              {productPosterUrl && (
                <button type="button" className="batch-video-button ghost" onClick={clearProductPoster}>
                  <Trash2 size={16} />
                  移除
                </button>
              )}
            </div>
          </div>
          {productPosterUrl ? (
            <div className="batch-video-poster-body">
              <img src={assetUrl(productPosterUrl)} alt="收尾产品海报" />
              <textarea
                value={productPosterPrompt}
                rows={3}
                readOnly
                title="产品海报提示词"
              />
            </div>
          ) : (
            <div className="batch-video-empty compact">
              <ImageIcon size={24} />
              <span>生成一张产品广告海报，最终成片会在结尾自然定格。</span>
            </div>
          )}
          <VersionStrip
            title="收尾海报历史"
            versions={productPosterHistory}
            activeUrl={productPosterUrl}
            onSelect={selectProductPosterVersion}
          />
        </div>
        <div className="batch-video-final-toolbar">
          <span>剪辑表 {finalClips.filter(clip => clip.videoUrl).length} 段，可截取不同版本混剪</span>
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={rebuildFinalClipsFromScenes}
            disabled={!scenes.some(scene => scene.video_url)}
          >
            <RefreshCw size={16} />
            按最终版本生成剪辑表
          </button>
          <button
            type="button"
            className="batch-video-button primary"
            onClick={handleComposeFinalVideo}
            disabled={isLoading('compose-final-video') || !canComposeFinalVideo}
          >
            <Scissors size={16} />
            {isLoading('compose-final-video') ? '合成中' : '拼接并加字幕'}
          </button>
        </div>
        {finalClips.length > 0 ? (
          <div className="batch-video-clip-list">
            {finalClips.map((clip, index) => {
              const currentScene = scenes.find(scene => scene.id === clip.sceneId) || scenes[0]
              const videoOptions = videoVersionOptionsForScene(currentScene)
              return (
                <div className="batch-video-clip-row" key={clip.id}>
                  <div className="batch-video-clip-head">
                    <strong>片段 {index + 1}</strong>
                    <div>
                      <button type="button" title="上移" onClick={() => moveFinalClip(clip.id, -1)} disabled={index === 0}>
                        <ArrowUp size={14} />
                      </button>
                      <button type="button" title="下移" onClick={() => moveFinalClip(clip.id, 1)} disabled={index === finalClips.length - 1}>
                        <ArrowDown size={14} />
                      </button>
                      <button type="button" title="删除片段" onClick={() => removeFinalClip(clip.id)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="batch-video-clip-body">
                    <div className="batch-video-clip-preview">
                      {clip.videoUrl ? (
                        <video src={assetUrl(clip.videoUrl)} controls preload="metadata" />
                      ) : (
                        <span>未选择视频</span>
                      )}
                    </div>
                    <div className="batch-video-clip-fields">
                      <label className="batch-video-field">
                        <span>来源分镜</span>
                        <select value={clip.sceneId} onChange={event => updateFinalClipScene(clip.id, event.target.value)}>
                          {scenes.map((scene, sceneIndex) => (
                            <option key={scene.id} value={scene.id}>{scene.title || `分镜 ${sceneIndex + 1}`}</option>
                          ))}
                        </select>
                      </label>
                      <label className="batch-video-field">
                        <span>视频版本</span>
                        <select
                          value={clip.videoUrl}
                          onChange={event => {
                            const selected = videoOptions.find(item => item.url === event.target.value)
                            updateFinalClip(clip.id, {
                              videoUrl: event.target.value,
                              sourceLabel: selected?.label || selected?.source || '',
                            })
                          }}
                        >
                          {videoOptions.length ? videoOptions.map((item, optionIndex) => (
                            <option key={`${item.url}-${optionIndex}`} value={item.url}>
                              {item.url === currentScene?.video_url ? '最终版' : item.label || `历史版本 ${optionIndex + 1}`}
                            </option>
                          )) : (
                            <option value="">暂无视频版本</option>
                          )}
                        </select>
                      </label>
                      <div className="batch-video-clip-time-grid">
                        <label className="batch-video-field">
                          <span>开始秒</span>
                          <input
                            type="number"
                            min="0"
                            step="0.1"
                            value={clip.startTime}
                            onChange={event => updateFinalClip(clip.id, { startTime: event.target.value })}
                          />
                        </label>
                        <label className="batch-video-field">
                          <span>结束秒</span>
                          <input
                            type="number"
                            min="0"
                            step="0.1"
                            value={clip.endTime}
                            placeholder="到结尾"
                            onChange={event => updateFinalClip(clip.id, { endTime: event.target.value })}
                          />
                        </label>
                      </div>
                      <label className="batch-video-field">
                        <span>旁白/字幕</span>
                        <textarea
                          value={clip.voiceoverText}
                          rows={2}
                          onChange={event => updateFinalClip(clip.id, {
                            voiceoverText: event.target.value,
                            subtitle: event.target.value,
                          })}
                        />
                      </label>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="batch-video-empty compact">
            <Scissors size={24} />
            <span>生成视频后，可把最终版或历史版本加入剪辑表，再截取片段混剪。</span>
          </div>
        )}
        {finalVideo?.video_url && (
          <div className="batch-video-final-result">
            <video src={assetUrl(finalVideo.video_url)} controls />
            <div className="batch-video-final-meta">
              {finalVideo.poster_appended
                ? `已追加收尾海报，停留约 ${Number(finalVideo.poster_duration || 0).toFixed(1)} 秒`
                : '这条成片未追加收尾海报'}
            </div>
            <a className="batch-video-button ghost" href={assetUrl(finalVideo.video_url)} download>
              下载完整视频
            </a>
          </div>
        )}
      </section>

      <section className="batch-video-panel task-panel">
        <div className="batch-video-panel-title">
          <ListChecks size={18} />
          <h2>批量任务</h2>
        </div>
        <div className="batch-video-task-toolbar">
          <button
            type="button"
            className="batch-video-button primary"
            onClick={handleSubmitBatch}
            disabled={isLoading('submit')}
          >
            <ListChecks size={16} />
            {isLoading('submit') ? '整理中' : '整理批量任务'}
          </button>
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={() => {
              scenes.forEach(scene => {
                if (scene.status !== 'video_generating' && scene.status !== 'processing') {
                  void handleGenerateVideo(scene)
                }
              })
            }}
            disabled={!scenes.length}
          >
            <Play size={16} />
            批量生成视频
          </button>
        </div>
        {batchResult?.tasks?.length ? (
          <div className="batch-video-task-list">
            {batchResult.tasks.map(task => (
              <div className="batch-video-task-row" key={task.id}>
                <span>{task.title || task.scene_id}</span>
                <code>{task.status}</code>
              </div>
            ))}
          </div>
        ) : (
          <div className="batch-video-empty small">
            <ListChecks size={26} />
            <span>暂无批量任务</span>
          </div>
        )}
      </section>
    </div>
  )
}
