export function assetUrl(url) {
  if (!url) return ''
  const token = typeof window !== 'undefined' ? window.localStorage.getItem('token') || '' : ''
  const needsToken = token && (url.startsWith('/api/files/') || url.includes('/api/files/')) && !url.includes('token=')
  const authedUrl = needsToken
    ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
    : url
  if (!authedUrl.startsWith('/')) return authedUrl
  return `${import.meta.env.VITE_API_URL || ''}${authedUrl}`
}

export const IMAGE_TOOL_WORKSPACE_STORAGE_KEY = 'image-toolbox-workspace-v2'
export const IMAGE_TOOL_SLOT_GROUP_IDS = ['upload', 'split', 'generate_set', 'generate_roles']

export const DEFAULT_WATERMARK_SETTINGS = {
  text: '',
  position: 'top_left',
  fontStyle: 'rounded',
  selectedFontId: '',
  fontUrl: '',
  fontName: '',
  color: '#ffffff',
  opacity: 100,
  strokeColor: '#000000',
  outputMode: 'both',
}

export function createEmptyImageToolSlots() {
  return Array.from({ length: 9 }, () => null)
}

export function createImageToolWorkspace() {
  return {
    workspace_id: `workspace_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    uploadedImages: [],
    splitSourceImage: [],
    splitImages: [],
    splitBatches: [],
    candidateBatches: [],
    selectedSlots: createEmptyImageToolSlots(),
    slotGroups: IMAGE_TOOL_SLOT_GROUP_IDS.reduce((acc, id) => ({ ...acc, [id]: createEmptyImageToolSlots() }), {}),
    styleAnchorImage: null,
    styleLock: 'strict',
    styleLockOptions: [],
    variationPolicy: 'subject_only',
    watermarkSettings: { ...DEFAULT_WATERMARK_SETTINGS },
    generateTheme: '',
    generateStyle: '',
    appliedReversePrompt: null,
    completedTaskIds: [],
    finalResult: { images: [], grid: null },
  }
}

export function normalizeImageToolSlots(slots) {
  return Array.from({ length: 9 }, (_, index) => slots?.[index]?.url ? slots[index] : null)
}

export function normalizeImageToolSlotGroups(slotGroups, legacySlots = []) {
  const hasGroups = slotGroups && typeof slotGroups === 'object'
  const groups = {}
  for (const id of IMAGE_TOOL_SLOT_GROUP_IDS) {
    groups[id] = normalizeImageToolSlots(hasGroups ? slotGroups[id] : [])
  }

  const hasAnyGroupedSlot = Object.values(groups).some(slots => slots.some(Boolean))
  const normalizedLegacy = normalizeImageToolSlots(legacySlots)
  if (!hasAnyGroupedSlot && normalizedLegacy.some(Boolean)) {
    groups.upload = normalizedLegacy
  }
  return groups
}

export function normalizeSplitBatches(splitBatches, legacySplitImages = []) {
  if (Array.isArray(splitBatches) && splitBatches.length) {
    return splitBatches
      .filter(batch => Array.isArray(batch?.images) && batch.images.length)
      .map((batch, index) => ({
        id: batch.id || `split_${Date.now()}_${index}`,
        label: batch.label || `第 ${index + 1} 批`,
        source_url: batch.source_url || '',
        images: batch.images,
        created_at: batch.created_at || Date.now(),
      }))
  }
  if (Array.isArray(legacySplitImages) && legacySplitImages.length) {
    return [{
      id: `split_legacy_${Date.now()}`,
      label: '历史切图',
      source_url: '',
      images: legacySplitImages,
      created_at: Date.now(),
    }]
  }
  return []
}

export function normalizeWatermarkSettings(settings) {
  const raw = settings && typeof settings === 'object' ? settings : {}
  return {
    ...DEFAULT_WATERMARK_SETTINGS,
    ...raw,
    text: typeof raw.text === 'string' ? raw.text : DEFAULT_WATERMARK_SETTINGS.text,
    position: typeof raw.position === 'string' ? raw.position : DEFAULT_WATERMARK_SETTINGS.position,
    fontStyle: typeof raw.fontStyle === 'string' ? raw.fontStyle : DEFAULT_WATERMARK_SETTINGS.fontStyle,
    selectedFontId: typeof raw.selectedFontId === 'string' ? raw.selectedFontId : DEFAULT_WATERMARK_SETTINGS.selectedFontId,
    fontUrl: typeof raw.fontUrl === 'string' ? raw.fontUrl : DEFAULT_WATERMARK_SETTINGS.fontUrl,
    fontName: typeof raw.fontName === 'string' ? raw.fontName : DEFAULT_WATERMARK_SETTINGS.fontName,
    color: typeof raw.color === 'string' ? raw.color : DEFAULT_WATERMARK_SETTINGS.color,
    opacity: Number.isFinite(Number(raw.opacity)) ? Number(raw.opacity) : DEFAULT_WATERMARK_SETTINGS.opacity,
    strokeColor: typeof raw.strokeColor === 'string' ? raw.strokeColor : DEFAULT_WATERMARK_SETTINGS.strokeColor,
    outputMode: ['both', 'separate', 'grid'].includes(raw.outputMode) ? raw.outputMode : DEFAULT_WATERMARK_SETTINGS.outputMode,
  }
}

export function loadImageToolWorkspace() {
  try {
    const raw = window.localStorage.getItem(IMAGE_TOOL_WORKSPACE_STORAGE_KEY)
    if (!raw) return createImageToolWorkspace()
    const parsed = JSON.parse(raw)
    const fallback = createImageToolWorkspace()
    const selectedSlots = normalizeImageToolSlots(parsed.selectedSlots)
    const splitBatches = normalizeSplitBatches(parsed.splitBatches, parsed.splitImages)
    return {
      ...fallback,
      ...parsed,
      uploadedImages: Array.isArray(parsed.uploadedImages) ? parsed.uploadedImages : [],
      splitSourceImage: Array.isArray(parsed.splitSourceImage) ? parsed.splitSourceImage : [],
      splitImages: Array.isArray(parsed.splitImages) ? parsed.splitImages : [],
      splitBatches,
      candidateBatches: Array.isArray(parsed.candidateBatches) ? parsed.candidateBatches : [],
      selectedSlots,
      slotGroups: normalizeImageToolSlotGroups(parsed.slotGroups, selectedSlots),
      styleAnchorImage: parsed.styleAnchorImage?.url ? parsed.styleAnchorImage : null,
      styleLock: ['strict', 'soft', 'off'].includes(parsed.styleLock) ? parsed.styleLock : 'strict',
      styleLockOptions: Array.isArray(parsed.styleLockOptions) ? parsed.styleLockOptions : [],
      variationPolicy: typeof parsed.variationPolicy === 'string' ? parsed.variationPolicy : 'subject_only',
      watermarkSettings: normalizeWatermarkSettings(parsed.watermarkSettings),
      generateTheme: typeof parsed.generateTheme === 'string' ? parsed.generateTheme : '',
      generateStyle: typeof parsed.generateStyle === 'string' ? parsed.generateStyle : '',
      appliedReversePrompt: parsed.appliedReversePrompt || null,
      completedTaskIds: Array.isArray(parsed.completedTaskIds) ? parsed.completedTaskIds : [],
      finalResult: parsed.finalResult || { images: [], grid: null },
    }
  } catch {
    window.localStorage.removeItem(IMAGE_TOOL_WORKSPACE_STORAGE_KEY)
    return createImageToolWorkspace()
  }
}

export function persistImageToolWorkspace(workspace) {
  window.localStorage.setItem(IMAGE_TOOL_WORKSPACE_STORAGE_KEY, JSON.stringify(workspace))
}

export function addImagesToImageToolWorkspaceSlots(images = []) {
  const workspace = loadImageToolWorkspace()
  const slotGroups = normalizeImageToolSlotGroups(workspace.slotGroups, workspace.selectedSlots)
  const selectedSlots = normalizeImageToolSlots(slotGroups.upload)
  const existing = new Set(selectedSlots.filter(Boolean).map(item => item.url))
  let inserted = 0

  for (const image of images) {
    if (!image?.url || existing.has(image.url)) continue
    const emptyIndex = selectedSlots.findIndex(item => !item)
    if (emptyIndex < 0) break
    selectedSlots[emptyIndex] = image
    existing.add(image.url)
    inserted += 1
  }

  persistImageToolWorkspace({
    ...workspace,
    slotGroups: { ...slotGroups, upload: selectedSlots },
    selectedSlots,
    finalResult: { images: [], grid: null },
  })
  return inserted
}

export function setImageToolWorkspaceStyleAnchor(image) {
  if (!image?.url) return false
  const workspace = loadImageToolWorkspace()
  persistImageToolWorkspace({
    ...workspace,
    styleAnchorImage: image,
  })
  return true
}

export function updateImageToolWorkspacePrompt({ theme, visualStyle, reversePayload = null } = {}) {
  const workspace = loadImageToolWorkspace()
  persistImageToolWorkspace({
    ...workspace,
    generateTheme: typeof theme === 'string' ? theme : workspace.generateTheme,
    generateStyle: typeof visualStyle === 'string' ? visualStyle : workspace.generateStyle,
    appliedReversePrompt: reversePayload || workspace.appliedReversePrompt || null,
  })
}

export async function downloadAsset(url, filename = '') {
  const resolved = assetUrl(url)
  if (!resolved) return
  const response = await fetch(resolved)
  if (!response.ok) throw new Error('下载失败，请稍后重试。')
  const blob = await response.blob()
  const objectUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename || url.split('/').pop() || 'image.png'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(objectUrl)
}

export function displayError(error) {
  const raw = error?.message || String(error || '')
  const withoutStatus = raw.replace(/^\s*\d{3}:\s*/, '')
  if (/Jimeng API key is not configured/i.test(withoutStatus)) {
    return '即梦 / Seedream 还没有配置 API Key，请先到设置里配置，或切换到 Gemini 图片。'
  }
  if (/Gemini API key is not configured/i.test(withoutStatus)) {
    return 'Gemini 图片还没有配置 API Key，请先到设置里配置，或切换到即梦 / Seedream。'
  }
  try {
    const parsed = JSON.parse(raw.trim())
    return parsed?.detail || parsed?._error || withoutStatus
  } catch {
    return withoutStatus
  }
}

export function noticeToneFromMessage(message = '', fallback = 'info') {
  if (!message) return fallback
  if (/失败|错误|报错|请先|不能|需要|未配置|超过|重试|尚未就绪|已满|为空/.test(message)) return 'error'
  if (/警告|等待|加载中|稍后/.test(message)) return 'warning'
  if (/已|成功|完成|提交|填入|更新|加入|设为/.test(message)) return 'success'
  return fallback
}

export function imageResultsFromPayload(payload) {
  const images = []
  if (payload?.image_url) images.push({ url: payload.image_url })
  for (const image of payload?.images || []) {
    if (image?.url) images.push(image)
  }
  return images
}
