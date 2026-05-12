import { useCallback } from 'react'
import { getErrorMessage } from './gameVideoPageHelpers'
import {
  getVideoMaxReferenceVideos,
  getVideoReferenceDurationLimits,
  getVideoReferenceProviderLabel,
} from './gameVideoModelUtils'

export function useSceneMediaActions({
  scenes,
  models,
  updateScene,
  setGenScenes,
  setReplScenes,
  uploadGameFile,
  uploadFilesWithFeedback,
  uploadSingleFileWithFeedback,
  validateReferenceVideoUpload,
  deleteServerFilesAfterSave,
}) {
  const uploadImageToScene = useCallback((sceneId, type, folder = false) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.multiple = true
    if (folder) input.webkitdirectory = true
    input.onchange = async (event) => {
      const files = Array.from(event.target.files).filter(file => file.type.startsWith('image/'))
      if (!files.length) return
      const newImages = await uploadFilesWithFeedback(files, { failureLabel: '图片上传失败' })
      if (!newImages.length) return
      const updateImages = (scene) => (
        type === 'character'
          ? { ...scene, charImages: [...scene.charImages, ...newImages] }
          : { ...scene, sceneImages: [...scene.sceneImages, ...newImages] }
      )
      setGenScenes(prev => prev.map(scene => scene.id === sceneId ? updateImages(scene) : scene))
      setReplScenes(prev => prev.map(scene => scene.id === sceneId ? updateImages(scene) : scene))
    }
    input.click()
  }, [setGenScenes, setReplScenes, uploadFilesWithFeedback])

  const removeImageFromScene = useCallback((sceneId, type, idx) => {
    const updateImages = (scene) => (
      type === 'character'
        ? { ...scene, charImages: scene.charImages.filter((_, index) => index !== idx) }
        : { ...scene, sceneImages: scene.sceneImages.filter((_, index) => index !== idx) }
    )
    setGenScenes(prev => prev.map(scene => scene.id === sceneId ? updateImages(scene) : scene))
    setReplScenes(prev => prev.map(scene => scene.id === sceneId ? updateImages(scene) : scene))
  }, [setGenScenes, setReplScenes])

  const uploadRefVideoToScene = useCallback((sceneId) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'video/*'
    input.onchange = async (event) => {
      const file = event.target.files[0]
      if (!file) return
      try {
        const result = await uploadGameFile(file)
        const scene = scenes.find(item => item.id === sceneId)
        const selectedModel = models.find(item => item.id === scene?.model)
        const referenceLimits = getVideoReferenceDurationLimits(selectedModel)
        const uploaded = await validateReferenceVideoUpload({
          url: result.url,
          durationSeconds: result.durationSeconds,
        }, {
          label: '参考视频',
          minSeconds: referenceLimits.minSeconds,
          maxSeconds: referenceLimits.maxSeconds,
          providerLabel: getVideoReferenceProviderLabel(selectedModel),
        })
        if (!uploaded) return
        updateScene(sceneId, {
          refVideoUrl: uploaded.url,
          refVideoDurationSeconds: uploaded.durationSeconds,
        })
      } catch (e) {
        alert('上传失败: ' + getErrorMessage(e, '上传失败'))
      }
    }
    input.click()
  }, [models, scenes, updateScene, uploadGameFile, validateReferenceVideoUpload])

  const uploadAdvancedVideosToScene = useCallback((sceneId) => {
    const scene = scenes.find(item => item.id === sceneId)
    const selectedModel = models.find(item => item.id === scene?.model)
    const maxAdvancedVideos = getVideoMaxReferenceVideos(selectedModel) || 1
    const currentCount = scene?.advancedRefVideos?.length || 0
    if (currentCount >= maxAdvancedVideos) {
      alert(`当前模型最多支持 ${maxAdvancedVideos} 个参考视频`)
      return
    }
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'video/*'
    input.multiple = true
    input.onchange = async (event) => {
      const files = Array.from(event.target.files || []).slice(0, maxAdvancedVideos - currentCount)
      if (!files.length) return
      const uploaded = []
      for (const file of files) {
        const result = await uploadSingleFileWithFeedback(file, '高级参考视频上传失败')
        const referenceLimits = getVideoReferenceDurationLimits(selectedModel)
        const accepted = await validateReferenceVideoUpload(result, {
          label: '高级参考视频',
          minSeconds: referenceLimits.minSeconds,
          maxSeconds: referenceLimits.maxSeconds,
          providerLabel: getVideoReferenceProviderLabel(selectedModel),
        })
        if (accepted) uploaded.push(accepted)
      }
      if (!uploaded.length) return
      const latestScene = scenes.find(item => item.id === sceneId) || scene
      updateScene(sceneId, {
        advancedRefVideos: [...(latestScene?.advancedRefVideos || []), ...uploaded].slice(0, maxAdvancedVideos),
      })
    }
    input.click()
  }, [models, scenes, updateScene, uploadSingleFileWithFeedback, validateReferenceVideoUpload])

  const removeAdvancedVideoFromScene = useCallback((sceneId, index) => {
    const scene = scenes.find(item => item.id === sceneId)
    const removed = scene?.advancedRefVideos?.[index]?.url
    deleteServerFilesAfterSave(removed, updateScene(sceneId, {
      advancedRefVideos: (scene?.advancedRefVideos || []).filter((_, itemIndex) => itemIndex !== index),
    }, { saveImmediately: true }))
  }, [deleteServerFilesAfterSave, scenes, updateScene])

  return {
    uploadImageToScene,
    removeImageFromScene,
    uploadRefVideoToScene,
    uploadAdvancedVideosToScene,
    removeAdvancedVideoFromScene,
  }
}
