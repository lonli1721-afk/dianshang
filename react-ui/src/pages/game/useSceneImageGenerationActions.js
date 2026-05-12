import { useCallback } from 'react'
import { DEFAULT_IMAGE_ASPECT_RATIO } from './gameVideoConstants'
import {
  getImageAspectOption,
  getImageRefBlockReason,
  normalizeImageAspectRatio,
  normalizeImageQualityForModel,
} from './gameVideoModelUtils'

export function useSceneImageGenerationActions({
  currentProjectId,
  genScenes,
  replScenes,
  imageModels,
  genModal,
  genPrompt,
  genImgModel,
  genImgProvider,
  genRefImages,
  genImageEditMode,
  genImageAspectRatio,
  genImageQuality,
  setGenModal,
  setGenPrompt,
  setGenImgModel,
  setGenImgProvider,
  setGeneratingImg,
  setGenRefImages,
  setGenImageEditMode,
  setGenImageAspectRatio,
  setGenImageQuality,
  setGenScenes,
  setReplScenes,
  uploadFilesWithFeedback,
  postImageGeneration,
  getFriendlyImageError,
  runSceneSave,
  deleteServerFilesAfterSave,
  insertTextAtCursor,
}) {
  const openGenModal = useCallback((sceneId, type) => {
    const scene = [...genScenes, ...replScenes].find(item => item.id === sceneId)
    setGenModal({ sceneId, type })
    setGenPrompt('')
    setGenRefImages([])
    setGenImageEditMode(false)
    setGenImageAspectRatio(type === 'scene' ? normalizeImageAspectRatio(scene?.aspectRatio) : DEFAULT_IMAGE_ASPECT_RATIO)
    setGenImageQuality('2K')
  }, [
    genScenes,
    replScenes,
    setGenImageAspectRatio,
    setGenImageEditMode,
    setGenImageQuality,
    setGenModal,
    setGenPrompt,
    setGenRefImages,
  ])

  const handleGenImage = useCallback(async () => {
    if (!genPrompt.trim() || !genModal) return
    const selectedModel = imageModels.find(model => model.id === genImgModel)
    const blockReason = getImageRefBlockReason(selectedModel, genRefImages.length, genImageEditMode && genRefImages.length > 0)
    if (blockReason) {
      alert(blockReason)
      return
    }
    setGeneratingImg(true)
    try {
      const imageSize = getImageAspectOption(genImageAspectRatio)
      const imageQuality = normalizeImageQualityForModel(genImageQuality, selectedModel)
      const result = await postImageGeneration({
        project_id: currentProjectId || '',
        prompt: genPrompt,
        provider: genImgProvider,
        model: genImgModel,
        width: imageSize.width,
        height: imageSize.height,
        aspect_ratio: imageSize.id,
        asset_type: genModal.type,
        reference_urls: genRefImages.map(image => image.url),
        edit_mode: genImageEditMode && genRefImages.length > 0,
        image_quality: imageQuality,
        prompt_optimize_mode: 'standard',
      })
      if (result.image_url) {
        const image = {
          url: result.image_url,
          name: genPrompt.slice(0, 20),
          prompt: genPrompt,
          type: genModal.type,
          aspectRatio: imageSize.id,
          width: imageSize.width,
          height: imageSize.height,
          quality: imageQuality,
          ts: Date.now(),
        }
        const addHistory = (scene) => ({ ...scene, imageGenHistory: [...(scene.imageGenHistory || []), image] })
        const nextGen = genScenes.map(scene => scene.id === genModal.sceneId ? addHistory(scene) : scene)
        const nextRepl = replScenes.map(scene => scene.id === genModal.sceneId ? addHistory(scene) : scene)
        setGenScenes(nextGen)
        setReplScenes(nextRepl)
        void runSceneSave(nextGen, nextRepl, currentProjectId)
      }
    } catch (e) {
      alert('生成失败: ' + getFriendlyImageError(e))
    } finally {
      setGeneratingImg(false)
    }
  }, [
    currentProjectId,
    genImageAspectRatio,
    genImageEditMode,
    genImageQuality,
    genImgModel,
    genImgProvider,
    genModal,
    genPrompt,
    genRefImages,
    genScenes,
    getFriendlyImageError,
    imageModels,
    postImageGeneration,
    replScenes,
    runSceneSave,
    setGeneratingImg,
    setGenScenes,
    setReplScenes,
  ])

  const closeGenModal = useCallback(() => {
    setGenModal(null)
  }, [setGenModal])

  const handleGenModalModelChange = useCallback((modelId) => {
    setGenImgModel(modelId)
    const model = imageModels.find(item => item.id === modelId)
    if (model) {
      setGenImgProvider(model.provider)
      setGenImageQuality(prev => normalizeImageQualityForModel(prev, model))
    }
  }, [imageModels, setGenImageQuality, setGenImgModel, setGenImgProvider])

  const uploadGenModalReferenceImages = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.multiple = true
    input.onchange = async (event) => {
      const files = Array.from(event.target.files || [])
      const uploaded = await uploadFilesWithFeedback(files, { failureLabel: '参考图上传失败' })
      if (uploaded.length) {
        setGenRefImages(prev => [...prev, ...uploaded])
      }
    }
    input.click()
  }, [setGenRefImages, uploadFilesWithFeedback])

  const removeGenModalReferenceImage = useCallback((index) => {
    setGenRefImages(prev => prev.filter((_, itemIndex) => itemIndex !== index))
  }, [setGenRefImages])

  const addHistoryImageToScene = useCallback((sceneId, image, type) => {
    const updateSceneImages = (scene) => (
      type === 'character'
        ? { ...scene, charImages: scene.charImages.some(item => item.url === image.url) ? scene.charImages : [...scene.charImages, { url: image.url, name: image.name }] }
        : { ...scene, sceneImages: scene.sceneImages.some(item => item.url === image.url) ? scene.sceneImages : [...scene.sceneImages, { url: image.url, name: image.name }] }
    )
    setGenScenes(prev => prev.map(scene => scene.id === sceneId ? updateSceneImages(scene) : scene))
    setReplScenes(prev => prev.map(scene => scene.id === sceneId ? updateSceneImages(scene) : scene))
  }, [setGenScenes, setReplScenes])

  const removeHistoryImage = useCallback((sceneId, index) => {
    const scene = [...genScenes, ...replScenes].find(item => item.id === sceneId)
    const removed = scene?.imageGenHistory?.[index]?.url
    const removeHistory = (item) => ({ ...item, imageGenHistory: (item.imageGenHistory || []).filter((_, itemIndex) => itemIndex !== index) })
    const nextGen = genScenes.map(item => item.id === sceneId ? removeHistory(item) : item)
    const nextRepl = replScenes.map(item => item.id === sceneId ? removeHistory(item) : item)
    setGenScenes(nextGen)
    setReplScenes(nextRepl)
    deleteServerFilesAfterSave(removed, runSceneSave(nextGen, nextRepl, currentProjectId))
  }, [currentProjectId, deleteServerFilesAfterSave, genScenes, replScenes, runSceneSave, setGenScenes, setReplScenes])

  const insertGenModalRefTag = useCallback((type, index) => {
    const label = type === 'character' ? `图片${index + 1}` : `场景图${index + 1}`
    insertTextAtCursor('game-gen-prompt', label, setGenPrompt)
  }, [insertTextAtCursor, setGenPrompt])

  return {
    openGenModal,
    handleGenImage,
    closeGenModal,
    handleGenModalModelChange,
    uploadGenModalReferenceImages,
    removeGenModalReferenceImage,
    addHistoryImageToScene,
    removeHistoryImage,
    insertGenModalRefTag,
  }
}
