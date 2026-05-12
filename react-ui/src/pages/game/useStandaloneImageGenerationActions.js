import { useCallback } from 'react'
import { absoluteMediaUrl } from './gameVideoPageHelpers'
import {
  getImageAspectOption,
  getImageRefBlockReason,
  normalizeImageQualityForModel,
} from './gameVideoModelUtils'

export function useStandaloneImageGenerationActions({
  currentProjectId,
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
  getFriendlyImageError,
  persistStandaloneImageState,
  deleteServerFilesAfterSave,
}) {
  const handleRefreshStandaloneImagePrompt = useCallback(async () => {
    if (!imgGenPrompt.trim()) return
    setImgGenRefreshing(true)
    try {
      const d = await postPromptRefresh(imgGenPrompt, imgGenPromptModel, 'image')
      const prompt = (d.prompt || '').trim()
      if (!prompt) throw new Error('模型没有返回润色结果，请稍后重试。')
      setImgGenPrompt(prompt)
      persistStandaloneImageState({ imgGenPrompt: prompt })
    } catch (e) {
      alert('刷新失败: ' + getFriendlyImageError(e))
    } finally {
      setImgGenRefreshing(false)
    }
  }, [
    getFriendlyImageError,
    imgGenPrompt,
    imgGenPromptModel,
    persistStandaloneImageState,
    postPromptRefresh,
    setImgGenPrompt,
    setImgGenRefreshing,
  ])

  const removeStandaloneHistoryImage = useCallback((idx) => {
    const removed = imgGenHistory[idx]?.url
    const nextHistory = imgGenHistory.filter((_, i) => i !== idx)
    setImgGenHistory(nextHistory)
    deleteServerFilesAfterSave(removed, persistStandaloneImageState({ imgGenHistory: nextHistory }))
  }, [deleteServerFilesAfterSave, imgGenHistory, persistStandaloneImageState, setImgGenHistory])

  const handleStandaloneImageModelChange = useCallback((modelId) => {
    setImgGenModel(modelId)
    const model = imageModels.find(item => item.id === modelId)
    if (!model) return
    const nextQuality = normalizeImageQualityForModel(imgGenQuality, model)
    setImgGenProvider(model.provider)
    setImgGenQuality(nextQuality)
    persistStandaloneImageState({ imgGenModel: modelId, imgGenProvider: model.provider, imgGenQuality: nextQuality })
  }, [
    imageModels,
    imgGenQuality,
    persistStandaloneImageState,
    setImgGenModel,
    setImgGenProvider,
    setImgGenQuality,
  ])

  const handleStandaloneImageAspectRatioChange = useCallback((aspectRatio) => {
    setImgGenAspectRatio(aspectRatio)
    persistStandaloneImageState({ imgGenAspectRatio: aspectRatio })
  }, [persistStandaloneImageState, setImgGenAspectRatio])

  const handleStandaloneImageQualityChange = useCallback((quality) => {
    const selectedModel = imageModels.find(item => item.id === imgGenModel)
    const nextQuality = normalizeImageQualityForModel(quality, selectedModel)
    setImgGenQuality(nextQuality)
    persistStandaloneImageState({ imgGenQuality: nextQuality })
  }, [imageModels, imgGenModel, persistStandaloneImageState, setImgGenQuality])

  const handleStandaloneImagePromptModelChange = useCallback((modelId) => {
    setImgGenPromptModel(modelId)
    persistStandaloneImageState({ imgGenPromptModel: modelId })
  }, [persistStandaloneImageState, setImgGenPromptModel])

  const handleStandaloneImageEditModeChange = useCallback((editMode) => {
    setImgGenEditMode(editMode)
    persistStandaloneImageState({ imgGenEditMode: editMode })
  }, [persistStandaloneImageState, setImgGenEditMode])

  const handleStandaloneReferenceImageUpload = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.multiple = true
    input.onchange = async (event) => {
      const uploaded = await uploadFilesWithFeedback(Array.from(event.target.files || []), { failureLabel: '参考图上传失败' })
      if (!uploaded.length) return
      const next = [...imgGenRefImages, ...uploaded]
      setImgGenRefImages(next)
      persistStandaloneImageState({ imgGenRefImages: next })
    }
    input.click()
  }, [imgGenRefImages, persistStandaloneImageState, setImgGenRefImages, uploadFilesWithFeedback])

  const handleRemoveStandaloneReferenceImage = useCallback((idx) => {
    const next = imgGenRefImages.filter((_, i) => i !== idx)
    setImgGenRefImages(next)
    persistStandaloneImageState({ imgGenRefImages: next })
  }, [imgGenRefImages, persistStandaloneImageState, setImgGenRefImages])

  const handleCopyStandaloneImageLink = useCallback((url) => {
    void navigator.clipboard.writeText(absoluteMediaUrl(url))
  }, [])

  const handleStandaloneGenImage = useCallback(async () => {
    if (!imgGenPrompt.trim()) return
    const selectedModel = imageModels.find(m => m.id === imgGenModel)
    const blockReason = getImageRefBlockReason(selectedModel, imgGenRefImages.length, imgGenEditMode && imgGenRefImages.length > 0)
    if (blockReason) {
      alert(blockReason)
      return
    }
    setImgGenLoading(true)
    try {
      const imageSize = getImageAspectOption(imgGenAspectRatio)
      const imageQuality = normalizeImageQualityForModel(imgGenQuality, selectedModel)
      const d = await postImageGeneration({
        project_id: currentProjectId || '',
        prompt: imgGenPrompt,
        provider: imgGenProvider,
        model: imgGenModel,
        width: imageSize.width,
        height: imageSize.height,
        aspect_ratio: imageSize.id,
        asset_type: 'standalone',
        reference_urls: imgGenRefImages.map(i => i.url),
        edit_mode: imgGenEditMode && imgGenRefImages.length > 0,
        image_quality: imageQuality,
        prompt_optimize_mode: 'standard',
      })
      if (d.image_url) {
        const item = {
          url: d.image_url,
          prompt: imgGenPrompt,
          model: imgGenModel,
          provider: imgGenProvider,
          aspectRatio: imageSize.id,
          width: imageSize.width,
          height: imageSize.height,
          quality: imageQuality,
          ts: Date.now(),
        }
        const nextHistory = [item, ...imgGenHistory]
        setImgGenHistory(nextHistory)
        persistStandaloneImageState({ imgGenHistory: nextHistory })
      }
    } catch (e) {
      alert('生成失败: ' + getFriendlyImageError(e))
    } finally {
      setImgGenLoading(false)
    }
  }, [
    currentProjectId,
    getFriendlyImageError,
    imageModels,
    imgGenAspectRatio,
    imgGenEditMode,
    imgGenHistory,
    imgGenModel,
    imgGenPrompt,
    imgGenProvider,
    imgGenQuality,
    imgGenRefImages,
    persistStandaloneImageState,
    postImageGeneration,
    setImgGenHistory,
    setImgGenLoading,
  ])

  return {
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
  }
}
