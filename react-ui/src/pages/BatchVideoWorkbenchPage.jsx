import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Boxes,
  Clapperboard,
  Copy,
  FileVideo,
  FolderOpen,
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
  { id: 'image2-main', name: 'Image2 主模型', provider: 'openai_image', available: true },
  { id: 'image2-toapis', name: 'Image2 ToAPIs', provider: 'toapis', available: true },
  { id: 'image2-vip', name: 'Image2 VIP（ToAPIs）', provider: 'toapis', available: true },
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
const CLIP_PLAYBACK_RATE_OPTIONS = [
  { value: 0.5, label: '0.5x 慢放' },
  { value: 0.75, label: '0.75x' },
  { value: 1, label: '1x 正常' },
  { value: 1.25, label: '1.25x' },
  { value: 1.5, label: '1.5x' },
  { value: 2, label: '2x 快放' },
]
const DEFAULT_AUTO_CLIP_DURATION = 6.4
const DEFAULT_AUTO_CLIP_PLAYBACK_RATE = 1.25
const AUTO_BATCH_CONCURRENCY = 3
const AUTO_WORK_MIN_SCENES = 3
const AUTO_WORK_MAX_SCENES = 4
const DEFAULT_LOCAL_RECOVERY_FOLDER = 'C:\\Users\\Administrator\\Desktop\\素材\\ai素材'
const DEFAULT_STORYBOARD_SCENE_COUNT = 6
const VEO_STORYBOARD_SCENE_COUNT = 4
const VEO_STORYBOARD_DURATION = 8
const DEFAULT_VOICEOVER_VOLUME = 1.35
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
    batchSceneArchive: [],
    batchResult: null,
    autoWorks: [],
    autoWorkArchive: [],
    finalVideo: null,
    finalClips: [],
    ttsVoiceType: '',
    ttsCustomVoiceType: '',
    ttsSpeedRatio: 1,
    voiceoverVolume: DEFAULT_VOICEOVER_VOLUME,
    rhythmMatchEnabled: true,
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
  batchSceneArchive,
  batchResult,
  autoWorks,
  autoWorkArchive,
  finalVideo,
  finalClips,
  ttsVoiceType,
  ttsCustomVoiceType,
  ttsSpeedRatio,
  voiceoverVolume,
  rhythmMatchEnabled,
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
    batchSceneArchive,
    batchResult,
    autoWorks,
    autoWorkArchive,
    finalVideo,
    finalClips,
    ttsVoiceType,
    ttsCustomVoiceType,
    ttsSpeedRatio,
    voiceoverVolume,
    rhythmMatchEnabled,
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

function normalizeClipPlaybackRate(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return 1
  return Number(Math.max(0.25, Math.min(4, number)).toFixed(2))
}

function formatClipTime(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number < 0) return '0.0s'
  const minutes = Math.floor(number / 60)
  const seconds = number - minutes * 60
  if (!minutes) return `${seconds.toFixed(1)}s`
  return `${minutes}m ${seconds.toFixed(1)}s`
}

function clipVideoElementId(clipId) {
  return `clip-video-${String(clipId || '').replace(/[^A-Za-z0-9_-]/g, '_')}`
}

function cacheBustedAssetUrl(url, token) {
  const resolvedUrl = assetUrl(url)
  if (!resolvedUrl || !token) return resolvedUrl
  return `${resolvedUrl}${resolvedUrl.includes('?') ? '&' : '?'}v=${encodeURIComponent(token)}`
}

function clipSliderMax(clip, previewState = {}) {
  const duration = Number(previewState.duration || 0)
  const startTime = Number(clip?.startTime || 0)
  const endTime = Number(clip?.endTime || 0)
  const safeDuration = Number.isFinite(duration) ? duration : 0
  const safeStartTime = Number.isFinite(startTime) ? startTime : 0
  const safeEndTime = Number.isFinite(endTime) ? endTime : 0
  return Number(Math.max(safeDuration, safeStartTime, safeEndTime, 8).toFixed(1))
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
    sceneId: scene.sourceSceneId || scene.id || `scene_${index}`,
    title: scene.title || `分镜 ${index + 1}`,
    videoUrl: selectedVersion.url,
    sourceLabel: selectedVersion.label || selectedVersion.source || scene.candidateSourceLabel || '',
    startTime: 0,
    endTime: DEFAULT_AUTO_CLIP_DURATION,
    playbackRate: DEFAULT_AUTO_CLIP_PLAYBACK_RATE,
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
  const playbackRate = normalizeClipPlaybackRate(clip.playbackRate ?? clip.playback_rate)
  return {
    id: String(clip.id || `clip_${Date.now()}_${index}`),
    sceneId: sceneId || scene.id || '',
    title: String(clip.title || scene.title || `片段 ${index + 1}`),
    videoUrl,
    sourceLabel: String(clip.sourceLabel || clip.source_label || ''),
    startTime,
    endTime: endTime !== '' && startTime !== '' && endTime <= startTime ? '' : endTime,
    playbackRate,
    voiceoverText,
    subtitle: hasVoiceoverValue ? voiceoverText : String(clip.subtitle || voiceoverText),
  }
}

function buildDefaultFinalClips(scenes) {
  return (Array.isArray(scenes) ? scenes : [])
    .map((scene, index) => createFinalClipFromScene(scene, index))
    .filter(Boolean)
}

function mergeSceneRecords(existingScene, nextScene, index = 0) {
  const existing = existingScene || {}
  const next = nextScene || {}
  const storyboardUrl = next.storyboard_image_url || next.storyboardImageUrl || existing.storyboard_image_url || existing.storyboardImageUrl || ''
  const videoUrl = next.video_url || next.videoUrl || existing.video_url || existing.videoUrl || ''
  return normalizeScene({
    ...existing,
    ...next,
    storyboard_image_url: storyboardUrl,
    video_url: videoUrl,
    status: videoUrl ? 'completed' : (next.status || existing.status || 'draft'),
    storyboardImageHistory: mergeVersionHistory(
      existing.storyboardImageHistory || existing.storyboard_image_history || next.storyboardImageHistory || next.storyboard_image_history,
      makeVersionItem(storyboardUrl),
    ),
    videoHistory: mergeVersionHistory(
      existing.videoHistory || existing.video_history || next.videoHistory || next.video_history,
      makeVersionItem(videoUrl),
    ),
  }, index)
}

function productDetailSceneScore(scene) {
  if (!scene) return 0
  return (
    (scene.video_url || scene.videoUrl ? 8 : 0)
    + (scene.storyboard_image_url || scene.storyboardImageUrl ? 4 : 0)
    + (scene.taskId ? 2 : 0)
    + (scene.status === 'completed' ? 1 : 0)
  )
}

function collectRestorableScenes(...sceneSources) {
  const sceneMap = new Map()
  let detailScene = null
  sceneSources.forEach(source => {
    ;(Array.isArray(source) ? source : []).forEach((scene, index) => {
      if (!scene) return
      const sceneId = scene.id || `scene_${sceneMap.size}_${index}`
      const isProductDetail = scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail'
      if (isProductDetail) {
        const mergedDetail = mergeSceneRecords(detailScene, { ...scene, id: detailScene?.id || sceneId }, sceneMap.size)
        detailScene = productDetailSceneScore(mergedDetail) >= productDetailSceneScore(detailScene)
          ? mergedDetail
          : detailScene
        return
      }
      const existing = sceneMap.get(sceneId)
      sceneMap.set(sceneId, mergeSceneRecords(existing, { ...scene, id: sceneId }, sceneMap.size))
    })
  })
  const restoredScenes = Array.from(sceneMap.values())
  if (detailScene) restoredScenes.push(normalizeScene(detailScene, restoredScenes.length))
  return restoredScenes
}

function collectScenesFromAutoWorks(sourceAutoWorks) {
  return (Array.isArray(sourceAutoWorks) ? sourceAutoWorks : []).flatMap(work => (
    Array.isArray(work?.scenes) ? work.scenes : []
  ))
}

function mergeAutoWorkRecords(existingWork, nextWork, index = 0) {
  const existing = existingWork || {}
  const next = nextWork || {}
  return normalizeAutoWork({
    ...existing,
    ...next,
    scenes: collectRestorableScenes(existing.scenes || [], next.scenes || []),
    sceneIds: Array.isArray(next.sceneIds) && next.sceneIds.length ? next.sceneIds : existing.sceneIds,
    finalClips: Array.isArray(next.finalClips) && next.finalClips.length ? next.finalClips : existing.finalClips,
    finalVideo: next.finalVideo || existing.finalVideo || null,
    updatedAt: Math.max(Number(existing.updatedAt || 0), Number(next.updatedAt || 0), Date.now()),
  }, index)
}

function collectRestorableAutoWorks(...workSources) {
  const workMap = new Map()
  workSources.forEach(source => {
    ;(Array.isArray(source) ? source : []).forEach((work, index) => {
      if (!work) return
      const workId = String(work.id || `auto_work_${workMap.size}_${index}`)
      const existing = workMap.get(workId)
      workMap.set(workId, mergeAutoWorkRecords(existing, { ...work, id: workId }, workMap.size))
    })
  })
  return Array.from(workMap.values())
}

function sceneArchiveSignature(sourceScenes) {
  return (Array.isArray(sourceScenes) ? sourceScenes : [])
    .map(scene => [
      scene?.id || '',
      scene?.referenceMode || scene?.reference_mode || '',
      scene?.storyboard_image_url || scene?.storyboardImageUrl || '',
      scene?.video_url || scene?.videoUrl || '',
      scene?.taskId || '',
      scene?.status || '',
    ].join(':'))
    .join('|')
}

function autoWorkArchiveSignature(sourceWorks) {
  return (Array.isArray(sourceWorks) ? sourceWorks : [])
    .map(work => [
      work?.id || '',
      work?.status || '',
      work?.finalVideo?.video_url || '',
      sceneArchiveSignature(work?.scenes || []),
    ].join(':'))
    .join('|')
}

function buildReviewableSceneCandidates(sourceScenes, sourceAutoWorks = []) {
  const candidates = []
  const seen = new Set()
  const pushSceneVersions = (scene, sceneIndex, sourceLabel = '') => {
    if (!scene) return
    videoVersionOptionsForScene(scene).forEach((version, versionIndex) => {
      if (!version?.url) return
      const sceneId = scene.id || `scene_${sceneIndex}`
      const key = `${sceneId}::${version.url}`
      if (seen.has(key)) return
      seen.add(key)
      candidates.push({
        ...scene,
        id: `${sceneId}__candidate_${versionIndex}_${candidates.length}`,
        sourceSceneId: sceneId,
        candidateVideoUrl: version.url,
        candidateVersion: version,
        candidateSourceLabel: version.label || version.source || sourceLabel,
        candidateIndex: candidates.length,
        video_url: version.url,
      })
    })
  }

  ;(Array.isArray(sourceScenes) ? sourceScenes : []).forEach((scene, index) => {
    pushSceneVersions(scene, index, '当前分镜')
  })
  ;(Array.isArray(sourceAutoWorks) ? sourceAutoWorks : []).forEach((work, workIndex) => {
    const workScenes = Array.isArray(work?.scenes) ? work.scenes : []
    workScenes.forEach((scene, sceneIndex) => {
      pushSceneVersions(scene, sceneIndex, work?.title || `批量成品 ${workIndex + 1}`)
    })
  })
  return candidates
}

function buildSegmentsFromClips(clips, sourceScenes) {
  const sceneList = Array.isArray(sourceScenes) ? sourceScenes : []
  return (Array.isArray(clips) ? clips : [])
    .map((clip, index) => {
      const scene = sceneList.find(item => item.id === clip.sceneId) || sceneList[index] || {}
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
        playback_rate: normalizeClipPlaybackRate(clip.playbackRate),
        subtitle: voiceoverText,
        voiceover_text: voiceoverText,
      }
    })
    .filter(segment => segment.video_url)
}

function splitAutoWorkSceneGroups(sourceScenes) {
  const pending = (Array.isArray(sourceScenes) ? sourceScenes : [])
    .filter(scene => scene && scene.referenceMode !== 'product_detail' && scene.reference_mode !== 'product_detail')
  return splitAutoWorkGroups(pending)
}

function splitAutoWorkClipGroups(sourceClips) {
  const pending = (Array.isArray(sourceClips) ? sourceClips : [])
    .filter(clip => clip && clip.videoUrl)
  return splitAutoWorkGroups(pending)
}

function splitAutoWorkGroups(pending) {
  const groups = []
  let index = 0
  while (index < pending.length) {
    const remaining = pending.length - index
    if (remaining < AUTO_WORK_MIN_SCENES) {
      break
    }
    let size = AUTO_WORK_MAX_SCENES
    if (remaining <= AUTO_WORK_MAX_SCENES) {
      size = remaining
    } else if (remaining === 5) {
      size = AUTO_WORK_MAX_SCENES
    } else if (remaining % AUTO_WORK_MAX_SCENES === 1 || remaining % AUTO_WORK_MAX_SCENES === 2) {
      size = AUTO_WORK_MIN_SCENES
    }
    groups.push(pending.slice(index, index + size))
    index += size
  }
  return groups.filter(group => group.length)
}

function normalizeAutoWork(work, index = 0) {
  if (!work || typeof work !== 'object') return null
  const scenes = Array.isArray(work.scenes)
    ? work.scenes.map((scene, sceneIndex) => normalizeScene(scene || {}, sceneIndex))
    : []
  const sceneIds = Array.isArray(work.sceneIds) && work.sceneIds.length
    ? work.sceneIds.map(id => String(id || '')).filter(Boolean)
    : scenes.map(scene => scene.id).filter(Boolean)
  const finalClips = Array.isArray(work.finalClips)
    ? work.finalClips.map((clip, clipIndex) => normalizeFinalClip(clip || {}, clipIndex, scenes)).filter(Boolean)
    : []
  return {
    id: String(work.id || `auto_work_${Date.now()}_${index}`),
    title: String(work.title || `成品 ${index + 1}`),
    strategy: String(work.strategy || ''),
    status: String(work.status || 'queued'),
    error: String(work.error || ''),
    scenes,
    sceneIds,
    finalClips,
    finalVideo: work.finalVideo && typeof work.finalVideo === 'object' ? work.finalVideo : null,
    createdAt: Number(work.createdAt || Date.now()),
    updatedAt: Number(work.updatedAt || work.createdAt || Date.now()),
  }
}

function autoWorkStatusText(status) {
  const key = String(status || '')
  if (key === 'completed') return '已成片'
  if (key === 'composing') return '合成中'
  if (key === 'generating') return '素材生成中'
  if (key === 'submitted') return '等待视频完成'
  if (key === 'failed') return '失败'
  if (key === 'ready') return '可合成'
  return '排队中'
}

async function runWithConcurrency(items, limit, runner) {
  const queue = Array.isArray(items) ? [...items] : []
  const workerCount = Math.max(1, Math.min(Number(limit) || 1, queue.length || 1))
  const workers = Array.from({ length: workerCount }, async () => {
    while (queue.length) {
      const item = queue.shift()
      await runner(item)
    }
  })
  await Promise.all(workers)
}

function modelLabel(model) {
  const suffix = model.available === false ? '（待接入）' : ''
  const price = videoModelPriceText(model)
  return `${model.name || model.id}${suffix}${price ? ` · ${price}` : ''}`
}

function providerForModel(modelId, models, fallback) {
  return models.find(item => item.id === modelId)?.provider || fallback
}

function normalizeImageModelId(modelId) {
  return modelId === 'image2' ? 'image2-main' : (modelId || 'image2-main')
}

function referenceLimitForImageModel(modelId, models) {
  const provider = providerForModel(modelId, models, 'openai_image')
  if (provider === 'toapis') return IMAGE2_REFERENCE_LIMIT
  if (provider === 'openai_image') return 4
  return 8
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

function videoModelRequestedResolution(model, fallbackResolution) {
  const options = videoModelResolutionOptions(model)
  const requested = String(fallbackResolution || '').trim() || String(model?.default_resolution || '').trim()
  if (requested && options.includes(requested)) return requested
  if (model?.default_resolution && options.includes(model.default_resolution)) return model.default_resolution
  return options[0] || '720p'
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
  const normalizedAutoWorks = Array.isArray(rawDraft.autoWorks)
    ? rawDraft.autoWorks.map((work, index) => normalizeAutoWork(work || {}, index)).filter(Boolean)
    : []
  const normalizedAutoWorkArchive = collectRestorableAutoWorks(
    Array.isArray(rawDraft.autoWorkArchive) ? rawDraft.autoWorkArchive : [],
    normalizedAutoWorks,
  )
  const normalizedBatchSceneArchive = collectRestorableScenes(
    Array.isArray(rawDraft.batchSceneArchive) ? rawDraft.batchSceneArchive : [],
    normalizedScenes,
    collectScenesFromAutoWorks(normalizedAutoWorkArchive),
  )
  const rawTtsVoiceType = typeof rawDraft.ttsVoiceType === 'string' ? rawDraft.ttsVoiceType : fallback.ttsVoiceType
  const ttsVoiceType = TTS_VOICE_OPTIONS.some(item => item.id === rawTtsVoiceType) ? rawTtsVoiceType : 'custom'
  const ttsSpeedRatio = Number(rawDraft.ttsSpeedRatio)
  const voiceoverVolume = Number(rawDraft.voiceoverVolume)
  const bgmUrl = typeof rawDraft.bgmUrl === 'string' ? rawDraft.bgmUrl : ''
  const bgmVolume = Number(rawDraft.bgmVolume)
  const normalizedBgmVolume = Number.isFinite(bgmVolume) ? Math.max(0, Math.min(1, bgmVolume)) : fallback.bgmVolume
  return {
    ...fallback,
    updatedAt: Number(rawDraft.updatedAt || 0),
    product: normalizeProductDraft(rawDraft.product),
    languageModel: typeof rawDraft.languageModel === 'string' ? rawDraft.languageModel : fallback.languageModel,
    imageModel: typeof rawDraft.imageModel === 'string' ? normalizeImageModelId(rawDraft.imageModel) : fallback.imageModel,
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
    batchSceneArchive: normalizedBatchSceneArchive,
    batchResult: rawDraft.batchResult && typeof rawDraft.batchResult === 'object' ? rawDraft.batchResult : null,
    autoWorks: normalizedAutoWorks,
    autoWorkArchive: normalizedAutoWorkArchive,
    finalVideo: rawDraft.finalVideo && typeof rawDraft.finalVideo === 'object' ? rawDraft.finalVideo : null,
    finalClips: normalizedFinalClips,
    ttsVoiceType,
    ttsCustomVoiceType: typeof rawDraft.ttsCustomVoiceType === 'string'
      ? rawDraft.ttsCustomVoiceType
      : (ttsVoiceType === 'custom' ? rawTtsVoiceType : ''),
    ttsSpeedRatio: Number.isFinite(ttsSpeedRatio) ? Math.max(0.6, Math.min(1.4, ttsSpeedRatio)) : fallback.ttsSpeedRatio,
    voiceoverVolume: Number.isFinite(voiceoverVolume) ? Math.max(0.2, Math.min(2, voiceoverVolume)) : fallback.voiceoverVolume,
    rhythmMatchEnabled: typeof rawDraft.rhythmMatchEnabled === 'boolean' ? rawDraft.rhythmMatchEnabled : fallback.rhythmMatchEnabled,
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
  const [batchSceneArchive, setBatchSceneArchive] = useState(() => initialDraft.batchSceneArchive || [])
  const [batchResult, setBatchResult] = useState(() => initialDraft.batchResult)
  const [autoWorks, setAutoWorks] = useState(() => initialDraft.autoWorks || [])
  const [autoWorkArchive, setAutoWorkArchive] = useState(() => initialDraft.autoWorkArchive || initialDraft.autoWorks || [])
  const [finalVideo, setFinalVideo] = useState(() => initialDraft.finalVideo || null)
  const [finalVideoRefreshToken, setFinalVideoRefreshToken] = useState(() => (
    initialDraft.finalVideo?.generated_at
    || initialDraft.finalVideo?.compose_generated_at
    || initialDraft.finalVideo?.video_url
    || ''
  ))
  const [finalClips, setFinalClips] = useState(() => initialDraft.finalClips || [])
  const [autoClipBuildPending, setAutoClipBuildPending] = useState(false)
  const [clipPreviewState, setClipPreviewState] = useState({})
  const [ttsVoiceType, setTtsVoiceType] = useState(() => initialDraft.ttsVoiceType || '')
  const [ttsCustomVoiceType, setTtsCustomVoiceType] = useState(() => initialDraft.ttsCustomVoiceType || '')
  const [ttsSpeedRatio, setTtsSpeedRatio] = useState(() => initialDraft.ttsSpeedRatio || 1)
  const [voiceoverVolume, setVoiceoverVolume] = useState(() => initialDraft.voiceoverVolume ?? DEFAULT_VOICEOVER_VOLUME)
  const [rhythmMatchEnabled, setRhythmMatchEnabled] = useState(() => initialDraft.rhythmMatchEnabled !== false)
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
  const [localRecoveryFolder, setLocalRecoveryFolder] = useState(DEFAULT_LOCAL_RECOVERY_FOLDER)
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
  const autoWorkComposingRef = useRef(new Set())
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
    setBatchSceneArchive(nextDraft.batchSceneArchive)
    setBatchResult(nextDraft.batchResult)
    setAutoWorks(nextDraft.autoWorks)
    setAutoWorkArchive(nextDraft.autoWorkArchive)
    setFinalVideo(nextDraft.finalVideo)
    setFinalClips(nextDraft.finalClips)
    setTtsVoiceType(nextDraft.ttsVoiceType)
    setTtsCustomVoiceType(nextDraft.ttsCustomVoiceType)
    setTtsSpeedRatio(nextDraft.ttsSpeedRatio)
    setVoiceoverVolume(nextDraft.voiceoverVolume)
    setRhythmMatchEnabled(nextDraft.rhythmMatchEnabled)
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
    setBatchSceneArchive(prev => prev.map(scene => (scene.id === sceneId ? mergeSceneRecords(scene, { ...scene, ...patch }) : scene)))
    setAutoWorkArchive(prev => prev.map(work => ({
      ...work,
      scenes: (work.scenes || []).map(scene => (scene.id === sceneId ? mergeSceneRecords(scene, { ...scene, ...patch }) : scene)),
    })))
    setAutoWorks(prev => prev.map(work => ({
      ...work,
      scenes: (work.scenes || []).map(scene => (scene.id === sceneId ? mergeSceneRecords(scene, { ...scene, ...patch }) : scene)),
    })))
  }, [])

  const updateSceneWith = useCallback((sceneId, updater) => {
    setScenes(prev => prev.map(scene => (
      scene.id === sceneId ? { ...scene, ...updater(scene) } : scene
    )))
    setBatchSceneArchive(prev => prev.map(scene => (
      scene.id === sceneId ? mergeSceneRecords(scene, { ...scene, ...updater(scene) }) : scene
    )))
    setAutoWorkArchive(prev => prev.map(work => ({
      ...work,
      scenes: (work.scenes || []).map(scene => (
        scene.id === sceneId ? mergeSceneRecords(scene, { ...scene, ...updater(scene) }) : scene
      )),
    })))
    setAutoWorks(prev => prev.map(work => ({
      ...work,
      scenes: (work.scenes || []).map(scene => (
        scene.id === sceneId ? mergeSceneRecords(scene, { ...scene, ...updater(scene) }) : scene
      )),
    })))
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

  const appendAllReviewableScenesToFinalClips = useCallback(() => {
    const candidates = buildReviewableSceneCandidates(scenes, autoWorks)
    const clips = candidates
      .map((scene, index) => createFinalClipFromScene(scene, index, scene.candidateVersion))
      .filter(Boolean)
    if (!clips.length) {
      setNotice({ type: 'warning', text: '当前还没有可加入选片审片的视频，先生成分镜视频。' })
      return
    }
    const existingKeys = new Set(
      finalClips
        .filter(clip => clip.videoUrl)
        .map(clip => `${clip.sceneId || ''}::${clip.videoUrl}`),
    )
    const nextClips = clips.filter(clip => {
      const key = `${clip.sceneId || ''}::${clip.videoUrl}`
      if (existingKeys.has(key)) return false
      existingKeys.add(key)
      return true
    })
    if (!nextClips.length) {
      setNotice({ type: 'warning', text: '所有已生成分镜都已经在选片审片里了。' })
      return
    }
    setFinalClips(prev => [...prev, ...nextClips])
    setNotice({
      type: 'success',
      text: `已把 ${nextClips.length} 个分镜加入选片审片，可继续拖动开始/结束截取可用画面。`,
    })
  }, [autoWorks, finalClips, scenes])

  const appendFinalClipFromScene = useCallback((scene, version = null) => {
    const sourceSceneId = scene.sourceSceneId || scene.id
    const index = scenes.findIndex(item => item.id === sourceSceneId)
    const clip = createFinalClipFromScene(scene, Math.max(0, index), version || scene.candidateVersion)
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

  const duplicateFinalClip = useCallback((clipId) => {
    setFinalClips(prev => {
      const index = prev.findIndex(clip => clip.id === clipId)
      if (index < 0) return prev
      const source = prev[index]
      const nextClip = normalizeFinalClip({
        ...source,
        id: `clip_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        startTime: source.endTime !== '' ? source.endTime : source.startTime,
        endTime: '',
      }, index + 1, scenes)
      if (!nextClip) return prev
      const next = [...prev]
      next.splice(index + 1, 0, nextClip)
      return next
    })
    setNotice({ type: 'success', text: '已复制为新的剪辑片段，可以在同一个视频里截取另一段不连续内容。' })
  }, [scenes])

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

  const updateClipPreviewState = useCallback((clipId, patch) => {
    setClipPreviewState(prev => ({
      ...prev,
      [clipId]: {
        ...(prev[clipId] || {}),
        ...patch,
      },
    }))
  }, [])

  const seekClipPreview = useCallback((clipId, seconds) => {
    const nextTime = normalizeClipTime(seconds)
    if (nextTime === '') return
    const video = typeof document === 'undefined' ? null : document.getElementById(clipVideoElementId(clipId))
    if (video) video.currentTime = nextTime
    updateClipPreviewState(clipId, { currentTime: nextTime })
  }, [updateClipPreviewState])

  const setClipBoundaryFromPreview = useCallback((clipId, boundary) => {
    const previewState = clipPreviewState[clipId] || {}
    const currentTime = normalizeClipTime(previewState.currentTime)
    if (currentTime === '') return
    updateFinalClip(clipId, boundary === 'start'
      ? { startTime: currentTime }
      : { endTime: currentTime })
  }, [clipPreviewState, updateFinalClip])

  const previewFinalClip = useCallback((clip) => {
    const video = typeof document === 'undefined' ? null : document.getElementById(clipVideoElementId(clip.id))
    if (!video) return
    const startTime = normalizeClipTime(clip.startTime)
    const endTime = normalizeClipTime(clip.endTime)
    video.playbackRate = normalizeClipPlaybackRate(clip.playbackRate)
    if (video._batchClipStopAtEnd) {
      video.removeEventListener('timeupdate', video._batchClipStopAtEnd)
      video._batchClipStopAtEnd = null
    }
    video.currentTime = startTime === '' ? 0 : startTime
    if (endTime !== '') {
      const stopAtEnd = () => {
        if (video.currentTime >= endTime) {
          video.pause()
          video.removeEventListener('timeupdate', stopAtEnd)
          video._batchClipStopAtEnd = null
        }
      }
      video._batchClipStopAtEnd = stopAtEnd
      video.addEventListener('timeupdate', stopAtEnd)
      video.addEventListener('ended', () => {
        video.pause()
        video.removeEventListener('timeupdate', stopAtEnd)
        video._batchClipStopAtEnd = null
      }, { once: true })
    }
    const playResult = video.play?.()
    if (playResult?.catch) playResult.catch(() => {})
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
    const nextWorks = collectRestorableAutoWorks(autoWorkArchive, autoWorks)
    if (autoWorkArchiveSignature(nextWorks) !== autoWorkArchiveSignature(autoWorkArchive)) {
      setAutoWorkArchive(nextWorks)
    }
    const nextScenes = collectRestorableScenes(
      batchSceneArchive,
      scenes,
      collectScenesFromAutoWorks(nextWorks),
    )
    if (sceneArchiveSignature(nextScenes) !== sceneArchiveSignature(batchSceneArchive)) {
      setBatchSceneArchive(nextScenes)
    }
  }, [autoWorkArchive, autoWorks, batchSceneArchive, scenes])

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
    if (!autoWorks.length || !productPosterUrl) return
    autoWorks.forEach(work => {
      if (!work || work.status === 'completed' || work.status === 'failed') return
      const workScenes = getCurrentScenesForWork(work)
      const detailScene = workScenes.find(scene => scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail')
      const readyAdScenes = workScenes.filter(scene => (
        scene.video_url
        && scene.referenceMode !== 'product_detail'
        && scene.reference_mode !== 'product_detail'
      ))
      if (readyAdScenes.length < AUTO_WORK_MIN_SCENES) return
      if (detailScene && !detailScene.video_url && detailScene.status !== 'failed') return
      const readyScenes = workScenes.filter(scene => (
        scene.video_url
        && (scene.referenceMode !== 'product_detail' || readyAdScenes.length >= AUTO_WORK_MIN_SCENES)
      ))
      void composeAutoWork(work, readyScenes)
    })
  }, [autoWorks, productPosterUrl, scenes])

  useEffect(() => {
    if (!autoWorks.length) return
    setBatchResult(prev => {
      if (!prev?.tasks?.length) return prev
      const tasks = autoWorks.map(work => ({
        id: work.id,
        title: work.title,
        status: work.finalVideo?.video_url ? 'completed' : work.status,
        video_url: work.finalVideo?.video_url || '',
      }))
      const currentSignature = prev.tasks
        .map(task => `${task.id}:${task.status}:${task.video_url || ''}`)
        .join('|')
      const nextSignature = tasks
        .map(task => `${task.id}:${task.status}:${task.video_url || ''}`)
        .join('|')
      return currentSignature === nextSignature ? prev : { ...prev, tasks }
    })
  }, [autoWorks])

  useEffect(() => {
    if (!autoClipBuildPending) return
    if (autoWorks.length) {
      setAutoClipBuildPending(false)
      return
    }
    const clips = buildDefaultFinalClips(scenes)
    const hasPendingScenes = scenes.some(scene => !scene.video_url && (scene.taskId || isProcessingTaskStatus(scene.status)))
    if (!clips.length) {
      if (!hasPendingScenes) {
        setAutoClipBuildPending(false)
      }
      return
    }
    const nextSignature = clips.map(clip => `${clip.sceneId}:${clip.videoUrl}`).join('|')
    const currentSignature = finalClips.map(clip => `${clip.sceneId}:${clip.videoUrl}`).join('|')
    if (nextSignature !== currentSignature) {
      setFinalClips(clips)
    }
    if (!hasPendingScenes) {
      setAutoClipBuildPending(false)
      setNotice({
        type: 'success',
        text: `批量视频已回填到剪辑表，默认截取 0-${DEFAULT_AUTO_CLIP_DURATION}s，画面 ${DEFAULT_AUTO_CLIP_PLAYBACK_RATE}x。`,
      })
    }
  }, [autoClipBuildPending, autoWorks.length, finalClips, scenes])

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
      batchSceneArchive,
      batchResult,
      autoWorks,
      autoWorkArchive,
      finalVideo,
      finalClips,
      ttsVoiceType,
      ttsCustomVoiceType,
      ttsSpeedRatio,
      voiceoverVolume,
      rhythmMatchEnabled,
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
    autoWorkArchive,
    autoWorks,
    batchSceneArchive,
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
    rhythmMatchEnabled,
    scenes,
    sellingPoints,
    storyboardCreativeBrief,
    storyboardReferences,
    transcript,
    ttsCustomVoiceType,
    ttsSpeedRatio,
    ttsVoiceType,
    voiceoverVolume,
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
      const selectedImageModel = normalizeImageModelId(imageModel)
      const imageReferenceLimit = referenceLimitForImageModel(selectedImageModel, imageModels)
      const plan = await api.post('/api/batch-video/product-reconstruction', {
        product: productPayload,
        image_model: selectedImageModel,
        aspect_ratio: '16:9',
      })
      if (plan.status !== 'ready') {
        setNotice({ type: 'warning', text: plan.message || '产品详情表提示词未生成。' })
        return
      }
      const result = await api.post('/api/game/generate_image', {
        project_id: '',
        prompt: plan.prompt,
        provider: plan.provider || providerForModel(selectedImageModel, imageModels, 'openai_image'),
        model: plan.image_model || selectedImageModel,
        aspect_ratio: '16:9',
        asset_type: 'product_detail_sheet',
        reference_urls: (plan.reference_urls || product.imageUrls.map(item => item.url)).slice(0, imageReferenceLimit),
        prompt_optimize_mode: 'standard',
        image_quality: '2K',
        output_format: 'png',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回产品详情表图片地址')
      const selectedModelLabel = imageModels.find(item => item.id === selectedImageModel)?.name || selectedImageModel
      const version = makeVersionItem(imageUrl, {
        prompt: plan.prompt || '',
        source: plan.image_model || selectedImageModel,
        label: `${selectedModelLabel} ${new Date().toLocaleTimeString()}`,
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
      const selectedImageModel = normalizeImageModelId(imageModel)
      const imageReferenceLimit = referenceLimitForImageModel(selectedImageModel, imageModels)
      const plan = await api.post('/api/batch-video/product-poster', {
        product: productPayload,
        selling_points: sellingPoints,
        image_model: selectedImageModel,
        aspect_ratio: aspectRatio,
      })
      if (plan.status !== 'ready') {
        setNotice({ type: 'warning', text: plan.message || '产品收尾海报提示词未生成。' })
        return
      }
      const result = await api.post('/api/game/generate_image', {
        project_id: '',
        prompt: plan.prompt,
        provider: plan.provider || providerForModel(selectedImageModel, imageModels, 'openai_image'),
        model: plan.image_model || selectedImageModel,
        aspect_ratio: plan.aspect_ratio || aspectRatio,
        asset_type: 'product_final_poster',
        reference_urls: (plan.reference_urls || productReferences).slice(0, imageReferenceLimit),
        prompt_optimize_mode: 'standard',
        image_quality: '2K',
        output_format: 'png',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回产品海报图片地址')
      const version = makeVersionItem(imageUrl, {
        prompt: plan.prompt || '',
        source: plan.image_model || selectedImageModel,
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
    const nextSceneList = mode === 'append' ? [...scenes, ...matrixScenes] : matrixScenes
    setScenes(nextSceneList)
    setBatchSceneArchive(prev => collectRestorableScenes(mode === 'append' ? prev : [], nextSceneList))
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
      const nextScenes = [...withoutOld, nextScene]
      setBatchSceneArchive(archive => collectRestorableScenes(archive, nextScenes))
      return nextScenes
    })
    setFinalVideo(null)
    setFinalClips([])
    setNotice({ type: 'success', text: '已在分镜最后追加产品细节收尾镜头：将直接用最终版产品还原图生成视频，不需要分镜图。' })
  }

  function buildAutoWorkDetailScene(workIndex = 0) {
    const detailScene = buildProductDetailEndingScene(
      product,
      isVeoModel(videoModel) ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio,
      requestedVideoDuration,
    )
    return {
      ...detailScene,
      id: `auto_detail_${Date.now()}_${workIndex}_${Math.random().toString(36).slice(2, 7)}`,
      title: `成品 ${workIndex + 1} 产品细节视频`,
      shot_notes: `${detailScene.shot_notes || ''} 自动成片产品细节，可失败不阻塞海报收尾。`,
    }
  }

  function buildAutoWorksFromScenes(sourceScenes, { includeDetail = true, preferredClips = [] } = {}) {
    const groups = splitAutoWorkSceneGroups(sourceScenes)
    return groups.map((group, workIndex) => {
      const workId = `auto_work_${Date.now()}_${workIndex}_${Math.random().toString(36).slice(2, 7)}`
      const detailScene = includeDetail && product.detailSheetUrl ? buildAutoWorkDetailScene(workIndex) : null
      const workScenes = [...group, detailScene].filter(Boolean).map(scene => ({
        ...scene,
        autoWorkId: workId,
      }))
      const sceneIds = workScenes.map(scene => scene.id)
      const workClips = preferredClips
        .filter(clip => sceneIds.includes(clip.sceneId))
        .map((clip, clipIndex) => normalizeFinalClip(clip, clipIndex, workScenes))
        .filter(Boolean)
      return normalizeAutoWork({
        id: workId,
        title: `成品 ${workIndex + 1}`,
        strategy: groupScenes.map(scene => scene.selling_point || scene.title).filter(Boolean).join(' / '),
        status: 'queued',
        scenes: workScenes,
        sceneIds,
        finalClips: workClips,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      }, workIndex)
    })
  }

  function getCurrentScenesForWork(work) {
    const sceneById = new Map(scenes.map(scene => [scene.id, scene]))
    const ids = Array.isArray(work.sceneIds) && work.sceneIds.length
      ? work.sceneIds
      : (work.scenes || []).map(scene => scene.id)
    return ids
      .map((sceneId, index) => sceneById.get(sceneId) || work.scenes?.[index])
      .filter(Boolean)
  }

  function buildClipsForAutoWork(work, workScenes) {
    const selectedSceneIds = new Set((work.sceneIds || []).filter(Boolean))
    const userSelectedClips = finalClips
      .filter(clip => clip.videoUrl && selectedSceneIds.has(clip.sceneId))
      .map((clip, index) => normalizeFinalClip(clip, index, workScenes))
      .filter(Boolean)
    if (userSelectedClips.length) return userSelectedClips
    if (Array.isArray(work.finalClips) && work.finalClips.some(clip => clip.videoUrl)) {
      return work.finalClips
    }
    return buildDefaultFinalClips(workScenes)
  }

  function loadAutoWorkForEditing(work) {
    const workScenes = getCurrentScenesForWork(work)
    const clips = buildClipsForAutoWork(work, workScenes)
    setFinalClips(clips)
    setFinalVideo(work.finalVideo || null)
    setFinalVideoRefreshToken(work.finalVideo?.local_refresh_token || work.finalVideo?.generated_at || work.finalVideo?.video_url || `${Date.now()}`)
    setClipPreviewState({})
    setNotice({ type: 'success', text: `已载入 ${work.title || '成品'}，可以继续编辑分镜和剪辑表。` })
  }

  function restoreAllScenesFromAutoWorks() {
    const restoredWorks = collectRestorableAutoWorks(autoWorkArchive, autoWorks)
    const restoredScenes = collectRestorableScenes(
      batchSceneArchive,
      scenes,
      collectScenesFromAutoWorks(restoredWorks),
    )
    if (!restoredScenes.length) {
      setNotice({ type: 'warning', text: '当前没有可恢复的批量分镜记录。' })
      return
    }
    setScenes(restoredScenes)
    setBatchSceneArchive(restoredScenes)
    if (restoredWorks.length) {
      setAutoWorks(restoredWorks)
      setAutoWorkArchive(restoredWorks)
    }
    setClipPreviewState({})
    const adSceneCount = restoredScenes.filter(scene => scene.referenceMode !== 'product_detail' && scene.reference_mode !== 'product_detail').length
    const hasDetailScene = restoredScenes.some(scene => scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail')
    setNotice({
      type: 'success',
      text: `已恢复 ${restoredScenes.length} 条批量分镜（${adSceneCount} 条广告分镜${hasDetailScene ? ' + 1 条产品细节' : ''}）${restoredWorks.length ? `，并恢复 ${restoredWorks.length} 个批量成品。` : '。'}`,
    })
    return
    {
    const sceneMap = new Map()
    let detailScene = null
    autoWorks.forEach(work => {
      ;(work.scenes || []).forEach(scene => {
        if (!scene?.id) return
        const isProductDetail = scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail'
        if (isProductDetail) {
          detailScene = {
            ...(detailScene || {}),
            ...scene,
          }
          return
        }
        const key = scene.id
        const existing = sceneMap.get(key)
        sceneMap.set(key, normalizeScene({
          ...(existing || {}),
          ...scene,
          storyboardImageHistory: mergeVersionHistory(
            existing?.storyboardImageHistory || scene.storyboardImageHistory || scene.storyboard_image_history,
            makeVersionItem(existing?.storyboard_image_url || scene.storyboard_image_url || scene.storyboardImageUrl),
          ),
          videoHistory: mergeVersionHistory(
            existing?.videoHistory || scene.videoHistory || scene.video_history,
            makeVersionItem(existing?.video_url || scene.video_url || scene.videoUrl),
          ),
        }, sceneMap.size))
      })
    })
    const restoredScenes = Array.from(sceneMap.values())
    if (detailScene) {
      restoredScenes.push(normalizeScene(detailScene, restoredScenes.length))
    }
    if (!restoredScenes.length) {
      setNotice({ type: 'warning', text: '当前没有可恢复的批量分镜记录。' })
      return
    }
    setScenes(restoredScenes)
    setClipPreviewState({})
    setNotice({ type: 'success', text: `已恢复 ${restoredScenes.length} 条批量分镜，可继续选片审片。` })
  }

    }
  async function handleRecoverLocalAssets() {
    const folderPath = String(localRecoveryFolder || '').trim()
    if (!folderPath) {
      setNotice({ type: 'warning', text: '请先填写本地素材文件夹路径。' })
      return
    }
    startLoading('recover-local-assets')
    setNotice(null)
    try {
      const result = await api.post('/api/batch-video/recover-local-assets', {
        folder_path: folderPath,
        product_name: product.name,
        limit: 120,
      }, { timeout: 120_000 })
      const recoveredScenes = (result.scenes || []).map((scene, index) => normalizeScene(scene || {}, index))
      if (!recoveredScenes.length) {
        setNotice({ type: 'warning', text: result.message || '没有找到可恢复的视频分镜。' })
        return
      }
      const nextFinalClips = buildDefaultFinalClips(recoveredScenes)
      const nextWorks = buildAutoWorksFromScenes(recoveredScenes, {
        includeDetail: false,
        preferredClips: nextFinalClips,
      })
      setScenes(recoveredScenes)
      setBatchSceneArchive(prev => collectRestorableScenes(prev, recoveredScenes))
      setAutoWorks(nextWorks)
      setAutoWorkArchive(prev => collectRestorableAutoWorks(prev, nextWorks))
      setFinalClips(nextFinalClips)
      setFinalVideo(null)
      setClipPreviewState({})
      setNotice({
        type: 'success',
        text: result.message || `已恢复 ${recoveredScenes.length} 条本地视频分镜。`,
      })
    } catch (error) {
      setNotice({ type: 'error', text: `本地素材恢复失败：${displayError(error)}` })
    } finally {
      finishLoading('recover-local-assets')
    }
  }

  function continueAutoWorkCompose(work) {
    const workScenes = getCurrentScenesForWork(work)
    const readyAdScenes = workScenes.filter(scene => (
      scene.video_url
      && scene.referenceMode !== 'product_detail'
      && scene.reference_mode !== 'product_detail'
    ))
    const readyScenes = workScenes.filter(scene => (
      scene.video_url
      && (scene.referenceMode !== 'product_detail' || readyAdScenes.length >= AUTO_WORK_MIN_SCENES)
    ))
    if (readyAdScenes.length < AUTO_WORK_MIN_SCENES) {
      setNotice({ type: 'warning', text: '这条成品还不够 3 个可用广告片段，先生成或选片后再合成。' })
      return
    }
    if (!productPosterUrl) {
      setNotice({ type: 'warning', text: '请先生成或选择收尾产品海报，成品视频结尾需要带海报。' })
      return
    }
    void composeAutoWork(work, readyScenes)
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

  async function generateStoryboardImageForAutoBatch(scene) {
    if (isUnsupportedModel(imageModel, imageModels)) {
      throw new Error('当前图片模型还没有接入适配器，请先切换可用图片模型。')
    }
    const productReferences = product.detailSheetUrl ? [product.detailSheetUrl] : []
    if (!productReferences.length) {
      throw new Error('请先用 Image2 还原产品完整形态，再自动批量生成分镜图和视频。')
    }
    const taskKey = `image-${scene.id}`
    startLoading(taskKey)
    updateScene(scene.id, { status: 'image_generating', error: '' })
    try {
      const provider = providerForModel(imageModel, imageModels, 'jimeng')
      const referencePrompt = [
        '【参考】只使用当前最终版 Image2 产品完整形态还原图作为唯一产品身份参考；必须保持同一款产品的轮廓、材质、结构、比例、鞋面、鞋底、扣具、纹理、配色和 logo 位置一致。',
        '【批量差异】本条分镜来自批量生产矩阵，必须保留当前分镜的独立角度、场景、光线、机位和广告质感，不要复用上一条分镜构图。',
        '【禁用】不要出现字幕、屏幕文字、价格、二维码、水印、主播、直播间、购买按钮、促销大字或电商 UI。',
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
      if (!imageUrl) throw new Error('图片模型未返回分镜图地址')
      const version = makeVersionItem(imageUrl, {
        prompt: referencePrompt,
        source: imageModel,
        label: `分镜图 ${new Date().toLocaleTimeString()}`,
      })
      const nextScene = {
        ...scene,
        storyboard_image_url: imageUrl,
        storyboardImageHistory: mergeVersionHistory(scene.storyboardImageHistory, version),
        status: 'storyboard_ready',
        error: '',
      }
      updateScene(scene.id, {
        storyboard_image_url: nextScene.storyboard_image_url,
        storyboardImageHistory: nextScene.storyboardImageHistory,
        status: nextScene.status,
        error: '',
      })
      return nextScene
    } catch (error) {
      updateScene(scene.id, { status: 'failed', error: displayError(error) })
      throw error
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
        provider === 'toapis' && !isProductDetailEnding
          ? '【Veo 首帧锁定】第 1 张输入图就是当前最终版分镜图，并且已按 frame 模式提交给视频模型。视频第 0 秒第一帧必须从这张分镜图无缝开始，构图、鞋型、鞋底齿纹、鞋面分区、鞋带孔、品牌位置、配色、磨损/水滴/岩石环境都必须延续，不得重新设计一双鞋，不得替换成相似鞋款，不得把产品改成其他登山鞋或跑鞋。镜头只能在这张首帧基础上做轻微推进、微摇、环境水雾和光影变化。'
          : '',
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
      const requestResolution = videoModelRequestedResolution(selectedModel, videoResolution)
      const requestAspectRatio = referenceImageMode ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio
      const body = {
        project_id: '',
        prompt: referenceVideoPrompt,
        provider,
        model: videoModel,
        duration: requestDuration,
        aspect_ratio: requestAspectRatio,
        resolution: requestResolution,
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
      const requestResolution = videoModelRequestedResolution(selectedVideoModel, videoResolution)
      const result = await api.post('/api/batch-video/submit', {
        product: productPayload,
        scenes,
        image_model: imageModel,
        video_model: videoModel,
        aspect_ratio: veoMode ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio,
        duration: veoMode ? 8 : duration,
        resolution: requestResolution,
      })
      setBatchResult(result)
      setNotice({ type: 'success', text: result.message || '批量任务已整理完成。' })
    } catch (error) {
      setNotice({ type: 'error', text: `批量任务整理失败：${displayError(error)}` })
    } finally {
      finishLoading('submit')
    }
  }

  async function handleAutoBatchGenerateVideos() {
    if (!product.name.trim()) {
      setNotice({ type: 'warning', text: '请先填写产品名称。' })
      return
    }
    if (!product.detailSheetUrl) {
      setNotice({ type: 'warning', text: '请先用 Image2 还原产品完整形态，自动批量需要用它锁定同一款产品外观。' })
      return
    }
    const matrixScenes = createMatrixScenes()
    if (!matrixScenes.length) {
      setNotice({ type: 'warning', text: '请先整理卖点，或在手动卖点里至少填写一条。自动批量会按卖点生成不同角度的视频。' })
      return
    }

    setScenes(matrixScenes)
    setBatchResult({
      message: `已创建 ${matrixScenes.length} 条不同角度的自动批量视频任务。`,
      tasks: matrixScenes.map(scene => ({
        id: scene.id,
        title: scene.title,
        scene_id: scene.id,
        status: 'queued',
      })),
    })
    setFinalVideo(null)
    setFinalClips([])
    setClipPreviewState({})
    setAutoClipBuildPending(true)
    startLoading('auto-batch-video')
    setNotice({
      type: 'info',
      text: `正在按 ${matrixScenes.length} 个不同角度生成分镜图和视频，并发 ${AUTO_BATCH_CONCURRENCY} 个；剪辑表默认 0-${DEFAULT_AUTO_CLIP_DURATION}s / ${DEFAULT_AUTO_CLIP_PLAYBACK_RATE}x。`,
    })

    const generatedScenes = []
    const failedScenes = []
    try {
      await runWithConcurrency(matrixScenes, AUTO_BATCH_CONCURRENCY, async scene => {
        try {
          const sceneWithImage = scene.storyboard_image_url ? scene : await generateStoryboardImageForAutoBatch(scene)
          if (!sceneWithImage?.storyboard_image_url) {
            throw new Error('分镜图生成失败，未进入视频生成。')
          }
          generatedScenes.push(sceneWithImage)
          await handleGenerateVideo(sceneWithImage)
        } catch (error) {
          failedScenes.push({ scene, error })
          updateScene(scene.id, { status: 'failed', error: displayError(error) })
        }
      })
      setNotice({
        type: failedScenes.length ? 'warning' : 'success',
        text: failedScenes.length
          ? `已提交 ${generatedScenes.length} 条不同角度视频，${failedScenes.length} 条失败；成功的视频生成完成后会自动回填剪辑表。`
          : `已提交 ${generatedScenes.length} 条不同角度视频，生成完成后会自动回填剪辑表。`,
      })
    } catch (error) {
      setNotice({ type: 'error', text: `按不同角度自动批量生成失败：${displayError(error)}` })
    } finally {
      finishLoading('auto-batch-video')
    }
  }

  async function handleContinueIncompleteScenes() {
    if (!scenes.length) {
      setNotice({ type: 'warning', text: '当前页面还没有分镜，不能继续生成。' })
      return
    }
    if (!product.detailSheetUrl) {
      setNotice({ type: 'warning', text: '请先选择最终版 Image2 产品还原图，否则无法稳定继续生成分镜图和视频。' })
      return
    }
    const pendingScenes = scenes.filter(scene => {
      if (scene.video_url || scene.taskId || isProcessingTaskStatus(scene.status)) return false
      if (scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail') {
        return true
      }
      return !scene.storyboard_image_url || !scene.video_url || scene.status === 'failed'
    })
    if (!pendingScenes.length) {
      setNotice({ type: 'success', text: '当前没有需要继续生成的分镜：已完成或正在处理中的都会自动跳过。' })
      return
    }

    startLoading('continue-scenes')
    setNotice({
      type: 'info',
      text: `正在继续生成 ${pendingScenes.length} 个未完成分镜；已完成和正在处理的分镜会跳过。`,
    })
    const continuedScenes = []
    const failedScenes = []
    try {
      await runWithConcurrency(pendingScenes, AUTO_BATCH_CONCURRENCY, async scene => {
        try {
          const isProductDetailScene = scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail'
          const sceneWithImage = isProductDetailScene || scene.storyboard_image_url
            ? scene
            : await generateStoryboardImageForAutoBatch(scene)
          if (!isProductDetailScene && !sceneWithImage?.storyboard_image_url) {
            throw new Error('分镜图生成失败，未进入视频生成。')
          }
          await handleGenerateVideo(sceneWithImage)
          continuedScenes.push(sceneWithImage)
        } catch (error) {
          failedScenes.push({ scene, error })
          updateScene(scene.id, { status: 'failed', error: displayError(error) })
        }
      })
      setNotice({
        type: failedScenes.length ? 'warning' : 'success',
        text: failedScenes.length
          ? `已继续提交 ${continuedScenes.length} 个分镜，${failedScenes.length} 个仍失败；稍后可再次点击继续。`
          : `已继续提交 ${continuedScenes.length} 个未完成分镜，视频完成后会自动显示。`,
      })
    } catch (error) {
      setNotice({ type: 'error', text: `继续生成失败：${displayError(error)}` })
    } finally {
      finishLoading('continue-scenes')
    }
  }

  async function handleAutoBatchGenerateWorks() {
    if (!product.name.trim()) {
      setNotice({ type: 'warning', text: '请先填写产品名称。' })
      return
    }
    if (!product.detailSheetUrl) {
      setNotice({ type: 'warning', text: '请先用 Image2 还原产品完整形态，自动生成素材需要用它锁定同一款产品外观。' })
      return
    }
    const matrixScenes = createMatrixScenes()
    if (!matrixScenes.length) {
      setNotice({ type: 'warning', text: '请先整理卖点，或在手动卖点里至少填写一条。' })
      return
    }
    const nextWorks = buildAutoWorksFromScenes(matrixScenes, { includeDetail: true, preferredClips: finalClips })
    const allScenes = nextWorks.flatMap(work => work.scenes || [])
    if (!nextWorks.length || !allScenes.length) {
      setNotice({ type: 'warning', text: '可生成的分镜不足，至少需要 3 个不同角度才能组成一条成品。' })
      return
    }
    setScenes(allScenes)
    setBatchSceneArchive(collectRestorableScenes(allScenes))
    setAutoWorks(nextWorks)
    setAutoWorkArchive(nextWorks)
    setBatchResult({
      message: `已创建 ${nextWorks.length} 条自动成品；每条默认 3-4 个广告分镜，优先追加产品细节视频，最终合成必须带海报。`,
      tasks: nextWorks.map(work => ({
        id: work.id,
        title: work.title,
        scene_id: work.id,
        status: work.status,
      })),
    })
    setFinalVideo(null)
    setFinalClips([])
    setClipPreviewState({})
    setAutoClipBuildPending(false)
    startLoading('auto-batch-video')
    setNotice({
      type: productPosterUrl ? 'info' : 'warning',
      text: productPosterUrl
        ? `正在生成 ${allScenes.length} 个素材，已分成 ${nextWorks.length} 条成品；素材完成后会自动合成带海报的成品。`
        : `正在先生成 ${allScenes.length} 个素材；当前还没有海报，生成海报后会自动合成最终成品。`,
    })

    const generatedScenes = []
    const failedScenes = []
    try {
      setAutoWorks(prev => prev.map(work => ({ ...work, status: 'generating', updatedAt: Date.now() })))
      await runWithConcurrency(allScenes, AUTO_BATCH_CONCURRENCY, async scene => {
        try {
          const isProductDetailScene = scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail'
          if (scene.video_url) {
            generatedScenes.push(scene)
            return
          }
          const sceneWithImage = isProductDetailScene || scene.storyboard_image_url
            ? scene
            : await generateStoryboardImageForAutoBatch(scene)
          if (!isProductDetailScene && !sceneWithImage?.storyboard_image_url) {
            throw new Error('分镜图生成失败，未进入视频生成。')
          }
          generatedScenes.push(sceneWithImage)
          await handleGenerateVideo(sceneWithImage)
        } catch (error) {
          failedScenes.push({ scene, error })
          updateScene(scene.id, { status: 'failed', error: displayError(error) })
        }
      })
      setAutoWorks(prev => prev.map(work => {
        const hasFailedScene = failedScenes.some(item => (work.sceneIds || []).includes(item.scene.id))
        return {
          ...work,
          status: 'submitted',
          error: hasFailedScene ? '部分素材生成失败；如果仍有 3 个以上广告片段可用，会继续尝试合成。' : '',
          updatedAt: Date.now(),
        }
      }))
      setNotice({
        type: failedScenes.length ? 'warning' : 'success',
        text: failedScenes.length
          ? `已提交 ${generatedScenes.length} 个素材，${failedScenes.length} 个失败；有足够可用片段的成品会继续自动合成。`
          : `已提交 ${generatedScenes.length} 个素材，完成后会按成品组自动混剪并追加海报。`,
      })
    } catch (error) {
      setNotice({ type: 'error', text: `按不同角度自动批量生成失败：${displayError(error)}` })
    } finally {
      finishLoading('auto-batch-video')
    }
  }

  async function composeVideoFromClips(sourceClips, sourceScenes, outputName = '', voiceoverStyle = '') {
    const segments = buildSegmentsFromClips(sourceClips, sourceScenes)
    if (!segments.length) {
      throw new Error('没有可用的视频片段')
    }
    if (!productPosterUrl) {
      throw new Error('请先生成或选择收尾产品海报')
    }
    const selectedTtsVoiceType = ttsVoiceType === 'custom' ? ttsCustomVoiceType.trim() : ttsVoiceType
    const selectedBgmVolume = clampNumber(bgmVolume, 0, 1, 0.45)
    const selectedVoiceoverVolume = clampNumber(voiceoverVolume, 0.2, 2, DEFAULT_VOICEOVER_VOLUME)
    return api.post('/api/batch-video/compose-final-video', {
      segments,
      product_name: product.name || '',
      product_description: product.description || product.category || '',
      selling_points: [
        ...sellingPoints.map(point => point.title || point.description).filter(Boolean),
        ...sourceScenes.map(scene => scene.selling_point || scene.hook || scene.title).filter(Boolean),
      ].slice(0, 12),
      voiceover_style: voiceoverStyle,
      aspect_ratio: isVeoModel(videoModel) ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio,
      subtitle_enabled: true,
      voiceover_enabled: true,
      keep_original_audio: true,
      bgm_enabled: bgmEnabled,
      bgm_url: bgmEnabled ? bgmUrl : '',
      original_audio_volume: 0.35,
      voiceover_volume: selectedVoiceoverVolume,
      rhythm_match_enabled: rhythmMatchEnabled,
      bgm_volume: selectedBgmVolume,
      poster_image_url: productPosterUrl || '',
      poster_duration: 0,
      tts_provider: 'doubao_speech_2_0',
      tts_voice_type: selectedTtsVoiceType,
      tts_speed_ratio: Number(ttsSpeedRatio) || 1,
      output_name: outputName || product.name || 'batch_final_video',
    })
  }

  async function composeAutoWork(work, workScenes) {
    if (!work?.id || autoWorkComposingRef.current.has(work.id)) return
    const clips = buildClipsForAutoWork(work, workScenes).filter(clip => clip.videoUrl)
    const usableAdClips = clips.filter(clip => {
      const scene = workScenes.find(item => item.id === clip.sceneId)
      return scene?.referenceMode !== 'product_detail'
    })
    if (usableAdClips.length < AUTO_WORK_MIN_SCENES) return
    autoWorkComposingRef.current.add(work.id)
    setAutoWorks(prev => prev.map(item => (
      item.id === work.id ? { ...item, status: 'composing', error: '', finalClips: clips, updatedAt: Date.now() } : item
    )))
    try {
      const composeStartedAt = new Date().toISOString()
      const result = await composeVideoFromClips(
        clips,
        workScenes,
        `${product.name || 'product'}_${work.title || work.id}`,
        work.strategy || work.title || '',
      )
      if (result.status !== 'completed' || !result.video_url) {
        throw new Error(result.message || '成片合成失败')
      }
      const nextFinalVideo = {
        ...result,
        generated_at: composeStartedAt,
        local_refresh_token: `${Date.now()}`,
      }
      setAutoWorks(prev => prev.map(item => (
        item.id === work.id
          ? {
            ...item,
            status: 'completed',
            error: '',
            scenes: workScenes,
            finalClips: clips,
            finalVideo: nextFinalVideo,
            updatedAt: Date.now(),
          }
          : item
      )))
    } catch (error) {
      setAutoWorks(prev => prev.map(item => (
        item.id === work.id ? { ...item, status: 'failed', error: displayError(error), updatedAt: Date.now() } : item
      )))
    } finally {
      autoWorkComposingRef.current.delete(work.id)
    }
  }

  function handleMixSelectedClipsIntoWorks() {
    const usableClips = finalClips.filter(clip => clip.videoUrl)
    if (!usableClips.length) {
      setNotice({ type: 'warning', text: '请先在剪辑表里用滑块选好可用片段，再批量混剪成品。' })
      return
    }
    if (!productPosterUrl) {
      setNotice({ type: 'warning', text: '请先生成或选择收尾产品海报；自动混剪的每条成品都会带海报。' })
      return
    }
    const groups = splitAutoWorkClipGroups(usableClips)
    if (!groups.length) {
      setNotice({ type: 'warning', text: '可用片段不足，至少需要 3 个片段才能自动混剪一条成品。' })
      return
    }
    const nextWorks = groups.map((group, workIndex) => {
      const workId = `mix_work_${Date.now()}_${workIndex}_${Math.random().toString(36).slice(2, 7)}`
      const sceneIds = Array.from(new Set(group.map(clip => clip.sceneId).filter(Boolean)))
      const groupScenes = sceneIds.map(sceneId => scenes.find(scene => scene.id === sceneId)).filter(Boolean)
      const detailScene = scenes.find(scene => scene.referenceMode === 'product_detail' && scene.video_url)
      const workScenes = [...groupScenes, detailScene].filter(Boolean).map(scene => ({ ...scene, autoWorkId: workId }))
      const clips = group
        .map((clip, clipIndex) => normalizeFinalClip(clip, clipIndex, workScenes))
        .filter(Boolean)
      if (detailScene && !clips.some(clip => clip.sceneId === detailScene.id)) {
        const detailClip = createFinalClipFromScene(detailScene, clips.length)
        if (detailClip) clips.push(detailClip)
      }
      return normalizeAutoWork({
        id: workId,
        title: `混剪成品 ${workIndex + 1}`,
        strategy: groupScenes.map(scene => scene.selling_point || scene.title).filter(Boolean).join(' / '),
        status: 'ready',
        scenes: workScenes,
        sceneIds: workScenes.map(scene => scene.id),
        finalClips: clips,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      }, workIndex)
    })
    const mergedWorks = collectRestorableAutoWorks(autoWorks, autoWorkArchive, nextWorks)
    setAutoWorks(mergedWorks)
    setAutoWorkArchive(mergedWorks)
    setBatchResult({
      message: `已按你选好的片段创建 ${nextWorks.length} 条低同质化混剪成品，正在自动合成。`,
      tasks: mergedWorks.map(work => ({ id: work.id, title: work.title, status: work.status })),
    })
    setNotice({ type: 'info', text: `已创建 ${nextWorks.length} 条混剪成品，会优先使用你滑块选好的开始/结束时间，并全部追加海报。` })
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
          playback_rate: normalizeClipPlaybackRate(clip.playbackRate),
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
    setFinalVideo(null)
    setFinalVideoRefreshToken(`pending_${Date.now()}`)
    try {
      const composeStartedAt = new Date().toISOString()
      const result = await composeVideoFromClips(sourceClips, scenes, product.name || 'batch_final_video', 'manual final mix')
      if (result.status !== 'completed' || !result.video_url) {
        setNotice({ type: result.status === 'needs_video' ? 'warning' : 'error', text: result.message || '完整视频合成失败。' })
        return
      }
      const nextFinalVideo = {
        ...result,
        generated_at: composeStartedAt,
        local_refresh_token: `${Date.now()}`,
      }
      setFinalVideo(nextFinalVideo)
      setFinalVideoRefreshToken(`${nextFinalVideo.video_url}_${nextFinalVideo.local_refresh_token}`)
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
  const reviewableScenes = buildReviewableSceneCandidates(scenes, autoWorks)
  const selectedFinalClips = finalClips.filter(clip => clip.videoUrl)
  const selectedClipGroups = splitAutoWorkClipGroups(selectedFinalClips)
  const selectedClipCountBySceneId = selectedFinalClips.reduce((acc, clip) => {
    if (clip.sceneId) acc[clip.sceneId] = (acc[clip.sceneId] || 0) + 1
    return acc
  }, {})

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
        <div className="batch-video-local-recovery">
          <div className="batch-video-local-recovery-copy">
            <strong>本地素材恢复</strong>
            <span>把已经下载到本机的分镜图和视频恢复回当前分镜列表，适合从 ToAPIs 任务日志重新下载后找回。</span>
          </div>
          <input
            value={localRecoveryFolder}
            onChange={event => setLocalRecoveryFolder(event.target.value)}
            placeholder="例如：C:\Users\Administrator\Desktop\素材\ai素材"
          />
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={handleRecoverLocalAssets}
            disabled={isLoading('recover-local-assets')}
          >
            <FolderOpen size={16} />
            {isLoading('recover-local-assets') ? '恢复中' : '从本地素材恢复'}
          </button>
        </div>
        <div className="batch-video-toolbar">
          {autoWorks.length > 0 && (
            <button
              type="button"
              className="batch-video-button ghost"
              onClick={restoreAllScenesFromAutoWorks}
            >
              <RefreshCw size={16} />
              恢复全部分镜
            </button>
          )}
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
          <label className="batch-video-field batch-video-voiceover-volume">
            <span>旁白音量 {Math.round(clampNumber(voiceoverVolume, 0.2, 2, DEFAULT_VOICEOVER_VOLUME) * 100)}%</span>
            <input
              type="range"
              min="0.2"
              max="2"
              step="0.05"
              value={voiceoverVolume}
              onChange={event => setVoiceoverVolume(event.target.value)}
            />
          </label>
        </div>
        <div className="batch-video-rhythm-toolbar">
          <label className="batch-video-audio-toggle">
            <input
              type="checkbox"
              checked={rhythmMatchEnabled}
              onChange={event => setRhythmMatchEnabled(event.target.checked)}
            />
            <span>自动匹配画面/旁白节奏</span>
          </label>
          <span className="batch-video-audio-hint">
            先由你逐段筛选可用画面；合成时画面偏长会收短尾部，旁白偏长会自动精简，避免成片节奏拖慢。
          </span>
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
        <div className="batch-video-review-panel">
          <div className="batch-video-review-head">
            <div>
              <strong><ListChecks size={16} /> 选片审片</strong>
              <span>先挑可用画面，再在下方剪辑表拖动开始/结束，最后批量混剪成品。</span>
            </div>
            <div className="batch-video-review-stats">
              <span>{reviewableScenes.length} 个已生成视频</span>
              <span>{selectedFinalClips.length} 段已选片段</span>
              <span>约 {selectedClipGroups.length} 条可混剪成品</span>
            </div>
          </div>
          <div className="batch-video-review-actions">
            <button
              type="button"
              className="batch-video-button ghost"
              onClick={appendAllReviewableScenesToFinalClips}
              disabled={!reviewableScenes.length}
            >
              <RefreshCw size={16} />
              全部加入片段池
            </button>
            <button
              type="button"
              className="batch-video-button primary"
              onClick={handleMixSelectedClipsIntoWorks}
              disabled={!selectedFinalClips.length}
            >
              <Scissors size={16} />
              用已选片段批量混剪
            </button>
          </div>
          <div className="batch-video-review-grid">
            <div className="batch-video-review-library">
              <div className="batch-video-review-subtitle">
                <strong>生成素材候选</strong>
                <span>每个分镜可多次加入，方便截取不同区间。</span>
              </div>
              {reviewableScenes.length > 0 ? (
                <div className="batch-video-review-card-grid">
                  {reviewableScenes.map((scene, sceneIndex) => {
                    const selectedCount = selectedClipCountBySceneId[scene.sourceSceneId || scene.id] || 0
                    return (
                      <article className="batch-video-review-card" key={`${scene.sourceSceneId || scene.id}_${scene.candidateVideoUrl || scene.video_url}`}>
                        <div className="batch-video-review-preview">
                          <video src={assetUrl(scene.video_url)} controls preload="metadata" playsInline />
                        </div>
                        <div className="batch-video-review-card-body">
                          <strong>#{sceneIndex + 1} {scene.title || '未命名分镜'}</strong>
                          <span>{scene.hook || scene.selling_point || scene.voiceover_text || '已生成可选视频素材'}</span>
                          <div className="batch-video-review-card-actions">
                            <button type="button" className="batch-video-button ghost" onClick={() => appendFinalClipFromScene(scene)}>
                              <Plus size={15} />
                              加入可用片段
                            </button>
                            {selectedCount > 0 && <em>已选 {selectedCount} 段</em>}
                          </div>
                        </div>
                      </article>
                    )
                  })}
                </div>
              ) : (
                <div className="batch-video-empty compact">
                  <FileVideo size={24} />
                  <span>还没有可审片的视频，先继续生成未完成分镜。</span>
                </div>
              )}
            </div>
            <div className="batch-video-review-pool">
              <div className="batch-video-review-subtitle">
                <strong>已选片段池</strong>
                <span>下方剪辑表可以逐段设开始、结束、倍速和旁白。</span>
              </div>
              {selectedFinalClips.length > 0 ? (
                <div className="batch-video-review-clip-list">
                  {selectedFinalClips.map((clip, clipIndex) => {
                    const clipScene = scenes.find(scene => scene.id === clip.sceneId)
                    const clipStart = clip.startTime === '' ? 0 : Number(clip.startTime || 0)
                    const clipEndText = clip.endTime === '' ? '到结尾' : formatClipTime(clip.endTime)
                    const clipRate = normalizeClipPlaybackRate(clip.playbackRate)
                    return (
                      <div className="batch-video-review-clip" key={clip.id}>
                        <div>
                          <strong>{clipIndex + 1}. {clip.title || clipScene?.title || '可用片段'}</strong>
                          <span>{formatClipTime(clipStart)} - {clipEndText} / {clipRate}x</span>
                        </div>
                        <div className="batch-video-review-clip-actions">
                          <button type="button" title="复制片段" onClick={() => duplicateFinalClip(clip.id)}>
                            <Copy size={14} />
                          </button>
                          <button type="button" title="移出片段池" onClick={() => removeFinalClip(clip.id)}>
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="batch-video-empty compact">
                  <Scissors size={24} />
                  <span>左侧加入片段后，这里会显示待混剪素材。</span>
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="batch-video-final-toolbar">
          <button
            type="button"
            className="batch-video-button primary"
            onClick={handleAutoBatchGenerateWorks}
            disabled={isLoading('auto-batch-video') || !product.name.trim()}
          >
            <Video size={16} />
            {isLoading('auto-batch-video') ? '批量生成中' : '按不同角度批量生成视频'}
          </button>
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={handleContinueIncompleteScenes}
            disabled={isLoading('continue-scenes') || !scenes.length}
          >
            <RefreshCw size={16} />
            {isLoading('continue-scenes') ? '继续生成中' : '继续生成未完成'}
          </button>
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
            className="batch-video-button ghost"
            onClick={handleMixSelectedClipsIntoWorks}
            disabled={!finalClips.some(clip => clip.videoUrl)}
          >
            <Scissors size={16} />
            按已选片段批量混剪成品
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
              const previewState = clipPreviewState[clip.id] || {}
              const sliderMax = clipSliderMax(clip, previewState)
              const currentPreviewTime = Math.min(Number(previewState.currentTime || 0), sliderMax)
              const clipStartValue = clip.startTime === '' ? 0 : Number(clip.startTime || 0)
              const clipEndValue = clip.endTime === '' ? sliderMax : Number(clip.endTime || 0)
              const clipPlaybackRate = normalizeClipPlaybackRate(clip.playbackRate)
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
                      <button type="button" title="复制片段，截取同一视频另一段" onClick={() => duplicateFinalClip(clip.id)}>
                        <Copy size={14} />
                      </button>
                      <button type="button" title="删除片段" onClick={() => removeFinalClip(clip.id)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="batch-video-clip-body">
                    <div className="batch-video-clip-preview">
                      {clip.videoUrl ? (
                        <video
                          id={clipVideoElementId(clip.id)}
                          src={assetUrl(clip.videoUrl)}
                          controls
                          preload="metadata"
                          onLoadedMetadata={event => {
                            const nextDuration = Number(event.currentTarget.duration || 0)
                            updateClipPreviewState(clip.id, {
                              duration: Number.isFinite(nextDuration) ? nextDuration : 0,
                              currentTime: Number(event.currentTarget.currentTime || 0),
                            })
                            event.currentTarget.playbackRate = clipPlaybackRate
                          }}
                          onPlay={event => {
                            event.currentTarget.playbackRate = clipPlaybackRate
                          }}
                          onTimeUpdate={event => updateClipPreviewState(clip.id, {
                            currentTime: Number(event.currentTarget.currentTime || 0),
                          })}
                        />
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
                            updateClipPreviewState(clip.id, { currentTime: 0, duration: 0 })
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
                      <label className="batch-video-field">
                        <span>画面倍速</span>
                        <select
                          value={clipPlaybackRate}
                          onChange={event => {
                            const nextRate = normalizeClipPlaybackRate(event.target.value)
                            updateFinalClip(clip.id, { playbackRate: nextRate })
                            const video = typeof document === 'undefined' ? null : document.getElementById(clipVideoElementId(clip.id))
                            if (video) video.playbackRate = nextRate
                          }}
                        >
                          {CLIP_PLAYBACK_RATE_OPTIONS.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </label>
                      {clip.videoUrl && (
                        <div className="batch-video-clip-trimmer">
                          <div className="batch-video-clip-trimmer-head">
                            <span>当前画面 {formatClipTime(currentPreviewTime)}</span>
                            <span>
                              截取 {formatClipTime(clipStartValue)}
                              {' - '}
                              {clip.endTime === '' ? '结尾' : formatClipTime(clipEndValue)}
                            </span>
                          </div>
                          <input
                            className="batch-video-clip-range"
                            type="range"
                            min="0"
                            max={sliderMax}
                            step="0.1"
                            value={currentPreviewTime}
                            onChange={event => seekClipPreview(clip.id, event.target.value)}
                          />
                          <div className="batch-video-clip-trimmer-actions">
                            <button type="button" className="batch-video-button ghost" onClick={() => setClipBoundaryFromPreview(clip.id, 'start')}>
                              设为开始
                            </button>
                            <button type="button" className="batch-video-button ghost" onClick={() => setClipBoundaryFromPreview(clip.id, 'end')}>
                              设为结束
                            </button>
                            <button type="button" className="batch-video-button ghost" onClick={() => previewFinalClip(clip)}>
                              试看片段
                            </button>
                          </div>
                        </div>
                      )}
                      <div className="batch-video-clip-time-grid">
                        <label className="batch-video-field">
                          <span>开始秒</span>
                          <div className="batch-video-clip-time-input-row">
                            <input
                              type="number"
                              min="0"
                              step="0.1"
                              value={clip.startTime}
                              onChange={event => updateFinalClip(clip.id, { startTime: event.target.value })}
                            />
                            <button
                              type="button"
                              className="batch-video-button ghost"
                              onClick={() => setClipBoundaryFromPreview(clip.id, 'start')}
                              disabled={!clip.videoUrl}
                            >
                              取当前为开始
                            </button>
                          </div>
                          <input
                            className="batch-video-clip-field-range"
                            type="range"
                            min="0"
                            max={sliderMax}
                            step="0.1"
                            value={Math.min(clipStartValue, sliderMax)}
                            onChange={event => updateFinalClip(clip.id, { startTime: event.target.value })}
                          />
                        </label>
                        <label className="batch-video-field">
                          <span>结束秒</span>
                          <div className="batch-video-clip-time-input-row">
                            <input
                              type="number"
                              min="0"
                              step="0.1"
                              value={clip.endTime}
                              placeholder="到结尾"
                              onChange={event => updateFinalClip(clip.id, { endTime: event.target.value })}
                            />
                            <button
                              type="button"
                              className="batch-video-button ghost"
                              onClick={() => setClipBoundaryFromPreview(clip.id, 'end')}
                              disabled={!clip.videoUrl}
                            >
                              取当前为结束
                            </button>
                          </div>
                          <input
                            className="batch-video-clip-field-range"
                            type="range"
                            min="0"
                            max={sliderMax}
                            step="0.1"
                            value={Math.min(clipEndValue, sliderMax)}
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
            <video
              key={`${finalVideo.video_url}_${finalVideoRefreshToken}`}
              src={cacheBustedAssetUrl(finalVideo.video_url, finalVideoRefreshToken)}
              controls
            />
            <div className="batch-video-final-meta">
              {finalVideo.poster_appended
                ? `已追加收尾海报，停留约 ${Number(finalVideo.poster_duration || 0).toFixed(1)} 秒`
                : '这条成片未追加收尾海报'}
            </div>
            <a className="batch-video-button ghost" href={cacheBustedAssetUrl(finalVideo.video_url, finalVideoRefreshToken)} download>
              下载完整视频
            </a>
          </div>
        )}
        {autoWorks.length > 0 && (
          <div className="batch-video-auto-works">
            <div className="batch-video-auto-works-head">
              <div>
                <strong>批量成品</strong>
                <span>每条成品由 3-4 个广告片段混剪，产品细节视频有则加入，结尾必须带海报。</span>
              </div>
              <button
                type="button"
                className="batch-video-button ghost"
                onClick={restoreAllScenesFromAutoWorks}
              >
                <ListChecks size={16} />
                恢复全部分镜
              </button>
              <button
                type="button"
                className="batch-video-button ghost"
                onClick={handleMixSelectedClipsIntoWorks}
                disabled={!finalClips.some(clip => clip.videoUrl)}
              >
                <Scissors size={16} />
                用当前剪辑表重新混剪
              </button>
            </div>
            <div className="batch-video-auto-work-grid">
              {autoWorks.map((work, workIndex) => {
                const workScenes = getCurrentScenesForWork(work)
                const adCount = workScenes.filter(scene => scene.referenceMode !== 'product_detail' && scene.reference_mode !== 'product_detail').length
                const detailReady = workScenes.some(scene => (scene.referenceMode === 'product_detail' || scene.reference_mode === 'product_detail') && scene.video_url)
                const finalWorkVideoUrl = work.finalVideo?.video_url || ''
                const previewUrl = finalWorkVideoUrl
                  || workScenes.find(scene => scene.video_url)?.video_url
                  || workScenes.find(scene => scene.storyboard_image_url)?.storyboard_image_url
                  || productPosterUrl
                const isGeneratedVideo = Boolean(finalWorkVideoUrl)
                const isVideoPreview = Boolean(finalWorkVideoUrl || workScenes.find(scene => scene.video_url)?.video_url)
                return (
                  <div className="batch-video-auto-work-card" key={work.id || workIndex}>
                    <button
                      type="button"
                      className="batch-video-auto-work-preview"
                      onClick={() => loadAutoWorkForEditing(work)}
                      title="进入编辑模式"
                    >
                      {isVideoPreview && previewUrl ? (
                        <video src={assetUrl(previewUrl)} muted playsInline preload="metadata" />
                      ) : previewUrl ? (
                        <img src={assetUrl(previewUrl)} alt={work.title || `成品 ${workIndex + 1}`} />
                      ) : (
                        <span>{workIndex + 1}</span>
                      )}
                    </button>
                    <div className="batch-video-auto-work-body">
                      <strong>{work.title || `成品 ${workIndex + 1}`}</strong>
                      <span>{autoWorkStatusText(work.status)} · {adCount} 个广告片段 · {detailReady ? '含产品细节' : '细节可缺省'} · 带海报</span>
                      {work.strategy && <span className="batch-video-auto-work-strategy">{work.strategy}</span>}
                      {work.error && <em>{work.error}</em>}
                      {finalWorkVideoUrl && (
                        <video
                          className="batch-video-auto-work-final-player"
                          src={cacheBustedAssetUrl(finalWorkVideoUrl, work.finalVideo?.local_refresh_token || work.finalVideo?.generated_at || '')}
                          controls
                          playsInline
                          preload="metadata"
                        />
                      )}
                      <div className="batch-video-auto-work-actions">
                        <button type="button" className="batch-video-button ghost" onClick={() => loadAutoWorkForEditing(work)}>
                          编辑此成品
                        </button>
                        {!finalWorkVideoUrl && (
                          <button
                            type="button"
                            className="batch-video-button primary"
                            onClick={() => continueAutoWorkCompose(work)}
                            disabled={autoWorkComposingRef.current.has(work.id)}
                          >
                            <Scissors size={15} />
                            {work.status === 'composing' ? '继续合成中' : '继续合成'}
                          </button>
                        )}
                        {work.finalVideo?.video_url && (
                          <a className="batch-video-button ghost" href={assetUrl(work.finalVideo.video_url)} download>
                            下载
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
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
            onClick={handleAutoBatchGenerateWorks}
            disabled={isLoading('auto-batch-video') || !product.name.trim()}
          >
            <Video size={16} />
            {isLoading('auto-batch-video') ? '批量生成中' : '按不同角度批量生成视频'}
          </button>
          <button
            type="button"
            className="batch-video-button ghost"
            onClick={handleMixSelectedClipsIntoWorks}
            disabled={!finalClips.some(clip => clip.videoUrl)}
          >
            <Scissors size={16} />
            按已选片段混剪成品
          </button>
        </div>
        {batchResult?.tasks?.length ? (
          <div className="batch-video-task-list">
            {batchResult.tasks.map(task => (
              <div className="batch-video-task-row" key={task.id}>
                <span>{task.title || task.scene_id}</span>
                <div className="batch-video-task-status">
                  <code>{task.status}</code>
                  {task.video_url && (
                    <a className="batch-video-button ghost" href={assetUrl(task.video_url)} download>
                      下载成片
                    </a>
                  )}
                </div>
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
