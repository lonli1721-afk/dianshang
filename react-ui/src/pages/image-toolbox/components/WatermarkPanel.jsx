import { ChevronDown, ChevronUp, Layers, Loader2, Plus, Settings2, Sparkles, Stamp, Trash2, UsersRound, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  DEFAULT_CANDIDATE_BATCH_SIZE,
  FRIEND_CIRCLE_NINE_GRID_STYLE,
  MAX_IMAGE_COUNT,
  NINE_IMAGE_SOURCE_MODES,
  PAID_FEATURE_NOTICE,
  REVERSE_MODELS,
  STYLE_LOCK_OPTIONS,
} from '../constants'
import {
  createEmptyImageToolSlots,
  createImageToolWorkspace,
  displayError,
  loadImageToolWorkspace,
  normalizeImageToolSlotGroups,
  normalizeWatermarkSettings,
  noticeToneFromMessage,
  persistImageToolWorkspace,
} from '../helpers'
import { generateNineImages, generateRoleImages, listWatermarkFonts, splitGridImage, suggestRoleItems, uploadWatermarkFont, watermarkImages } from '../imageToolboxApi'
import { CandidateImagePicker } from './CandidateImagePicker'
import { Field } from './Field'
import { ImageGrid } from './ImageGrid'
import { PanelNotice } from './PanelNotice'
import { PromptAssistBox } from './PromptAssistBox'
import { ResultGrid } from './ResultGrid'
import { TaskQueuePanel } from './TaskQueuePanel'
import { UploadTile } from './UploadTile'
import { WatermarkControls } from './WatermarkControls'

const DEFAULT_STYLE_LOCK_OPTIONS = STYLE_LOCK_OPTIONS.map(item => item.id)
const DEFAULT_ROLE_ITEMS = ['番茄锅', '肥牛卷', '虾滑', '鱼丸', '金针菇', '午餐肉', '毛肚', '豆皮', '青菜']

const inferRoleSuggestionTopic = (value = '') => {
  const raw = String(value || '').trim()
  if (!raw) return ''
  return raw
    .replace(/同风格|九图|角色|主体|物品|素材|生成|小游戏|游戏|一组|一套/g, '')
    .replace(/[，,。；;：:\s]+/g, '')
    .trim()
}

const defaultGenerateModelForProvider = (provider) => (
  provider === 'gemini_image'
    ? 'gemini-3.1-flash-image-preview'
    : provider === 'openai_image'
      ? 'gpt-image-2'
      : 'seedream-4.5'
)

const PROGRESSIVE_IMAGE_CONCURRENCY = 3

async function runWithConcurrency(items, concurrency, worker) {
  let cursor = 0
  const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor
      cursor += 1
      await worker(items[index], index)
    }
  })
  await Promise.all(runners)
}

const emptySlots = () => createEmptyImageToolSlots()

const normalizeSlots = (slots) => Array.from({ length: MAX_IMAGE_COUNT }, (_, index) => slots?.[index]?.url ? slots[index] : null)

const flattenBatches = (batches) => batches.flatMap(batch => batch.images || [])

const removeUrlFromSlots = (slots, url) => normalizeSlots(slots).map(item => item?.url === url ? null : item)

const removeUrlFromSlotGroups = (slotGroups, url) => Object.fromEntries(
  Object.entries(slotGroups).map(([key, slots]) => [key, removeUrlFromSlots(slots, url)]),
)

const removeRefsFromSlotGroups = (slotGroups, refs) => Object.fromEntries(
  Object.entries(slotGroups).map(([key, slots]) => [
    key,
    normalizeSlots(slots).map(image => (
      image && (refs.urls.has(image.url) || refs.batchIds.has(image.batch_id)) ? null : image
    )),
  ]),
)

const buildSplitBatch = (images, sourceImage, batchNumber) => {
  const id = `split_${Date.now()}_${Math.random().toString(16).slice(2)}`
  const label = `第 ${batchNumber} 批`
  return {
    id,
    label,
    source_url: sourceImage?.url || '',
    images: (images || []).map((image, index) => ({
      ...image,
      batch_id: image.batch_id || id,
      batch_label: label,
      pool_index: index + 1,
    })),
    created_at: Date.now(),
  }
}

const buildCandidateBatch = (data, batchNumber, fallbackSize, labelPrefix = '第', sourceTaskId = '') => {
  const batchId = data.batch_id || `batch_${Date.now()}_${batchNumber}`
  const label = labelPrefix === '角色' ? `角色九图 ${batchNumber}` : `第 ${batchNumber} 批`
  const images = (data.images || []).map((item, index) => ({
    ...item,
    batch_id: item.batch_id || batchId,
    batch_label: label,
    pool_index: index + 1,
  }))
  return {
    id: batchId,
    label,
    images,
    failures: data.failures || [],
    requested_count: data.requested_count || data.batch_size || fallbackSize,
    provider: data.provider,
    model: data.model,
    style_anchor_url: data.style_anchor_url || '',
    style_lock: data.style_lock || 'strict',
    variation_policy: data.variation_policy || 'subject_only',
    task_id: sourceTaskId,
    created_at: Date.now(),
  }
}

const TERMINAL_TASK_STATUSES = new Set(['completed', 'failed', 'canceled'])

const isGeneratedWorkspaceImage = (image) => Boolean(image?.batch_id || image?.batch_label || image?.pool_index)

const collectTaskArtifactRefs = (taskItems = []) => {
  const taskIds = new Set()
  const batchIds = new Set()
  const urls = new Set()

  for (const task of taskItems) {
    if (!task) continue
    const taskId = task.task_id || task.id
    if (taskId) taskIds.add(taskId)
    const payload = task.result_payload || {}
    if (payload.batch_id) batchIds.add(payload.batch_id)
    if (payload.image_url) urls.add(payload.image_url)
    if (payload.grid?.url) urls.add(payload.grid.url)
    for (const image of payload.images || []) {
      if (image?.url) urls.add(image.url)
      if (image?.batch_id) batchIds.add(image.batch_id)
    }
  }

  return { taskIds, batchIds, urls }
}

export function WatermarkPanel({
  uploadImages,
  notify,
  jimengModels = [],
  geminiModels = [],
  openaiModels = [],
  modelsLoaded = true,
  tasks = [],
  submitTask,
  taskNotice = null,
  cancelTask,
  deleteTask,
  clearFinishedTasks,
  refreshTasks,
  locateRequest = null,
  onLocateTask,
}) {
  const [workspace, setWorkspace] = useState(() => loadImageToolWorkspace())
  const [sourceMode, setSourceMode] = useState('upload')
  const [generateTheme, setGenerateTheme] = useState(() => workspace.generateTheme || '户外保温杯商品图')
  const [generateStyle, setGenerateStyle] = useState(() => workspace.generateStyle || FRIEND_CIRCLE_NINE_GRID_STYLE)
  const [roleItems, setRoleItems] = useState(DEFAULT_ROLE_ITEMS)
  const [roleSuggestTopic, setRoleSuggestTopic] = useState(() => inferRoleSuggestionTopic(workspace.generateTheme || '甜品'))
  const [roleSuggestType, setRoleSuggestType] = useState('object')
  const [roleSuggestModel, setRoleSuggestModel] = useState('gemini-2.5-flash')
  const [roleSuggesting, setRoleSuggesting] = useState(false)
  const [generateProvider, setGenerateProvider] = useState('jimeng')
  const [generateModel, setGenerateModel] = useState('seedream-4.5')
  const [batchSize, setBatchSize] = useState(DEFAULT_CANDIDATE_BATCH_SIZE)
  const [styleLock, setStyleLock] = useState(() => workspace.styleLock || 'strict')
  const [styleLockOptions, setStyleLockOptions] = useState(() => (
    Array.isArray(workspace.styleLockOptions) && workspace.styleLockOptions.length
      ? workspace.styleLockOptions
    : DEFAULT_STYLE_LOCK_OPTIONS
  ))
  const [variationPolicy, setVariationPolicy] = useState(() => workspace.variationPolicy || 'subject_only')
  const initialWatermarkSettings = normalizeWatermarkSettings(workspace.watermarkSettings)
  const [text, setText] = useState(initialWatermarkSettings.text)
  const [position, setPosition] = useState(initialWatermarkSettings.position)
  const [fontStyle, setFontStyle] = useState(initialWatermarkSettings.fontStyle)
  const [fontOptions, setFontOptions] = useState([])
  const [selectedFontId, setSelectedFontId] = useState(initialWatermarkSettings.selectedFontId)
  const [fontUrl, setFontUrl] = useState(initialWatermarkSettings.fontUrl)
  const [fontName, setFontName] = useState(initialWatermarkSettings.fontName)
  const [color, setColor] = useState(initialWatermarkSettings.color)
  const [opacity, setOpacity] = useState(initialWatermarkSettings.opacity)
  const [strokeColor, setStrokeColor] = useState(initialWatermarkSettings.strokeColor)
  const [outputMode, setOutputMode] = useState(initialWatermarkSettings.outputMode)
  const [loading, setLoading] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [progressTasks, setProgressTasks] = useState([])
  const [fontUploading, setFontUploading] = useState(false)
  const [panelNotice, setPanelNotice] = useState(null)
  const [actionNotice, setActionNotice] = useState(null)
  const [drawerSection, setDrawerSection] = useState(null)
  const [highlightedTaskId, setHighlightedTaskId] = useState('')
  const [highlightedBatchId, setHighlightedBatchId] = useState('')
  const [expandedSplitBatchIds, setExpandedSplitBatchIds] = useState(new Set())
  const appliedTaskIdsRef = useRef(new Set(workspace.completedTaskIds || []))

  const uploadedImages = workspace.uploadedImages || []
  const splitSourceImage = workspace.splitSourceImage || []
  const splitBatches = workspace.splitBatches || []
  const splitImages = splitBatches.flatMap(batch => batch.images || [])
  const candidateBatches = workspace.candidateBatches || []
  const slotGroups = normalizeImageToolSlotGroups(workspace.slotGroups, workspace.selectedSlots)
  const selectedSlots = normalizeSlots(slotGroups[sourceMode])
  const styleAnchorImage = workspace.styleAnchorImage
  const finalResult = workspace.finalResult || { images: [], grid: null }
  const savedWatermarkSettings = normalizeWatermarkSettings(workspace.watermarkSettings)
  const draftWatermarkSettings = normalizeWatermarkSettings({
    text,
    position,
    fontStyle,
    selectedFontId,
    fontUrl,
    fontName,
    color,
    opacity,
    strokeColor,
    outputMode,
  })

  const generateProviderModels = generateProvider === 'gemini_image'
    ? geminiModels
    : generateProvider === 'openai_image'
      ? openaiModels
      : jimengModels
  const generateProviderLabel = generateProvider === 'gemini_image' ? 'Gemini 图片' : '即梦 / Seedream'
  const resolvedGenerateProviderLabel = generateProvider === 'openai_image' ? 'OpenAI Image' : generateProviderLabel
  const generateProviderReady = generateProviderModels.length > 0
  const selectedSlotImages = useMemo(() => selectedSlots.filter(Boolean), [selectedSlots])
  const selectedSlotUrls = useMemo(() => selectedSlotImages.map(item => item.url), [selectedSlotImages])
  const filledRoleCount = useMemo(() => roleItems.filter(item => item.trim()).length, [roleItems])
  const preparedCount = selectedSlotImages.length
  const getFinishDisabledReason = (settings = savedWatermarkSettings) => !preparedCount
    ? '请先把素材放入槽位。'
    : !settings.text.trim()
      ? '请先填写水印文字。'
      : settings.outputMode !== 'separate' && preparedCount !== MAX_IMAGE_COUNT
        ? `九宫格需要 9 张图片，当前已选 ${preparedCount} 张。`
        : ''
  const finishDisabledReason = getFinishDisabledReason(savedWatermarkSettings)
  const draftFinishDisabledReason = getFinishDisabledReason(draftWatermarkSettings)
  const canGenerateFinal = !finishDisabledReason
  const finalButtonLabel = savedWatermarkSettings.outputMode === 'separate'
    ? `生成 ${preparedCount} 张水印单图`
    : savedWatermarkSettings.outputMode === 'grid'
      ? '用 9 槽生成 1 张 3x3 九宫格'
      : preparedCount === MAX_IMAGE_COUNT
        ? '用 9 槽生成 9 张单图 + 1 张九宫格'
        : '用已选素材生成成品'
  const loadingFinalLabel = savedWatermarkSettings.outputMode === 'separate'
    ? `正在生成 ${preparedCount} 张水印单图...`
    : '正在生成水印成品...'

  const showPanelNotice = useCallback((message, tone, target = '') => {
    if (!message) {
      if (target) {
        setActionNotice(prev => prev?.target === target ? null : prev)
        return
      }
      setPanelNotice(null)
      return
    }
    const resolvedTone = tone || noticeToneFromMessage(message)
    if (target) {
      setActionNotice({ target, message, tone: resolvedTone })
    } else {
      setPanelNotice({ message, tone: resolvedTone })
    }
    notify?.({ scope: 'toast', message, tone: resolvedTone })
  }, [notify])

  const renderActionNotice = (target) => (
    <PanelNotice notice={actionNotice?.target === target ? actionNotice : null} className="image-tool-action-notice" />
  )

  const upsertProgressTask = useCallback((task) => {
    setProgressTasks(prev => {
      const id = task.task_id || task.id
      if (!id) return prev
      const next = prev.filter(item => item.task_id !== id)
      return [{ ...task, task_id: id }, ...next].slice(0, 20)
    })
  }, [])

  const updateProgressTask = useCallback((taskId, patch) => {
    setProgressTasks(prev => prev.map(task => (
      task.task_id === taskId ? { ...task, ...patch, updated_at: new Date().toISOString() } : task
    )))
  }, [])

  const removeProgressTask = useCallback(async (taskId) => {
    setProgressTasks(prev => prev.filter(task => task.task_id !== taskId))
  }, [])

  const clearFinishedProgressTasks = useCallback(async () => {
    setProgressTasks(prev => prev.filter(task => task.status === 'queued' || task.status === 'running'))
  }, [])

  const panelUploadImages = useCallback((files, options, target = 'upload') => (
    uploadImages(files, {
      ...options,
      setNotice: (message) => showPanelNotice(message, undefined, target),
    })
  ), [showPanelNotice, uploadImages])

  const updateWorkspace = useCallback((updater) => {
    setWorkspace(prev => {
      const next = typeof updater === 'function' ? updater(prev) : { ...prev, ...updater }
      const selectedSlots = normalizeSlots(next.selectedSlots)
      return {
        ...createImageToolWorkspace(),
        ...next,
        splitBatches: Array.isArray(next.splitBatches) ? next.splitBatches : [],
        selectedSlots,
        slotGroups: normalizeImageToolSlotGroups(next.slotGroups, selectedSlots),
        watermarkSettings: normalizeWatermarkSettings(next.watermarkSettings),
      }
    })
  }, [])

  useEffect(() => {
    persistImageToolWorkspace(workspace)
  }, [workspace])

  useEffect(() => {
    updateWorkspace(prev => ({ ...prev, generateTheme, generateStyle }))
  }, [generateTheme, generateStyle, updateWorkspace])

  useEffect(() => {
    updateWorkspace(prev => ({
      ...prev,
      styleLock,
      styleLockOptions,
      variationPolicy,
    }))
  }, [styleLock, styleLockOptions, variationPolicy, updateWorkspace])

  useEffect(() => {
    const completed = tasks.filter(task => (
      task.status === 'completed'
      && ['generate_nine', 'generate_roles', 'watermark'].includes(task.type)
      && !appliedTaskIdsRef.current.has(task.task_id)
    ))
    if (!completed.length) return

    const generationTasks = completed.filter(task => ['generate_nine', 'generate_roles'].includes(task.type))
    const watermarkTasks = completed.filter(task => task.type === 'watermark')

    updateWorkspace(prev => {
      const nextCompletedIds = [...(prev.completedTaskIds || [])]
      const nextBatches = [...(prev.candidateBatches || [])]
      let nextFinalResult = prev.finalResult || { images: [], grid: null }
      let addedGenerationCount = 0
      let addedWatermarkCount = 0

      for (const task of completed) {
        const data = task.result_payload || {}
        if (task.type === 'watermark') {
          if (!(data.images || []).length && !data.grid) continue
          appliedTaskIdsRef.current.add(task.task_id)
          nextCompletedIds.push(task.task_id)
          nextFinalResult = {
            images: data.images || [],
            grid: data.grid || null,
            task_id: task.task_id,
          }
          addedWatermarkCount += 1
          continue
        }

        if (!(data.images || []).length && !(data.failures || []).length) continue
        appliedTaskIdsRef.current.add(task.task_id)
        nextCompletedIds.push(task.task_id)
        nextBatches.push(buildCandidateBatch(
          data,
          nextBatches.length + 1,
          data.requested_count || data.batch_size || DEFAULT_CANDIDATE_BATCH_SIZE,
          task.type === 'generate_roles' ? '角色' : '第',
          task.task_id,
        ))
        addedGenerationCount += 1
      }

      return {
        ...prev,
        candidateBatches: nextBatches,
        completedTaskIds: Array.from(new Set(nextCompletedIds)).slice(-120),
        finalResult: addedWatermarkCount ? nextFinalResult : addedGenerationCount ? { images: [], grid: null } : nextFinalResult,
      }
    })

    if (watermarkTasks.length) {
      showPanelNotice('已生成水印成品，结果已更新到右侧处理结果。', 'success', 'slots')
    }
    if (generationTasks.length) {
      showPanelNotice(`已接收 ${generationTasks.length} 个生成任务结果，素材池已更新。`, 'success')
    }
  }, [tasks, showPanelNotice, updateWorkspace])

  useEffect(() => {
    const task = locateRequest?.task
    if (!task || !['generate_nine', 'generate_roles', 'watermark'].includes(task.type)) return
    const taskId = task.task_id
    if (task.type === 'watermark') {
      const payload = task.result_payload || {}
      if (task.status !== 'completed' || (!(payload.images || []).length && !payload.grid)) {
        showPanelNotice('这个水印任务还没有可定位的结果。', 'warning', 'tasks')
        return
      }
      updateWorkspace(prev => ({
        ...prev,
        finalResult: { images: payload.images || [], grid: payload.grid || null, task_id: taskId },
      }))
      setHighlightedTaskId(taskId)
      setHighlightedBatchId('')
      showPanelNotice('已定位到该水印任务结果。', 'success', 'slots')
      const scrollTimer = window.setTimeout(() => {
        document.querySelector(`[data-watermark-result-task-id="${taskId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 80)
      const clearTimer = window.setTimeout(() => {
        setHighlightedTaskId('')
      }, 3200)
      return () => {
        window.clearTimeout(scrollTimer)
        window.clearTimeout(clearTimer)
      }
    }

    const batchId = task.result_payload?.batch_id || ''
    setSourceMode(task.type === 'generate_roles' ? 'generate_roles' : 'generate_set')
    setHighlightedTaskId(taskId)
    setHighlightedBatchId(batchId)
    showPanelNotice('已定位到该任务产出批次。', 'success', 'tasks')

    const selector = [
      taskId ? `[data-image-task-id="${taskId}"]` : '',
      batchId ? `[data-image-batch-id="${batchId}"]` : '',
    ].filter(Boolean).join(',')
    const scrollTimer = window.setTimeout(() => {
      if (selector) document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 80)
    const clearTimer = window.setTimeout(() => {
      setHighlightedTaskId('')
      setHighlightedBatchId('')
    }, 3200)
    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(clearTimer)
    }
  }, [locateRequest, showPanelNotice, updateWorkspace])

  useEffect(() => {
    let alive = true
    listWatermarkFonts('户外保温杯商品图')
      .then(data => {
        if (!alive) return
        const fonts = data.fonts || []
        setFontOptions(fonts)
        if (fonts.length) setSelectedFontId(prev => prev || fonts[0].id)
      })
      .catch(error => {
        if (alive) showPanelNotice(displayError(error), 'error')
      })
    return () => { alive = false }
  }, [showPanelNotice])

  useEffect(() => {
    const models = generateProvider === 'gemini_image'
      ? geminiModels
      : generateProvider === 'openai_image'
        ? openaiModels
        : jimengModels
    const fallbackModel = defaultGenerateModelForProvider(generateProvider)
    if (modelsLoaded && generateProvider === 'gemini_image' && !models.length && jimengModels.length) {
      setGenerateProvider('jimeng')
      setGenerateModel(jimengModels[0].id)
      return
    }
    if (models.length && !models.some(model => model.id === generateModel)) {
      const preferred = models.find(model => model.id === fallbackModel)
      setGenerateModel((preferred || models[0]).id)
    } else if (modelsLoaded && !models.length && generateModel !== fallbackModel) {
      setGenerateModel(fallbackModel)
    }
  }, [generateProvider, generateModel, jimengModels, geminiModels, openaiModels, modelsLoaded])

  const setFinalResult = (result) => updateWorkspace(prev => ({ ...prev, finalResult: result }))

  const handleSourceMode = (mode) => {
    if (!mode.enabled) {
      showPanelNotice(PAID_FEATURE_NOTICE, 'warning')
      return
    }
    setSourceMode(mode.id)
    showPanelNotice('')
  }

  const setStyleAnchor = (image) => {
    if (!image?.url) {
      updateWorkspace(prev => ({ ...prev, styleAnchorImage: null }))
      showPanelNotice('已移除风格样板图，后续生成不会再引用这张样板。', 'success')
      return
    }
    updateWorkspace(prev => ({ ...prev, styleAnchorImage: image }))
    showPanelNotice('已设为风格样板，后续批次会优先贴近这张图。', 'success')
  }

  const updateCurrentSlots = (slotUpdater) => {
    updateWorkspace(prev => {
      const groups = normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)
      const current = normalizeSlots(groups[sourceMode])
      const nextSlots = normalizeSlots(typeof slotUpdater === 'function' ? slotUpdater(current) : slotUpdater)
      return {
        ...prev,
        slotGroups: { ...groups, [sourceMode]: nextSlots },
        selectedSlots: nextSlots,
        finalResult: { images: [], grid: null },
      }
    })
  }

  const removeImageFromEverySlotGroup = (prev, url) => {
    const groups = normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)
    return removeUrlFromSlotGroups(groups, url)
  }

  const setUploadedImages = (images) => {
    updateWorkspace(prev => ({ ...prev, uploadedImages: images, finalResult: { images: [], grid: null } }))
  }

  const setSplitSourceImage = (images) => {
    updateWorkspace(prev => ({ ...prev, splitSourceImage: images, finalResult: { images: [], grid: null } }))
  }

  const addSplitBatch = (images) => {
    if (!images?.length) return
    const batch = buildSplitBatch(images, splitSourceImage[0], splitBatches.length + 1)
    setExpandedSplitBatchIds(new Set([batch.id]))
    updateWorkspace(prev => ({
      ...prev,
      splitImages: images,
      splitBatches: [...(prev.splitBatches || []), batch],
      finalResult: { images: [], grid: null },
    }))
  }

  const toggleSlotImage = (image) => {
    if (!image?.url) return
    const existing = selectedSlots.some(item => item?.url === image.url)
    if (!existing && selectedSlots.every(Boolean)) {
      showPanelNotice('9 个成片槽位已满，请先移出一张再添加。', 'warning', 'slots')
      return
    }
    updateCurrentSlots(currentSlots => {
      const nextSlots = normalizeSlots(currentSlots)
      const existingIndex = nextSlots.findIndex(item => item?.url === image.url)
      if (existingIndex >= 0) {
        nextSlots[existingIndex] = null
      } else {
        const emptyIndex = nextSlots.findIndex(item => !item)
        if (emptyIndex >= 0) nextSlots[emptyIndex] = image
      }
      return nextSlots
    })
  }

  const fillImagesToSlots = (images = []) => {
    let inserted = 0
    updateCurrentSlots(currentSlots => {
      const nextSlots = normalizeSlots(currentSlots)
      const existing = new Set(nextSlots.filter(Boolean).map(item => item.url))
      for (const image of images) {
        if (!image?.url || existing.has(image.url)) continue
        const emptyIndex = nextSlots.findIndex(item => !item)
        if (emptyIndex < 0) break
        nextSlots[emptyIndex] = image
        existing.add(image.url)
        inserted += 1
      }
      return nextSlots
    })
    showPanelNotice(inserted ? `已填入 ${inserted} 张素材。` : '没有可填入的空槽位。', inserted ? 'success' : 'warning', 'slots')
  }

  const clearSlot = (index) => {
    updateCurrentSlots(currentSlots => {
      const nextSlots = normalizeSlots(currentSlots)
      nextSlots[index] = null
      return nextSlots
    })
  }

  const moveSlot = (fromIndex, toIndex) => {
    updateCurrentSlots(currentSlots => {
      const nextSlots = normalizeSlots(currentSlots)
      const [item] = nextSlots.splice(fromIndex, 1)
      nextSlots.splice(toIndex, 0, item)
      return normalizeSlots(nextSlots)
    })
  }

  const clearSlots = () => {
    updateCurrentSlots(emptySlots())
  }

  const removeTaskArtifacts = useCallback((taskItems = []) => {
    const refs = collectTaskArtifactRefs(taskItems)
    if (!refs.taskIds.size && !refs.batchIds.size && !refs.urls.size) return 0

    let removed = 0
    updateWorkspace(prev => {
      const nextBatches = []
      for (const batch of prev.candidateBatches || []) {
        const images = batch.images || []
        const batchMatched = refs.taskIds.has(batch.task_id)
          || refs.taskIds.has(batch.source_task_id)
          || refs.batchIds.has(batch.id)
        if (batchMatched) {
          removed += images.length
          continue
        }

        const nextImages = images.filter(image => {
          const matched = refs.urls.has(image.url) || refs.batchIds.has(image.batch_id)
          if (matched) removed += 1
          return !matched
        })
        if (nextImages.length || (batch.failures || []).length) {
          nextBatches.push({ ...batch, images: nextImages })
        }
      }

      const nextSlotGroups = removeRefsFromSlotGroups(
        normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots),
        refs,
      )
      const styleAnchor = prev.styleAnchorImage
      const nextCompletedTaskIds = (prev.completedTaskIds || []).filter(taskId => !refs.taskIds.has(taskId))
      const finalResult = prev.finalResult || { images: [], grid: null }
      const finalImages = finalResult.images || []
      const finalGrid = finalResult.grid
      const finalMatches = [
        ...finalImages.filter(image => image?.url && refs.urls.has(image.url)),
        finalGrid?.url && refs.urls.has(finalGrid.url) ? finalGrid : null,
      ].filter(Boolean)
      if (finalMatches.length) removed += finalMatches.length
      refs.taskIds.forEach(taskId => appliedTaskIdsRef.current.delete(taskId))

      return {
        ...prev,
        candidateBatches: nextBatches,
        slotGroups: nextSlotGroups,
        selectedSlots: normalizeSlots(nextSlotGroups[sourceMode]),
        styleAnchorImage: styleAnchor && (refs.urls.has(styleAnchor.url) || refs.batchIds.has(styleAnchor.batch_id)) ? null : styleAnchor,
        completedTaskIds: nextCompletedTaskIds,
        finalResult: finalMatches.length ? { images: [], grid: null } : finalResult,
      }
    })
    return removed
  }, [sourceMode, updateWorkspace])

  const clearGeneratedWorkspaceArtifacts = useCallback(() => {
    let removed = 0
    updateWorkspace(prev => {
      const generatedUrls = new Set()
      for (const batch of prev.candidateBatches || []) {
        for (const image of batch.images || []) {
          if (image?.url) generatedUrls.add(image.url)
        }
      }
      const groups = normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)
      const nextSlotGroups = Object.fromEntries(Object.entries(groups).map(([key, slots]) => [key, normalizeSlots(slots).map(image => {
        const matched = image && (generatedUrls.has(image.url) || isGeneratedWorkspaceImage(image))
        if (matched) {
          if (image.url && !generatedUrls.has(image.url)) generatedUrls.add(image.url)
          return null
        }
        return image
      })]))
      removed = generatedUrls.size
      const styleAnchor = prev.styleAnchorImage
      const removeAnchor = styleAnchor && (generatedUrls.has(styleAnchor.url) || isGeneratedWorkspaceImage(styleAnchor))
      appliedTaskIdsRef.current.clear()

      return {
        ...prev,
        candidateBatches: [],
        slotGroups: nextSlotGroups,
        selectedSlots: normalizeSlots(nextSlotGroups[sourceMode]),
        styleAnchorImage: removeAnchor ? null : styleAnchor,
        completedTaskIds: [],
        finalResult: { images: [], grid: null },
      }
    })
    return removed
  }, [sourceMode, updateWorkspace])

  const handleDeleteTask = useCallback(async (taskId) => {
    const task = tasks.find(item => item.task_id === taskId)
    await deleteTask?.(taskId)
    const removed = removeTaskArtifacts(task ? [task] : [])
    showPanelNotice(
      removed ? `已删除任务，并移除 ${removed} 张关联图片。` : '已删除任务。',
      'success',
      'tasks',
    )
  }, [deleteTask, removeTaskArtifacts, showPanelNotice, tasks])

  const handleClearFinishedTasks = useCallback(async () => {
    const finishedTasks = tasks.filter(task => TERMINAL_TASK_STATUSES.has(task.status))
    await clearFinishedTasks?.()
    const removed = finishedTasks.length
      ? removeTaskArtifacts(finishedTasks)
      : clearGeneratedWorkspaceArtifacts()
    showPanelNotice(
      removed ? `已清理历史任务，并移除 ${removed} 张关联图片。` : '已清理历史任务。',
      'success',
      'tasks',
    )
  }, [clearFinishedTasks, clearGeneratedWorkspaceArtifacts, removeTaskArtifacts, showPanelNotice, tasks])

  const removeSourceImage = (key, index) => {
    updateWorkspace(prev => {
      const current = prev[key] || []
      const removed = current[index]
      const nextImages = current.filter((_, itemIndex) => itemIndex !== index)
      return {
        ...prev,
        [key]: nextImages,
        slotGroups: removed?.url ? removeImageFromEverySlotGroup(prev, removed.url) : normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots),
        selectedSlots: removed?.url ? removeUrlFromSlots(normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)[sourceMode], removed.url) : normalizeSlots(normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)[sourceMode]),
        styleAnchorImage: prev.styleAnchorImage?.url === removed?.url ? null : prev.styleAnchorImage,
        finalResult: { images: [], grid: null },
      }
    })
  }

  const removeCandidate = (url) => {
    updateWorkspace(prev => ({
      ...prev,
      candidateBatches: (prev.candidateBatches || [])
        .map(batch => ({ ...batch, images: (batch.images || []).filter(item => item.url !== url) }))
        .filter(batch => (batch.images || []).length || (batch.failures || []).length),
      slotGroups: removeImageFromEverySlotGroup(prev, url),
      selectedSlots: removeUrlFromSlots(normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)[sourceMode], url),
      styleAnchorImage: prev.styleAnchorImage?.url === url ? null : prev.styleAnchorImage,
      finalResult: { images: [], grid: null },
    }))
  }

  const removeSplitBatch = (batchId) => {
    const batch = splitBatches.find(item => item.id === batchId)
    const urls = new Set((batch?.images || []).map(image => image.url).filter(Boolean))
    updateWorkspace(prev => {
      const groups = normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)
      const nextSlotGroups = Object.fromEntries(Object.entries(groups).map(([key, slots]) => [
        key,
        normalizeSlots(slots).map(image => image && urls.has(image.url) ? null : image),
      ]))
      return {
        ...prev,
        splitBatches: (prev.splitBatches || []).filter(item => item.id !== batchId),
        splitImages: (prev.splitImages || []).filter(image => !urls.has(image.url)),
        slotGroups: nextSlotGroups,
        selectedSlots: normalizeSlots(nextSlotGroups[sourceMode]),
        styleAnchorImage: prev.styleAnchorImage?.url && urls.has(prev.styleAnchorImage.url) ? null : prev.styleAnchorImage,
        finalResult: { images: [], grid: null },
      }
    })
    setExpandedSplitBatchIds(prev => {
      const next = new Set(prev)
      next.delete(batchId)
      return next
    })
  }

  const removeSplitImage = (batchId, imageIndex) => {
    let removedUrl = ''
    updateWorkspace(prev => {
      const nextBatches = (prev.splitBatches || []).map(batch => {
        if (batch.id !== batchId) return batch
        const image = batch.images?.[imageIndex]
        removedUrl = image?.url || ''
        return { ...batch, images: (batch.images || []).filter((_, index) => index !== imageIndex) }
      }).filter(batch => (batch.images || []).length)
      const groups = removedUrl ? removeImageFromEverySlotGroup(prev, removedUrl) : normalizeImageToolSlotGroups(prev.slotGroups, prev.selectedSlots)
      return {
        ...prev,
        splitBatches: nextBatches,
        splitImages: (prev.splitImages || []).filter(image => image.url !== removedUrl),
        slotGroups: groups,
        selectedSlots: normalizeSlots(groups[sourceMode]),
        styleAnchorImage: prev.styleAnchorImage?.url === removedUrl ? null : prev.styleAnchorImage,
        finalResult: { images: [], grid: null },
      }
    })
  }

  const runSplitGrid = async () => {
    if (!splitSourceImage.length) {
      showPanelNotice('请先上传一张要切成九图的图片。', 'error', 'split')
      return
    }

    setSplitting(true)
    showPanelNotice('', undefined, 'split')
    try {
      const data = await splitGridImage({ image_url: splitSourceImage[0].url })
      addSplitBatch(data.images || [])
      showPanelNotice('已切出 9 张素材，可单独入槽、下载或加水印。', 'success', 'split')
    } catch (error) {
      showPanelNotice(displayError(error), 'error', 'split')
    } finally {
      setSplitting(false)
    }
  }

  const saveWatermarkSettings = (settings = draftWatermarkSettings, toneTarget = 'finish') => {
    const nextSettings = normalizeWatermarkSettings(settings)
    updateWorkspace(prev => ({ ...prev, watermarkSettings: nextSettings }))
    showPanelNotice('水印设置已保存，后续生成会沿用这套设置。', 'success', toneTarget)
    return nextSettings
  }

  const buildWatermarkPayload = (items, settings = savedWatermarkSettings) => {
    const resolvedSettings = normalizeWatermarkSettings(settings)
    const resolvedText = (resolvedSettings.text || '').trim()
    if (!items.length || !resolvedText) {
      throw new Error('请先选择素材并填写水印文字。')
    }

    return {
      image_urls: items.map(item => item.url),
      text: resolvedText,
      position: resolvedSettings.position,
      font_style: resolvedSettings.fontStyle,
      font_id: resolvedSettings.selectedFontId.startsWith('custom:') ? '' : resolvedSettings.selectedFontId,
      font_url: resolvedSettings.selectedFontId.startsWith('custom:') ? resolvedSettings.fontUrl : '',
      color: resolvedSettings.color,
      opacity: resolvedSettings.opacity,
      stroke_color: resolvedSettings.strokeColor,
      output_mode: resolvedSettings.outputMode,
    }
  }

  const watermarkPreparedImages = async (items, settings = savedWatermarkSettings) => {
    return await watermarkImages(buildWatermarkPayload(items, settings))
  }

  const getStyleLockPayload = () => ({
    style_anchor_url: styleLock === 'off' ? '' : styleAnchorImage?.url || '',
    style_lock: styleLock,
    style_lock_options: styleLock === 'off' ? [] : styleLockOptions,
    variation_policy: variationPolicy,
  })

  const createProgressiveBatch = (labelPrefix, requestedCount, requestPayload) => {
    const batchNumber = candidateBatches.length + 1
    const batchId = `${labelPrefix === '角色' ? 'roles' : 'batch'}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    const label = labelPrefix === '角色' ? `角色九图 ${batchNumber}` : `第 ${batchNumber} 批`
    const batch = {
      id: batchId,
      label,
      images: [],
      failures: [],
      requested_count: requestedCount,
      pending_count: requestedCount,
      provider: requestPayload.provider,
      model: requestPayload.model,
      style_anchor_url: requestPayload.style_anchor_url || '',
      style_lock: requestPayload.style_lock || 'strict',
      variation_policy: requestPayload.variation_policy || 'subject_only',
      request_payload: requestPayload,
      created_at: Date.now(),
    }
    updateWorkspace(prev => ({
      ...prev,
      candidateBatches: [...(prev.candidateBatches || []), batch],
      finalResult: { images: [], grid: null },
    }))
    return { batchId, label }
  }

  const updateProgressiveBatch = (batchId, updater) => {
    updateWorkspace(prev => ({
      ...prev,
      candidateBatches: (prev.candidateBatches || []).map(batch => (
        batch.id === batchId ? updater(batch) : batch
      )),
    }))
  }

  const appendGeneratedImage = (batchId, label, data, fallbackIndex) => {
    const incoming = (data.images || [data]).filter(item => item?.url)
    updateProgressiveBatch(batchId, batch => {
      const existingUrls = new Set((batch.images || []).map(item => item.url))
      const nextImages = [...(batch.images || [])]
      for (const image of incoming) {
        if (existingUrls.has(image.url)) continue
        nextImages.push({
          ...image,
          batch_id: batchId,
          batch_label: label,
          pool_index: image.index || fallbackIndex,
        })
      }
      return {
        ...batch,
        images: nextImages.sort((a, b) => (a.pool_index || 0) - (b.pool_index || 0)),
        failures: (batch.failures || []).filter(item => item.index !== fallbackIndex),
        pending_count: Math.max(0, (batch.pending_count || 0) - 1),
      }
    })
  }

  const appendGeneratedFailure = (batchId, failure) => {
    updateProgressiveBatch(batchId, batch => ({
      ...batch,
      failures: [
        ...(batch.failures || []).filter(item => item.index !== failure.index),
        failure,
      ].sort((a, b) => (a.index || 0) - (b.index || 0)),
      pending_count: Math.max(0, (batch.pending_count || 0) - 1),
    }))
  }

  const runGenerateCandidates = async () => {
    if (!generateTheme.trim()) {
      showPanelNotice('请先填写要生成的画面内容，比如“户外保温杯商品图”。', 'error', 'generate')
      return
    }
    if (!modelsLoaded) {
      showPanelNotice('生图模型还在加载，请稍后再试。', 'warning', 'generate')
      return
    }
    if (!generateProviderReady) {
      showPanelNotice(`${resolvedGenerateProviderLabel}还没有配置 API Key，请先到设置里配置，或切换生图平台。`, 'error', 'generate')
      return
    }

    setGenerating(true)
    showPanelNotice('', undefined, 'generate')
    try {
      const requestPayload = {
        theme: generateTheme,
        visual_style: generateStyle,
        provider: generateProvider,
        model: generateModel,
        aspect_ratio: '1:1',
        batch_size: 1,
        count: 1,
        total_count: batchSize,
        ...getStyleLockPayload(),
      }
      const { batchId, label } = createProgressiveBatch('第', batchSize, requestPayload)
      const progressTaskId = `local-generate-nine-${batchId}`
      upsertProgressTask({
        task_id: progressTaskId,
        type: 'generate_nine',
        status: 'running',
        provider: generateProvider,
        model: generateModel,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        result_payload: null,
      })
      showPanelNotice(`${label}开始生成：最多 ${PROGRESSIVE_IMAGE_CONCURRENCY} 张并发，完成一张会立即进入素材池。`, 'success', 'generate')
      let successCount = 0
      let failureCount = 0
      await runWithConcurrency(
        Array.from({ length: batchSize }, (_, index) => index + 1),
        PROGRESSIVE_IMAGE_CONCURRENCY,
        async (index) => {
          try {
            const data = await generateNineImages({ ...requestPayload, single_index: index })
            appendGeneratedImage(batchId, label, data, index)
            successCount += (data.images || []).length || 1
          } catch (error) {
            failureCount += 1
            appendGeneratedFailure(batchId, {
              index,
              prompt: '',
              error: displayError(error),
              provider: generateProvider,
              model: generateModel,
            })
          }
          updateProgressTask(progressTaskId, {
            error: failureCount ? `已失败 ${failureCount} 张，可在素材池单张重试。` : '',
          })
        },
      )
      updateProgressTask(progressTaskId, {
        status: successCount ? 'completed' : 'failed',
        error: successCount ? (failureCount ? `完成 ${successCount} 张，失败 ${failureCount} 张。` : '') : `全部失败，共 ${failureCount} 张。`,
        result_payload: { batch_id: batchId, images: Array.from({ length: successCount }), failures: Array.from({ length: failureCount }) },
      })
      showPanelNotice(`${label}生成完成，可从素材池挑 9 张放入槽位；失败的单张可单独重试。`, 'success', 'generate')
    } catch (error) {
      showPanelNotice(displayError(error), 'error', 'generate')
    } finally {
      setGenerating(false)
    }
  }

  const runGenerateRoles = async () => {
    const roles = roleItems.map(item => item.trim()).filter(Boolean)
    if (!generateTheme.trim()) {
      showPanelNotice('请先填写同风格角色九图主题。', 'error', 'generate_roles')
      return
    }
    if (roles.length !== MAX_IMAGE_COUNT) {
      showPanelNotice('同风格角色九图需要 9 个角色或物品名。', 'error', 'generate_roles')
      return
    }
    if (!modelsLoaded) {
      showPanelNotice('生图模型还在加载，请稍后再试。', 'warning', 'generate_roles')
      return
    }
    if (!generateProviderReady) {
      showPanelNotice(`${resolvedGenerateProviderLabel}还没有配置 API Key，请先到设置里配置，或切换生图平台。`, 'error', 'generate_roles')
      return
    }
    setGenerating(true)
    showPanelNotice('', undefined, 'generate_roles')
    try {
      const requestPayload = {
        theme: generateTheme,
        visual_style: generateStyle,
        roles: [],
        provider: generateProvider,
        model: generateModel,
        aspect_ratio: '1:1',
        total_count: MAX_IMAGE_COUNT,
        ...getStyleLockPayload(),
      }
      const { batchId, label } = createProgressiveBatch('角色', MAX_IMAGE_COUNT, { ...requestPayload, roles })
      const progressTaskId = `local-generate-roles-${batchId}`
      upsertProgressTask({
        task_id: progressTaskId,
        type: 'generate_roles',
        status: 'running',
        provider: generateProvider,
        model: generateModel,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        result_payload: null,
      })
      showPanelNotice(`${label}开始生成：最多 ${PROGRESSIVE_IMAGE_CONCURRENCY} 张并发，完成一张会立即进入素材池。`, 'success', 'generate_roles')
      let successCount = 0
      let failureCount = 0
      await runWithConcurrency(
        roles.map((role, index) => ({ role, index: index + 1 })),
        PROGRESSIVE_IMAGE_CONCURRENCY,
        async ({ role, index }) => {
          try {
            const data = await generateRoleImages({
              ...requestPayload,
              roles: [role],
              single_index: index,
            })
            appendGeneratedImage(batchId, label, data, index)
            successCount += (data.images || []).length || 1
          } catch (error) {
            failureCount += 1
            appendGeneratedFailure(batchId, {
              index,
              role,
              prompt: '',
              error: displayError(error),
              provider: generateProvider,
              model: generateModel,
            })
          }
          updateProgressTask(progressTaskId, {
            error: failureCount ? `已失败 ${failureCount} 张，可在素材池单张重试。` : '',
          })
        },
      )
      updateProgressTask(progressTaskId, {
        status: successCount ? 'completed' : 'failed',
        error: successCount ? (failureCount ? `完成 ${successCount} 张，失败 ${failureCount} 张。` : '') : `全部失败，共 ${failureCount} 张。`,
        result_payload: { batch_id: batchId, images: Array.from({ length: successCount }), failures: Array.from({ length: failureCount }) },
      })
      showPanelNotice(`${label}生成完成，失败的单张可单独重试。`, 'success', 'generate_roles')
    } catch (error) {
      showPanelNotice(displayError(error), 'error', 'generate_roles')
    } finally {
      setGenerating(false)
    }
  }

  const uploadFont = async (files) => {
    const file = files[0]
    if (!file) return

    setFontUploading(true)
    showPanelNotice('', undefined, 'finish')
    try {
      const data = await uploadWatermarkFont(file)
      setFontUrl(data.url)
      setFontName(file.name)
      const customId = `custom:${data.url}`
      setSelectedFontId(customId)
      setFontOptions(prev => [
        {
          id: customId,
          name: file.name.replace(/\.[^.]+$/, ''),
          source: '上传字体',
          preview_url: data.preview_url,
          font_url: data.url,
        },
        ...prev.filter(item => item.id !== customId),
      ])
      showPanelNotice(`已使用字体：${file.name}`, 'success', 'finish')
    } catch (error) {
      showPanelNotice(displayError(error), 'error', 'finish')
    } finally {
      setFontUploading(false)
    }
  }

  const runWatermark = async (settings = savedWatermarkSettings, target = 'final') => {
    const disabledReason = getFinishDisabledReason(settings)
    if (disabledReason) {
      showPanelNotice(disabledReason, 'error', target)
      return
    }

    setLoading(true)
    showPanelNotice('', undefined, target)
    try {
      const payload = buildWatermarkPayload(selectedSlotImages, settings)
      if (submitTask) {
        await submitTask('watermark', payload)
        setDrawerSection(null)
        showPanelNotice('水印任务已提交；可继续提交其他任务，完成后右侧会提示“已生成”。', 'success', 'slots')
        return
      }

      showPanelNotice(`${loadingFinalLabel} 请稍等。`, 'warning', 'finish')
      const data = await watermarkPreparedImages(selectedSlotImages, settings)
      const images = data.images || []
      const grid = data.grid || null
      setFinalResult({ images, grid })
      setDrawerSection(null)
      const doneText = settings.outputMode === 'separate'
        ? `已生成 ${images.length} 张水印单图，结果已更新到右侧处理结果。`
        : grid && images.length
          ? `已生成 ${images.length} 张水印单图和 1 张九宫格，结果已更新。`
          : grid
            ? '已生成 1 张九宫格水印图，结果已更新。'
            : `已生成 ${images.length} 张水印图，结果已更新。`
      showPanelNotice(doneText, 'success', 'slots')
    } catch (error) {
      showPanelNotice(displayError(error), 'error', target)
    } finally {
      setLoading(false)
    }
  }

  const retryGeneratedFailure = async (batch, failure) => {
    if (!batch?.request_payload || !failure?.index) {
      showPanelNotice('这条失败记录缺少重试参数，请重新生成一批。', 'warning')
      return
    }
    const label = batch.label || '当前批次'
    updateProgressiveBatch(batch.id, current => ({
      ...current,
      failures: (current.failures || []).filter(item => item.index !== failure.index),
      pending_count: (current.pending_count || 0) + 1,
    }))
    try {
      const payload = {
        ...batch.request_payload,
        count: 1,
        batch_size: 1,
        total_count: batch.request_payload.total_count || batch.requested_count || MAX_IMAGE_COUNT,
        single_index: failure.index,
      }
      const data = failure.role
        ? await generateRoleImages({ ...payload, roles: [failure.role] })
        : await generateNineImages(payload)
      appendGeneratedImage(batch.id, label, data, failure.index)
      showPanelNotice(`第 ${failure.index} 张已重试成功。`, 'success')
    } catch (error) {
      appendGeneratedFailure(batch.id, {
        ...failure,
        error: displayError(error),
      })
      showPanelNotice(`第 ${failure.index} 张重试失败：${displayError(error)}`, 'error')
    }
  }

  const visibleTasks = useMemo(() => {
    const seen = new Set()
    return [...progressTasks, ...tasks].filter(task => {
      const id = task.task_id || task.id
      if (!id || seen.has(id)) return false
      seen.add(id)
      return true
    })
  }, [progressTasks, tasks])

  const pickerProps = {
    batches: candidateBatches,
    selectedSlots,
    styleAnchorImage,
    highlightedTaskId,
    highlightedBatchId,
    onToggleCandidate: toggleSlotImage,
    onFillBatch: fillImagesToSlots,
    onRemove: removeCandidate,
    onRetryFailure: retryGeneratedFailure,
    onSetAnchor: setStyleAnchor,
    onClearSlot: clearSlot,
    onMoveSlot: moveSlot,
    onClearSlots: clearSlots,
  }

  const renderPoolWorkspace = () => {
    if (sourceMode === 'upload') {
      return (
        <section className="image-tool-workspace-section">
          <div className="image-tool-panel-title"><Layers size={18} />上传素材池</div>
          <ImageGrid
            images={uploadedImages}
            onRemove={index => removeSourceImage('uploadedImages', index)}
            selectedUrls={selectedSlotUrls}
            styleAnchorImage={styleAnchorImage}
            onToggle={toggleSlotImage}
            onSetAnchor={setStyleAnchor}
            showActions
          />
        </section>
      )
    }

    if (sourceMode === 'split') {
      const latestSplitBatch = splitBatches[splitBatches.length - 1]
      const expandedIds = expandedSplitBatchIds
      const toggleSplitBatch = (batchId) => {
        setExpandedSplitBatchIds(prev => {
          const next = new Set(prev)
          if (next.has(batchId)) next.delete(batchId)
          else next.add(batchId)
          return next
        })
      }
      return (
        <div className="image-tool-workspace-stack">
          <section className="image-tool-workspace-section">
            <div className="image-tool-panel-title"><Layers size={18} />待切图片</div>
            <ImageGrid
              images={splitSourceImage}
              onRemove={index => removeSourceImage('splitSourceImage', index)}
              emptyText="还没有待切图片"
              styleAnchorImage={styleAnchorImage}
              onSetAnchor={setStyleAnchor}
              showActions
            />
          </section>
          <section className="image-tool-workspace-section">
            <div className="image-tool-panel-title">
              <Layers size={18} />切图素材池
              <span>{splitBatches.length} 批 / {splitImages.length} 张</span>
              <button type="button" onClick={() => fillImagesToSlots(latestSplitBatch?.images || [])} disabled={!latestSplitBatch?.images?.length || selectedSlotImages.length >= MAX_IMAGE_COUNT}>
                <Plus size={14} />最新批次入槽
              </button>
            </div>
            {!splitBatches.length && <div className="image-tool-empty"><Plus size={22} />切图后会出现在这里</div>}
            {!!splitBatches.length && (
              <div className="image-tool-split-batch-list">
                {splitBatches.map((batch, index) => {
                  const expanded = expandedIds.has(batch.id)
                  const batchSelectedCount = (batch.images || []).filter(image => selectedSlotUrls.includes(image.url)).length
                  return (
                    <section key={batch.id || index} className={`image-tool-split-batch ${expanded ? 'is-expanded' : ''}`}>
                      <div className="image-tool-split-batch-head">
                        <button type="button" className="image-tool-split-batch-toggle" onClick={() => toggleSplitBatch(batch.id)}>
                          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                          <strong>{batch.label || `第 ${index + 1} 批`}</strong>
                          <span>{batch.images?.length || 0} 张 · 已入槽 {batchSelectedCount} 张</span>
                        </button>
                        <div className="image-tool-split-batch-actions">
                          <button type="button" onClick={() => fillImagesToSlots(batch.images || [])} disabled={!batch.images?.length || selectedSlotImages.length >= MAX_IMAGE_COUNT}>
                            <Plus size={13} />本批入槽
                          </button>
                          <button type="button" onClick={() => removeSplitBatch(batch.id)}>
                            <Trash2 size={13} />删除本批
                          </button>
                        </div>
                      </div>
                      {expanded && (
                        <ImageGrid
                          images={batch.images || []}
                          onRemove={imageIndex => removeSplitImage(batch.id, imageIndex)}
                          emptyText="这一批还没有图片"
                          selectedUrls={selectedSlotUrls}
                          styleAnchorImage={styleAnchorImage}
                          onToggle={toggleSlotImage}
                          onSetAnchor={setStyleAnchor}
                          showActions
                        />
                      )}
                    </section>
                  )
                })}
              </div>
            )}
          </section>
        </div>
      )
    }

    return <CandidateImagePicker {...pickerProps} view="pool" showSummary={false} />
  }

  const runRoleSuggestions = async () => {
    const topic = roleSuggestTopic.trim() || inferRoleSuggestionTopic(generateTheme)
    if (!topic) {
      showPanelNotice('请先输入一个主体主题，例如：甜品、恐龙、武器。', 'warning', 'generate_roles')
      return
    }
    setRoleSuggesting(true)
    showPanelNotice('', undefined, 'generate_roles')
    try {
      const data = await suggestRoleItems({
        topic,
        theme: generateTheme,
        subject_type: roleSuggestType,
        model: roleSuggestModel,
        count: MAX_IMAGE_COUNT,
      })
      const nextItems = Array.isArray(data.items) ? data.items.map(item => String(item || '').trim()).filter(Boolean) : []
      if (nextItems.length !== MAX_IMAGE_COUNT) {
        throw new Error('模型返回的主体数量不足 9 个，请重新生成一次。')
      }
      setRoleItems(nextItems.slice(0, MAX_IMAGE_COUNT))
      setRoleSuggestTopic(topic)
      if (!generateTheme.trim()) setGenerateTheme(topic)
      showPanelNotice('已根据主题推荐 9 个主体，可以继续手动微调。', 'success', 'generate_roles')
    } catch (error) {
      showPanelNotice(displayError(error), 'error', 'generate_roles')
    } finally {
      setRoleSuggesting(false)
    }
  }

  const roleEditor = (
    <div className="image-tool-role-list">
      <div className="image-tool-role-list-head">
        <strong>9 个角色/物品</strong>
        <button type="button" onClick={() => setRoleItems(DEFAULT_ROLE_ITEMS)}>填入火锅示例</button>
      </div>
      <div className="image-tool-role-suggest">
        <input
          value={roleSuggestTopic}
          onChange={event => setRoleSuggestTopic(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault()
              runRoleSuggestions()
            }
          }}
          placeholder="输入主题，如：甜品、武器、宠物"
        />
        <select
          value={roleSuggestType}
          onChange={event => setRoleSuggestType(event.target.value)}
          disabled={roleSuggesting}
          title="选择模型按角色还是物品推荐"
        >
          <option value="object">物品</option>
          <option value="character">角色</option>
        </select>
        <select value={roleSuggestModel} onChange={event => setRoleSuggestModel(event.target.value)} disabled={roleSuggesting}>
          {REVERSE_MODELS.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}
        </select>
        <button
          type="button"
          onClick={runRoleSuggestions}
          disabled={roleSuggesting}
        >
          {roleSuggesting ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}模型推荐 9 个
        </button>
      </div>
      <div className="image-tool-role-grid">
        {roleItems.map((item, index) => (
          <label key={index}>
            <span>{index + 1}</span>
            <input
              value={item}
              onChange={event => {
                const next = [...roleItems]
                next[index] = event.target.value
                setRoleItems(next)
              }}
              placeholder={`主体 ${index + 1}`}
            />
          </label>
        ))}
      </div>
    </div>
  )

  const finalOutputPanel = (
    <>
      <div className="image-tool-setting-summary image-tool-final-output-summary">
        <div>
          <strong>成品输出</strong>
          <span>{preparedCount}/{MAX_IMAGE_COUNT} 槽位，水印：{savedWatermarkSettings.text.trim() || '未设置'} · {savedWatermarkSettings.outputMode === 'separate' ? '单图' : savedWatermarkSettings.outputMode === 'grid' ? '九宫格' : '单图+九宫格'}</span>
        </div>
        <div className="image-tool-setting-actions">
          <button type="button" onClick={() => setDrawerSection('finish')}>
            <Settings2 size={15} />水印设置
          </button>
          <button type="button" onClick={() => runWatermark(savedWatermarkSettings, 'final')} disabled={loading || !canGenerateFinal} title={finishDisabledReason || finalButtonLabel}>
            {loading ? <Loader2 className="spin" size={15} /> : <Stamp size={15} />}
            生成水印成品
          </button>
        </div>
      </div>
      {renderActionNotice('final')}
    </>
  )

  const drawerTitle = drawerSection === 'prompt'
    ? '提示词与风格锁定'
    : drawerSection === 'roles'
      ? '同风格角色主体'
      : '水印设置'

  const showGeneratedPool = sourceMode === 'generate_set' || sourceMode === 'generate_roles'
  const canClearTaskHistory = tasks.some(task => TERMINAL_TASK_STATUSES.has(task.status))
    || candidateBatches.length > 0
    || Object.values(slotGroups).some(slots => slots.some(isGeneratedWorkspaceImage))

  return (
    <section className="image-tool-layout">
      <div className="image-tool-panel">
        <div className="image-tool-panel-title"><Stamp size={18} />九图成片</div>
          <div className="image-tool-mode-grid">
            {NINE_IMAGE_SOURCE_MODES.map(mode => {
              const Icon = mode.icon
              return (
                <button
                  key={mode.id}
                  type="button"
                  className={sourceMode === mode.id ? 'is-active' : ''}
                  disabled={!mode.enabled}
                  title={mode.enabled ? mode.label : PAID_FEATURE_NOTICE}
                  onClick={() => handleSourceMode(mode)}
                >
                  <strong><Icon size={15} />{mode.label}</strong>
                  <span>{mode.hint}</span>
                </button>
              )
            })}
          </div>

        {sourceMode === 'upload' && (
          <>
            <UploadTile
              label="上传图片，最多 9 张"
              disabled={loading}
              onFiles={files => panelUploadImages(files, { limit: MAX_IMAGE_COUNT, current: uploadedImages, onChange: setUploadedImages })}
            />
            <button type="button" className="image-tool-secondary" disabled={!uploadedImages.length || selectedSlotImages.length >= MAX_IMAGE_COUNT} onClick={() => fillImagesToSlots(uploadedImages)}>
              上传图填入空槽
            </button>
            {renderActionNotice('upload')}
          </>
        )}

        {sourceMode === 'split' && (
          <>
            <UploadTile
              label="上传一张图，切成 9 张"
              disabled={loading || splitting}
              multiple={false}
              onFiles={files => panelUploadImages(files.slice(0, 1), { limit: 1, current: [], onChange: setSplitSourceImage }, 'split')}
            />
            <button type="button" className="image-tool-secondary" disabled={loading || splitting || !splitSourceImage.length} onClick={runSplitGrid}>
              {splitting ? <Loader2 className="spin" size={16} /> : null}
              切成 9 张素材
            </button>
            <button type="button" className="image-tool-secondary" disabled={!splitBatches.length || selectedSlotImages.length >= MAX_IMAGE_COUNT} onClick={() => fillImagesToSlots(splitBatches[splitBatches.length - 1]?.images || [])}>
              最新切图填入空槽
            </button>
            {renderActionNotice('split')}
          </>
        )}

        {sourceMode === 'generate_set' && (
          <>
            <div className="image-tool-compact-prompt">
              <Field label="画面内容">
                <textarea rows={2} value={generateTheme} onChange={event => setGenerateTheme(event.target.value)} placeholder="例：户外保温杯商品图" />
              </Field>
              <Field label="画风提示词">
                <textarea rows={3} value={generateStyle} onChange={event => setGenerateStyle(event.target.value)} placeholder="例：2D 卡通，粗线条，白底或浅色底，统一构图" />
              </Field>
              <button type="button" className="image-tool-secondary" onClick={() => setDrawerSection('prompt')}>
                <Settings2 size={16} />提示词与反推设置
              </button>
            </div>
            <div className="image-tool-form-grid">
              <Field label="生图平台">
                <select value={generateProvider} onChange={event => setGenerateProvider(event.target.value)}>
                  <option value="jimeng">即梦 / Seedream</option>
                  <option value="gemini_image">Gemini 图片</option>
                  <option value="openai_image">OpenAI Image</option>
                </select>
              </Field>
              <Field label="可用模型">
                <select value={generateModel} onChange={event => setGenerateModel(event.target.value)}>
                  {generateProviderModels.map(model => (
                    <option key={model.id} value={model.id}>{model.name || model.id}</option>
                  ))}
                  {!generateProviderModels.length && (
                    <option value={generateModel}>{modelsLoaded ? `${resolvedGenerateProviderLabel}未配置 API Key` : '模型加载中'}</option>
                  )}
                </select>
              </Field>
              <Field label="每批抽卡数量">
                <select value={batchSize} onChange={event => setBatchSize(Number(event.target.value))}>
                  {[3, 6, 9, 12].map(size => <option key={size} value={size}>{size} 张候选</option>)}
                </select>
              </Field>
              <Field label="素材池状态">
                <input value={`${flattenBatches(candidateBatches).length} 张候选 / ${selectedSlotImages.length} 个槽位`} readOnly />
              </Field>
            </div>
            <button type="button" className="image-tool-secondary" disabled={loading || generating || !modelsLoaded || !generateProviderReady} onClick={runGenerateCandidates}>
              {generating ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
              提交素材候选任务
            </button>
            {renderActionNotice('generate')}
          </>
        )}

        {sourceMode === 'generate_roles' && (
          <>
            <div className="image-tool-compact-prompt">
              <Field label="统一主题">
                <textarea rows={2} value={generateTheme} onChange={event => setGenerateTheme(event.target.value)} placeholder="例：户外保温杯商品图" />
              </Field>
              <Field label="统一画风">
                <textarea rows={3} value={generateStyle} onChange={event => setGenerateStyle(event.target.value)} placeholder="例：同一模板、同一构图、只替换主体元素" />
              </Field>
              <div className="image-tool-setting-summary">
                <div>
                  <strong>角色主体</strong>
                  <span>{filledRoleCount}/9 已填写</span>
                </div>
                <button type="button" onClick={() => setDrawerSection('roles')}>
                  <UsersRound size={15} />编辑主体
                </button>
              </div>
              <button type="button" className="image-tool-secondary" onClick={() => setDrawerSection('prompt')}>
                <Settings2 size={16} />提示词与反推设置
              </button>
            </div>
            <div className="image-tool-form-grid">
              <Field label="生图平台">
                <select value={generateProvider} onChange={event => setGenerateProvider(event.target.value)}>
                  <option value="jimeng">即梦 / Seedream</option>
                  <option value="gemini_image">Gemini 图片</option>
                  <option value="openai_image">OpenAI Image</option>
                </select>
              </Field>
              <Field label="可用模型">
                <select value={generateModel} onChange={event => setGenerateModel(event.target.value)}>
                  {generateProviderModels.map(model => (
                    <option key={model.id} value={model.id}>{model.name || model.id}</option>
                  ))}
                  {!generateProviderModels.length && (
                    <option value={generateModel}>{modelsLoaded ? `${resolvedGenerateProviderLabel}未配置 API Key` : '模型加载中'}</option>
                  )}
                </select>
              </Field>
            </div>
            <button type="button" className="image-tool-secondary" disabled={loading || generating || !modelsLoaded || !generateProviderReady} onClick={runGenerateRoles}>
              {generating ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
              提交同风格角色九图任务
            </button>
            {renderActionNotice('generate_roles')}
          </>
        )}

        <PanelNotice notice={panelNotice} />

        {false && <div className="image-tool-setting-summary image-tool-output-summary-old">
          <div>
            <strong>成品输出</strong>
            <span>{preparedCount}/{MAX_IMAGE_COUNT} 槽位，水印：{savedWatermarkSettings.text.trim() || '未设置'} · {savedWatermarkSettings.outputMode === 'separate' ? '单图' : savedWatermarkSettings.outputMode === 'grid' ? '九宫格' : '单图+九宫格'}</span>
          </div>
          <div className="image-tool-setting-actions">
            <button type="button" onClick={() => setDrawerSection('finish')}>
              <Settings2 size={15} />水印设置
            </button>
            <button type="button" onClick={() => runWatermark(savedWatermarkSettings, 'final')} disabled={loading || !canGenerateFinal} title={finishDisabledReason || finalButtonLabel}>
              {loading ? <Loader2 className="spin" size={15} /> : <Stamp size={15} />}
              生成水印成品
            </button>
          </div>
        </div>}
        {false && renderActionNotice('final')}
        <div className="image-tool-left-task-slot">
          <TaskQueuePanel
            tasks={visibleTasks}
            notice={taskNotice}
            onCancel={cancelTask}
            onDelete={async (taskId) => {
              if (String(taskId || '').startsWith('local-')) return removeProgressTask(taskId)
              return handleDeleteTask(taskId)
            }}
            onClearFinished={async () => {
              await clearFinishedProgressTasks()
              await handleClearFinishedTasks()
            }}
            onRefresh={refreshTasks}
            onLocate={onLocateTask}
            canClearFinished={canClearTaskHistory}
            compact
          />
          {renderActionNotice('tasks')}
        </div>
      </div>

      <div className="image-tool-panel image-tool-workspace-panel">
        <div className="image-tool-panel-title"><Layers size={18} />处理结果</div>
        <CandidateImagePicker
          {...pickerProps}
          view={showGeneratedPool ? 'all' : 'slots'}
          showSummary={showGeneratedPool}
          slotFooter={finalOutputPanel}
        />
        {renderActionNotice('slots')}
        {!showGeneratedPool && renderPoolWorkspace()}
        {((finalResult.images || []).length > 0 || finalResult.grid) && (
          <div
            className={`image-tool-result-locate ${highlightedTaskId && highlightedTaskId === finalResult.task_id ? 'is-located' : ''}`}
            data-watermark-result-task-id={finalResult.task_id || undefined}
          >
            <ResultGrid images={finalResult.images} grid={finalResult.grid} />
          </div>
        )}
      </div>
      {drawerSection && (
        <div className="image-tool-drawer-backdrop" role="presentation" onClick={() => setDrawerSection(null)}>
          <aside className="image-tool-drawer" onClick={event => event.stopPropagation()}>
            <div className="image-tool-drawer-head">
              <strong>{drawerTitle}</strong>
              <button type="button" onClick={() => setDrawerSection(null)} title="关闭">
                <X size={16} />
              </button>
            </div>
            {drawerSection === 'prompt' && (
              <>
                <PromptAssistBox
                  theme={generateTheme}
                  visualStyle={generateStyle}
                  onThemeChange={setGenerateTheme}
                  onVisualStyleChange={setGenerateStyle}
                  uploadImages={(files, options) => panelUploadImages(files, options, 'prompt')}
                  setNotice={(message, tone) => showPanelNotice(message, tone, 'prompt')}
                  styleLock={styleLock}
                  onStyleLockChange={setStyleLock}
                  styleLockOptions={styleLockOptions}
                  onStyleLockOptionsChange={setStyleLockOptions}
                  variationPolicy={variationPolicy}
                  onVariationPolicyChange={setVariationPolicy}
                  styleAnchorImage={styleAnchorImage}
                  onStyleAnchorChange={setStyleAnchor}
                  onApplyFriendCirclePreset={() => setGenerateStyle(FRIEND_CIRCLE_NINE_GRID_STYLE)}
                  disabled={loading || generating}
                />
                {renderActionNotice('prompt')}
              </>
            )}
            {drawerSection === 'roles' && roleEditor}
            {drawerSection === 'finish' && (
              <>
                <WatermarkControls
                  text={text}
                  setText={setText}
                  outputMode={outputMode}
                  setOutputMode={setOutputMode}
                  position={position}
                  setPosition={setPosition}
                  fontStyle={fontStyle}
                  setFontStyle={setFontStyle}
                  opacity={opacity}
                  setOpacity={setOpacity}
                  color={color}
                  setColor={setColor}
                  strokeColor={strokeColor}
                  setStrokeColor={setStrokeColor}
                  fontOptions={fontOptions}
                  selectedFontId={selectedFontId}
                  setSelectedFontId={setSelectedFontId}
                  fontUrl={fontUrl}
                  setFontUrl={setFontUrl}
                  fontName={fontName}
                  setFontName={setFontName}
                  fontUploading={fontUploading}
                  uploadFont={uploadFont}
                  disabled={loading}
                />
                {!loading && draftFinishDisabledReason && (
                  <div className="image-tool-inline-warning">{draftFinishDisabledReason}</div>
                )}
                <div className="image-tool-drawer-action-grid">
                  <button type="button" className="image-tool-secondary" disabled={loading} onClick={() => saveWatermarkSettings(draftWatermarkSettings, 'finish')}>
                    <Settings2 size={16} />保存设置
                  </button>
                  <button
                    type="button"
                    className="image-tool-primary"
                    disabled={loading || Boolean(draftFinishDisabledReason)}
                    onClick={() => {
                      const nextSettings = saveWatermarkSettings(draftWatermarkSettings, 'finish')
                      runWatermark(nextSettings, 'finish')
                    }}
                  >
                    {loading ? <Loader2 className="spin" size={16} /> : <Stamp size={16} />}
                    {loading ? '正在提交水印任务...' : '保存并生成'}
                  </button>
                </div>
                {renderActionNotice('finish')}
              </>
            )}
          </aside>
        </div>
      )}
    </section>
  )
}
