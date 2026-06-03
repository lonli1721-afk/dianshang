import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../../services/api'
import ImageGenerationPanel from '../../game/components/ImageGenerationPanel'
import { DEFAULT_IMAGE_ASPECT_RATIO } from '../../game/gameVideoConstants'
import { absoluteMediaUrl, logGamePageError, mediaUrl } from '../../game/gameVideoPageHelpers'
import { cleanImageModelLabel, getImageQualityIds, normalizeImageQualityForModel } from '../../game/gameVideoModelUtils'
import { useStandaloneImageGenerationActions } from '../../game/useStandaloneImageGenerationActions'
import { uploadGameImage } from '../imageToolboxApi'

const STORAGE_KEY = 'image-toolbox-standalone-image-v1'

function readStoredState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeStoredState(patch) {
  const current = readStoredState()
  const next = { ...current, ...patch }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  return Promise.resolve(next)
}

function friendlyImageError(error) {
  const raw = error?.message || String(error || '')
  let text = raw
  try {
    const parsed = JSON.parse(raw)
    text = parsed?.detail || parsed?._error || parsed?.message || raw
  } catch {
    // Keep the original provider message when it is not JSON.
  }
  if (/503|UNAVAILABLE|high demand|temporar/i.test(text)) return '模型服务当前繁忙，请稍后重试。'
  if (/504|DEADLINE_EXCEEDED|deadline expired/i.test(text)) return '模型响应超时，请稍后重试。'
  if (/OversizeImage|exceeds the limit|10 MiB|图片.*过大|参考图超过/i.test(text)) {
    return '参考图超过即梦 10 MiB 输入限制。系统会自动压缩本地上传图；如果仍失败，请先把参考图压缩到 10 MiB 以下后重试。'
  }
  return text
}

export function StandaloneImagePanel({ imageModels, modelsLoaded, onOpenImage }) {
  const stored = useMemo(() => readStoredState(), [])
  const [imgGenHistory, setImgGenHistory] = useState(() => Array.isArray(stored.imgGenHistory) ? stored.imgGenHistory : [])
  const [imgGenPrompt, setImgGenPrompt] = useState(() => stored.imgGenPrompt || '')
  const [imgGenPromptModel, setImgGenPromptModel] = useState(() => stored.imgGenPromptModel || 'doubao-seed-2-0-pro-260215')
  const [imgGenModel, setImgGenModel] = useState(() => stored.imgGenModel || '')
  const [imgGenProvider, setImgGenProvider] = useState(() => stored.imgGenProvider || '')
  const [imgGenRefImages, setImgGenRefImages] = useState(() => Array.isArray(stored.imgGenRefImages) ? stored.imgGenRefImages : [])
  const [imgGenEditMode, setImgGenEditMode] = useState(() => !!stored.imgGenEditMode)
  const [imgGenAspectRatio, setImgGenAspectRatio] = useState(() => stored.imgGenAspectRatio || DEFAULT_IMAGE_ASPECT_RATIO)
  const [imgGenQuality, setImgGenQuality] = useState(() => stored.imgGenQuality || '2K')
  const [imgGenLoading, setImgGenLoading] = useState(false)
  const [imgGenRefreshing, setImgGenRefreshing] = useState(false)

  useEffect(() => {
    if (!modelsLoaded || !imageModels.length || imgGenModel) return
    const firstModel = imageModels[0]
    const nextQuality = normalizeImageQualityForModel(imgGenQuality, firstModel)
    setImgGenModel(firstModel.id)
    setImgGenProvider(firstModel.provider)
    setImgGenQuality(nextQuality)
    writeStoredState({ imgGenModel: firstModel.id, imgGenProvider: firstModel.provider, imgGenQuality: nextQuality })
  }, [imageModels, imgGenModel, imgGenQuality, modelsLoaded])

  const uploadFilesWithFeedback = useCallback(async (files, { failureLabel }) => {
    const uploaded = []
    let failedCount = 0
    for (const file of files) {
      try {
        const result = await uploadGameImage(file)
        uploaded.push({ url: result.url, name: file.name.replace(/\.[^.]+$/, '') })
      } catch (error) {
        failedCount += 1
        logGamePageError(`${failureLabel}:${file.name}`, error)
      }
    }
    if (failedCount > 0) {
      alert(`${failureLabel}：成功 ${uploaded.length} 个，失败 ${failedCount} 个，请重试失败文件。`)
    }
    return uploaded
  }, [])

  const postImageGeneration = useCallback((body) => api.post('/api/game/generate_image', body), [])

  const postPromptRefresh = useCallback((prompt, model, target = 'image') => (
    api.post('/api/game/refresh_prompt', {
      project_id: '',
      prompt,
      model,
      target,
      scene_refs: target === 'image' ? imgGenRefImages.map(item => item.url) : [],
    })
  ), [imgGenRefImages])

  const persistStandaloneImageState = useCallback((patch) => writeStoredState(patch), [])

  const {
    handleRefreshStandaloneImagePrompt,
    removeStandaloneHistoryImage,
    handleStandaloneImageModelChange,
    handleStandaloneImageAspectRatioChange,
    handleStandaloneImageQualityChange,
    handleStandaloneImagePromptModelChange,
    handleStandaloneImageEditModeChange,
    handleStandaloneReferenceImageUpload,
    handleRemoveStandaloneReferenceImage,
    handleCopyStandaloneImageLink,
    handleStandaloneGenImage,
  } = useStandaloneImageGenerationActions({
    currentProjectId: '',
    imageModels,
    imgGenPrompt,
    imgGenPromptModel,
    imgGenModel,
    imgGenProvider,
    imgGenRefImages,
    imgGenEditMode,
    imgGenAspectRatio,
    imgGenQuality,
    imgGenHistory,
    setImgGenPrompt,
    setImgGenPromptModel,
    setImgGenModel,
    setImgGenProvider,
    setImgGenRefImages,
    setImgGenEditMode,
    setImgGenAspectRatio,
    setImgGenQuality,
    setImgGenLoading,
    setImgGenRefreshing,
    setImgGenHistory,
    uploadFilesWithFeedback,
    postImageGeneration,
    postPromptRefresh,
    getFriendlyImageError: friendlyImageError,
    persistStandaloneImageState,
    deleteServerFilesAfterSave: () => {},
  })

  const selectedModel = imageModels.find(model => model.id === imgGenModel)
  const qualityIds = getImageQualityIds(selectedModel)
  const safeQuality = normalizeImageQualityForModel(imgGenQuality, selectedModel)

  return (
    <ImageGenerationPanel
      active
      imageModels={imageModels}
      model={imgGenModel}
      aspectRatio={imgGenAspectRatio}
      quality={safeQuality}
      qualityIds={qualityIds}
      promptModel={imgGenPromptModel}
      prompt={imgGenPrompt}
      refreshing={imgGenRefreshing}
      loading={imgGenLoading}
      refImages={imgGenRefImages}
      editMode={imgGenEditMode}
      history={imgGenHistory}
      cleanImageModelName={cleanImageModelLabel}
      onModelChange={handleStandaloneImageModelChange}
      onAspectRatioChange={handleStandaloneImageAspectRatioChange}
      onQualityChange={handleStandaloneImageQualityChange}
      onPromptModelChange={handleStandaloneImagePromptModelChange}
      onPromptChange={setImgGenPrompt}
      onRefreshPrompt={handleRefreshStandaloneImagePrompt}
      onUploadReferenceImages={handleStandaloneReferenceImageUpload}
      onEditModeChange={handleStandaloneImageEditModeChange}
      onOpenImage={(url) => onOpenImage?.(mediaUrl(url))}
      onRemoveReferenceImage={handleRemoveStandaloneReferenceImage}
      onGenerate={handleStandaloneGenImage}
      onRemoveHistoryImage={removeStandaloneHistoryImage}
      onCopyImageLink={(url) => {
        void navigator.clipboard.writeText(absoluteMediaUrl(url))
        handleCopyStandaloneImageLink(url)
      }}
    />
  )
}
