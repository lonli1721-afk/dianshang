import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Boxes,
  Clapperboard,
  FileVideo,
  Image as ImageIcon,
  ListChecks,
  Mic2,
  Package,
  Play,
  Plus,
  Sparkles,
  Trash2,
  Upload,
  Video,
  Wand2,
} from 'lucide-react'
import { api } from '../services/api'
import { useGameTaskPolling } from './game/useGameTaskPolling'

const DEFAULT_LANGUAGE_MODELS = [
  { id: 'doubao-seed-2-0-pro-260215', name: 'Doubao Seed 2.0 Pro', available: true },
  { id: 'doubao-seed-2-0-mini', name: 'Doubao Seed 2.0 Mini', available: false },
  { id: 'doubao-seed-2-0-lite', name: 'Doubao Seed 2.0 Lite', available: false },
]

const DEFAULT_IMAGE_MODELS = [
  { id: 'image2', name: 'Image2 产品还原', provider: 'jimeng', available: true },
  { id: 'seedream-5.0', name: 'Seedream 5.0', provider: 'jimeng', available: true },
  { id: 'seedream-4.5', name: 'Seedream 4.5', provider: 'jimeng', available: true },
  { id: 'nanobanana', name: 'Nano Banana', provider: 'custom_image', available: false },
]

const DEFAULT_VIDEO_MODELS = [
  { id: 'seedance-2.0', name: 'Seedance 2.0', provider: 'jimeng', available: true },
  { id: 'happyhorse-1.0-i2v', name: 'HappyHorse I2V', provider: 'happyhorse', available: true },
  { id: 'happyhorse-1.0-t2v', name: 'HappyHorse T2V', provider: 'happyhorse', available: true },
  { id: 'veo3.1-fast', name: 'Veo 3.1 Fast', provider: 'toapis', available: true },
  { id: 'veo3.1-lite', name: 'Veo 3.1 Lite', provider: 'toapis', available: true },
  { id: 'veo3.1-quality', name: 'Veo 3.1 Quality', provider: 'toapis', available: true },
]

const ASPECT_OPTIONS = ['9:16', '16:9', '1:1', '4:3', '3:4']
const DURATION_OPTIONS = [4, 5, 6, 8, 10, 12, 15]
const DEFAULT_STORYBOARD_SCENE_COUNT = 6
const VEO_STORYBOARD_SCENE_COUNT = 4
const VEO_STORYBOARD_DURATION = 8
const WORKBENCH_DRAFT_STORAGE_KEY = 'ecommerce-batch-video-workbench-draft-v1'

const DEFAULT_PRODUCT = {
  name: '',
  category: '',
  description: '',
  imageUrls: [],
  detailSheetUrl: '',
  detailSheetPrompt: '',
}

function createDefaultDraft() {
  return {
    product: { ...DEFAULT_PRODUCT, imageUrls: [] },
    languageModel: DEFAULT_LANGUAGE_MODELS[0].id,
    imageModel: DEFAULT_IMAGE_MODELS[0].id,
    videoModel: DEFAULT_VIDEO_MODELS[0].id,
    aspectRatio: '9:16',
    duration: 5,
    variantCount: DEFAULT_STORYBOARD_SCENE_COUNT,
    liveVideo: null,
    transcript: '',
    manualSellingPoints: '',
    sellingPoints: [],
    storyboardReferences: [],
    scenes: [],
    batchResult: null,
  }
}

function readMediaUrl(result) {
  if (!result) return ''
  if (typeof result === 'string') return result
  if (result.url) return result.url
  if (result.image_url) return result.image_url
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

function splitLines(text) {
  return String(text || '')
    .split(/\n|；|;/)
    .map(item => item.trim())
    .filter(Boolean)
}

function modelLabel(model) {
  const suffix = model.available === false ? '（待接入）' : ''
  return `${model.name || model.id}${suffix}`
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

function storyboardDefaultsForVideoModel(modelId) {
  return isVeoModel(modelId)
    ? { count: VEO_STORYBOARD_SCENE_COUNT, duration: VEO_STORYBOARD_DURATION }
    : { count: DEFAULT_STORYBOARD_SCENE_COUNT, duration: 5 }
}

function normalizeVeoAspectRatio(value) {
  return value === '16:9' || value === '9:16' ? value : '9:16'
}

function sanitizeStoryboardPromptText(text) {
  const replacements = {
    不出现主播: '',
    禁止主播: '',
    无人物主播: '',
    主播: '产品实测动作',
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
    String(text || ''),
  ).replace(/\s+/g, ' ').trim()
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
  return {
    id: scene.id || `scene_${Date.now()}_${index}`,
    title: scene.title || `分镜 ${index + 1}`,
    selling_point: scene.selling_point || scene.sellingPoint || '',
    hook: scene.hook || '',
    image_prompt: sanitizeStoryboardPromptText(scene.image_prompt || scene.imagePrompt || ''),
    video_prompt: sanitizeStoryboardPromptText(scene.video_prompt || scene.videoPrompt || ''),
    shot_notes: scene.shot_notes || scene.shotNotes || '',
    storyboard_image_url: scene.storyboard_image_url || scene.storyboardImageUrl || '',
    video_url: scene.video_url || scene.videoUrl || '',
    status: scene.status || 'draft',
    error: scene.error || '',
    taskId: scene.taskId || '',
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
  const storyboardDefaults = storyboardDefaultsForVideoModel(videoModel)
  return {
    ...fallback,
    product: normalizeProductDraft(rawDraft.product),
    languageModel: typeof rawDraft.languageModel === 'string' ? rawDraft.languageModel : fallback.languageModel,
    imageModel: typeof rawDraft.imageModel === 'string' ? rawDraft.imageModel : fallback.imageModel,
    videoModel,
    aspectRatio: ASPECT_OPTIONS.includes(rawDraft.aspectRatio) ? rawDraft.aspectRatio : fallback.aspectRatio,
    duration: isVeoModel(videoModel)
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
    storyboardReferences: Array.isArray(rawDraft.storyboardReferences)
      ? rawDraft.storyboardReferences.map(normalizeMediaItem).filter(Boolean)
      : [],
    scenes: Array.isArray(rawDraft.scenes)
      ? rawDraft.scenes.map((scene, index) => normalizeScene(scene || {}, index))
      : [],
    batchResult: rawDraft.batchResult && typeof rawDraft.batchResult === 'object' ? rawDraft.batchResult : null,
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
  try {
    window.localStorage.setItem(
      WORKBENCH_DRAFT_STORAGE_KEY,
      JSON.stringify({
        ...draft,
        updatedAt: Date.now(),
      }),
    )
  } catch {
    // Ignore storage quota and private-mode failures; the page can still be used normally.
  }
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
  const [aspectRatio, setAspectRatio] = useState(() => initialDraft.aspectRatio)
  const [duration, setDuration] = useState(() => initialDraft.duration)
  const [variantCount, setVariantCount] = useState(() => Math.max(storyboardDefaultsForVideoModel(initialDraft.videoModel).count, initialDraft.variantCount))
  const [liveVideo, setLiveVideo] = useState(() => initialDraft.liveVideo)
  const [transcript, setTranscript] = useState(() => initialDraft.transcript)
  const [manualSellingPoints, setManualSellingPoints] = useState(() => initialDraft.manualSellingPoints)
  const [sellingPoints, setSellingPoints] = useState(() => initialDraft.sellingPoints)
  const [storyboardReferences, setStoryboardReferences] = useState(() => initialDraft.storyboardReferences)
  const [scenes, setScenes] = useState(() => initialDraft.scenes)
  const [batchResult, setBatchResult] = useState(() => initialDraft.batchResult)
  const [notice, setNotice] = useState(null)
  const [loadingTasks, setLoadingTasks] = useState({})

  const productPayload = useMemo(() => buildProductPayload(product), [product])
  const storyboardDefaults = useMemo(() => storyboardDefaultsForVideoModel(videoModel), [videoModel])
  const veoStoryboardMode = isVeoModel(videoModel)
  const previousVeoStoryboardModeRef = useRef(veoStoryboardMode)
  const storyboardRegenerateIndexRef = useRef(0)

  const { registerTaskPolling } = useGameTaskPolling({
    intervalMs: 6000,
    hiddenIntervalMs: 30000,
    onPollingError: () => setNotice({ type: 'warning', text: '视频任务状态轮询失败，请稍后刷新状态。' }),
  })

  const updateProduct = (key, value) => {
    setProduct(prev => ({ ...prev, [key]: value }))
  }

  const updateScene = useCallback((sceneId, patch) => {
    setScenes(prev => prev.map(scene => (scene.id === sceneId ? { ...scene, ...patch } : scene)))
  }, [])

  const updateSellingPoint = useCallback((index, patch) => {
    setSellingPoints(prev => prev.map((point, itemIndex) => (
      itemIndex === index ? { ...point, ...patch } : point
    )))
  }, [])

  const removeSellingPoint = useCallback((index) => {
    setSellingPoints(prev => prev.filter((_, itemIndex) => itemIndex !== index))
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

  const handleClearDraft = useCallback(() => {
    const emptyDraft = createDefaultDraft()
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(WORKBENCH_DRAFT_STORAGE_KEY)
      } catch {
        // Ignore storage failures.
      }
    }
    setProduct(emptyDraft.product)
    setLanguageModel(emptyDraft.languageModel)
    setImageModel(emptyDraft.imageModel)
    setVideoModel(emptyDraft.videoModel)
    setAspectRatio(emptyDraft.aspectRatio)
    setDuration(emptyDraft.duration)
    setVariantCount(emptyDraft.variantCount)
    setLiveVideo(emptyDraft.liveVideo)
    setTranscript(emptyDraft.transcript)
    setManualSellingPoints(emptyDraft.manualSellingPoints)
    setSellingPoints(emptyDraft.sellingPoints)
    setStoryboardReferences(emptyDraft.storyboardReferences)
    setScenes(emptyDraft.scenes)
    setBatchResult(emptyDraft.batchResult)
    setLoadingTasks({})
    setNotice({ type: 'success', text: '本地草稿已清空。' })
  }, [])

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
    saveWorkbenchDraft({
      product,
      languageModel,
      imageModel,
      videoModel,
      aspectRatio,
      duration,
      variantCount,
      liveVideo,
      transcript,
      manualSellingPoints,
      sellingPoints,
      storyboardReferences,
      scenes,
      batchResult,
    })
  }, [
    aspectRatio,
    batchResult,
    duration,
    imageModel,
    languageModel,
    liveVideo,
    manualSellingPoints,
    product,
    scenes,
    sellingPoints,
    storyboardReferences,
    transcript,
    variantCount,
    videoModel,
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
        provider: plan.provider || 'jimeng',
        model: plan.image_model || 'image2',
        aspect_ratio: '16:9',
        asset_type: 'product_detail_sheet',
        reference_urls: plan.reference_urls || product.imageUrls.map(item => item.url).slice(0, 8),
        prompt_optimize_mode: 'standard',
        image_quality: '2K',
        output_format: 'png',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回产品详情表图片地址')
      setProduct(prev => ({
        ...prev,
        detailSheetUrl: imageUrl,
        detailSheetPrompt: plan.prompt || '',
      }))
      setNotice({ type: 'success', text: '产品完整形态详情表已生成，后续分镜和视频会优先参考这张图。' })
    } catch (error) {
      setNotice({ type: 'error', text: `产品完整形态还原失败：${displayError(error)}` })
    } finally {
      finishLoading('product-detail-sheet')
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
      const storyboardDuration = veoMode ? VEO_STORYBOARD_DURATION : duration
      const storyboardCount = veoMode
        ? VEO_STORYBOARD_SCENE_COUNT
        : Math.max(DEFAULT_STORYBOARD_SCENE_COUNT, variantCount)
      storyboardRegenerateIndexRef.current += 1
      const regenerateIndex = storyboardRegenerateIndexRef.current
      const creativeSeed = `${Date.now()}-${regenerateIndex}-${Math.random().toString(36).slice(2, 10)}`
      const result = await api.post('/api/batch-video/storyboard-plan', {
        product: productPayload,
        selling_points: sellingPoints,
        storyboard_reference_urls: storyboardReferences.map(item => item.url),
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

  async function handleStoryboardUpload(sceneId, files) {
    const taskKey = `storyboard-upload-${sceneId}`
    startLoading(taskKey)
    setNotice(null)
    try {
      const uploaded = await uploadFiles(files, 'image/')
      if (!uploaded.length) return
      updateScene(sceneId, {
        storyboard_image_url: uploaded[0].url,
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
    const productReferences = product.detailSheetUrl
      ? [product.detailSheetUrl, ...product.imageUrls.map(item => item.url)]
      : product.imageUrls.map(item => item.url)
    const sceneReferences = storyboardReferences.map(item => item.url)
    if (!productReferences.length) {
      setNotice({ type: 'warning', text: '请先上传产品参考图，分镜图会参考上方产品图生成。' })
      return
    }
    const taskKey = `image-${scene.id}`
    startLoading(taskKey)
    updateScene(scene.id, { status: 'image_generating', error: '' })
    try {
      const provider = providerForModel(imageModel, imageModels, 'jimeng')
      const referencePrompt = [
        '【参考】@产品参考图 使用上方上传的产品图片作为产品外观参考，保持同一个产品的轮廓、颜色、材质、结构、鞋面/鞋底/扣具/纹理等关键细节。',
        sceneReferences.length ? '【分镜参考】@分镜参考图 用于参考构图、场景、光线、机位、动作节奏和广告质感；不要照搬其中无关产品。' : '',
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
        reference_urls: [...productReferences, ...sceneReferences].slice(0, 8),
        prompt_optimize_mode: 'standard',
      })
      const imageUrl = readMediaUrl(result)
      if (!imageUrl) throw new Error('图片模型未返回图片地址')
      updateScene(scene.id, {
        storyboard_image_url: imageUrl,
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
    if (isVeoModel(videoModel) && !scene.storyboard_image_url) {
      setNotice({ type: 'warning', text: '请先生成或上传分镜图，Veo 视频会参考分镜图和产品图生成。' })
      return
    }
    const taskKey = `video-${scene.id}`
    startLoading(taskKey)
    updateScene(scene.id, { status: 'video_generating', error: '', taskId: '' })
    try {
      const provider = providerForModel(videoModel, videoModels, 'jimeng')
      const productReferences = product.detailSheetUrl
        ? [product.detailSheetUrl, ...product.imageUrls.map(item => item.url)]
        : product.imageUrls.map(item => item.url)
      const sceneReferences = storyboardReferences.map(item => item.url)
      const refImages = scene.storyboard_image_url
        ? [scene.storyboard_image_url]
        : productReferences.slice(0, 1)
      const referenceVideoPrompt = [
        '【参考】@图片1 作为本分镜首帧/构图参考；@产品参考图 使用上方上传的产品图片作为产品外观参考，保持同一个产品的轮廓、颜色、材质、结构、鞋面/鞋底/扣具/纹理等关键细节。',
        sceneReferences.length ? '【分镜参考】已上传额外分镜参考图，可参考其构图、场景、光线、机位、动作节奏和广告质感；产品外观仍以产品参考图为准。' : '',
        '不要改变产品品类，不要自行改款。',
        sanitizeStoryboardPromptText(scene.video_prompt),
      ].filter(Boolean).join(' ')
      const firstFrameOnly = videoModel === 'happyhorse-1.0-i2v' || videoModel.startsWith('vidu')
      const referenceImageMode = isVeoModel(videoModel)
      const requestDuration = referenceImageMode ? 8 : duration
      const requestAspectRatio = referenceImageMode ? normalizeVeoAspectRatio(aspectRatio) : aspectRatio
      const body = {
        project_id: '',
        prompt: referenceVideoPrompt,
        provider,
        model: videoModel,
        duration: requestDuration,
        aspect_ratio: requestAspectRatio,
        resolution: '720p',
        image_url: firstFrameOnly || referenceImageMode ? (refImages[0] || '') : '',
        character_refs: [],
        scene_refs: firstFrameOnly || referenceImageMode ? [] : refImages,
        reference_video_url: '',
        advanced_reference_videos: [],
      }
      const result = await api.post('/api/game/generate_video', body)
      const videoUrl = readMediaUrl(result)
      if (videoUrl) {
        updateScene(scene.id, { status: 'completed', video_url: videoUrl, taskId: '', error: '' })
      } else if (result.task_id) {
        updateScene(scene.id, { status: 'processing', taskId: result.task_id, error: '' })
        registerTaskPolling(result.task_id, updates => {
          updateScene(scene.id, {
            status: updates.status || 'processing',
            video_url: updates.videoUrl || updates.video_url || '',
            error: updates.error || '',
            taskId: updates.taskId ?? result.task_id,
          })
        })
      } else {
        updateScene(scene.id, { status: 'processing', error: '', taskId: '' })
      }
    } catch (error) {
      updateScene(scene.id, { status: 'failed', error: displayError(error), taskId: '' })
      setNotice({ type: 'error', text: `视频生成失败：${displayError(error)}` })
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
      })
      setBatchResult(result)
      setNotice({ type: 'success', text: result.message || '批量任务已整理完成。' })
    } catch (error) {
      setNotice({ type: 'error', text: `批量任务整理失败：${displayError(error)}` })
    } finally {
      finishLoading('submit')
    }
  }

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
                  <img src={image.url} alt={image.name || `产品图 ${index + 1}`} />
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
                <span>根据参考图生成正视图、侧视图、俯视图、仰视图和细节特写</span>
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
                <img src={product.detailSheetUrl} alt="产品完整形态详情表" />
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

      <section className="batch-video-panel storyboard-panel">
        <div className="batch-video-panel-title">
          <ListChecks size={18} />
          <h2>场景与分镜</h2>
        </div>
        <div className="batch-video-toolbar">
          <label className="batch-video-field compact-field">
            <span>画幅</span>
            <select value={aspectRatio} onChange={event => setAspectRatio(event.target.value)}>
              {ASPECT_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="batch-video-field compact-field">
            <span>时长</span>
            <select
              value={duration}
              onChange={event => setDuration(Number(event.target.value))}
              disabled={veoStoryboardMode}
            >
              {DURATION_OPTIONS.map(option => <option key={option} value={option}>{option} 秒</option>)}
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
        </div>

        <div className="batch-video-storyboard-reference-panel">
          <div className="batch-video-storyboard-reference-head">
            <div>
              <strong>分镜参考图</strong>
              <span>用于参考构图、场景、光线、机位和广告质感，产品外观仍以上方产品图为准</span>
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
              {isLoading('storyboard-references') ? '上传中...' : '上传参考图'}
            </label>
          </div>
          {storyboardReferences.length > 0 && (
            <div className="batch-video-thumb-grid storyboard-reference-grid">
              {storyboardReferences.map((image, index) => (
                <div className="batch-video-thumb" key={`${image.url}-${index}`}>
                  <img src={image.url} alt={image.name || `分镜参考图 ${index + 1}`} />
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
          ) : scenes.map((scene, index) => (
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
                  onClick={() => setScenes(prev => prev.filter(item => item.id !== scene.id))}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="batch-video-scene-body">
                <div className="batch-video-preview">
                  {scene.storyboard_image_url ? (
                    <img src={scene.storyboard_image_url} alt={scene.title} />
                  ) : (
                    <div className="batch-video-preview-empty">
                      <ImageIcon size={24} />
                      <span>分镜图</span>
                    </div>
                  )}
                  {scene.video_url && (
                    <video src={scene.video_url} controls />
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
                    <span>视频提示词</span>
                    <textarea
                      value={scene.video_prompt}
                      onChange={event => updateScene(scene.id, { video_prompt: event.target.value })}
                      rows={4}
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
              {scene.error && <div className="batch-video-scene-error">{scene.error}</div>}
              {scene.taskId && <div className="batch-video-task-id">任务 ID：{scene.taskId}</div>}
              <div className="batch-video-scene-actions">
                <label className="batch-video-button ghost file-button">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={event => {
                      void handleStoryboardUpload(scene.id, event.target.files)
                      event.target.value = ''
                    }}
                  />
                  <Upload size={15} />
                  上传分镜图
                </label>
                <button
                  type="button"
                  className="batch-video-button ghost"
                  onClick={() => handleGenerateStoryboardImage(scene)}
                  disabled={isLoading(`image-${scene.id}`)}
                >
                  <ImageIcon size={15} />
                  {isLoading(`image-${scene.id}`) ? '生成中' : '生成分镜图'}
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
              </div>
            </article>
          ))}
        </div>
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
