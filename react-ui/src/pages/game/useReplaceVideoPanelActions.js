import { useCallback } from 'react'
import {
  getReplaceProviderSpec,
  getReplaceReferenceDurationLimits,
} from './gameVideoModelUtils'

export function useReplaceVideoPanelActions({
  replProvider,
  replHistoryRef,
  replVideoUrl,
  setReplProvider,
  setReplError,
  setReplCharImage,
  setReplRefVideo,
  setReplRefVideoDurationSeconds,
  setReplVideoResolution,
  setReplVideoUrl,
  setReplStatus,
  setReplTaskId,
  setReplStartTime,
  setReplHistory,
  uploadSingleFileWithFeedback,
  validateReferenceVideoUpload,
  persistReplaceVideoState,
}) {
  const handleReplaceProviderChange = useCallback((provider) => {
    setReplProvider(provider)
    setReplError('')
  }, [setReplError, setReplProvider])

  const handleClearReplaceCharacterImage = useCallback(() => {
    setReplCharImage(null)
  }, [setReplCharImage])

  const handleReplaceCharacterFileSelected = useCallback(async (file) => {
    const uploaded = await uploadSingleFileWithFeedback(file, '角色图片上传失败')
    if (uploaded) setReplCharImage(uploaded)
  }, [setReplCharImage, uploadSingleFileWithFeedback])

  const handleClearReplaceReferenceVideo = useCallback(() => {
    setReplRefVideo('')
    setReplRefVideoDurationSeconds(null)
  }, [setReplRefVideo, setReplRefVideoDurationSeconds])

  const handleReplaceReferenceVideoFileSelected = useCallback(async (file) => {
    const uploaded = await uploadSingleFileWithFeedback(file, '参考视频上传失败')
    if (!uploaded) return
    const referenceLimits = getReplaceReferenceDurationLimits(replProvider)
    const accepted = await validateReferenceVideoUpload(uploaded, {
      label: '参考视频',
      minSeconds: referenceLimits.minSeconds,
      maxSeconds: referenceLimits.maxSeconds,
      providerLabel: getReplaceProviderSpec(replProvider).providerLabel,
    })
    if (!accepted) return
    setReplRefVideo(accepted.url)
    setReplRefVideoDurationSeconds(accepted.durationSeconds)
  }, [
    replProvider,
    setReplRefVideo,
    setReplRefVideoDurationSeconds,
    uploadSingleFileWithFeedback,
    validateReferenceVideoUpload,
  ])

  const handleReplaceResolutionChange = useCallback((resolution) => {
    setReplVideoResolution(resolution)
    persistReplaceVideoState({ replVideoResolution: resolution })
  }, [persistReplaceVideoState, setReplVideoResolution])

  const handleResetReplaceResult = useCallback(() => {
    setReplVideoUrl('')
    setReplStatus('idle')
    setReplError('')
    setReplTaskId('')
    setReplStartTime(null)
    persistReplaceVideoState({ replVideoUrl: '', replStatus: 'idle', replError: '', replTaskId: '', replStartTime: null })
  }, [
    persistReplaceVideoState,
    setReplError,
    setReplStartTime,
    setReplStatus,
    setReplTaskId,
    setReplVideoUrl,
  ])

  const handleSelectReplaceHistory = useCallback((item) => {
    setReplVideoUrl(item.url)
    persistReplaceVideoState({ replVideoUrl: item.url })
  }, [persistReplaceVideoState, setReplVideoUrl])

  const handleRemoveReplaceHistoryItem = useCallback((index) => {
    const removed = replHistoryRef.current[index]
    const nextHistory = replHistoryRef.current.filter((_, itemIndex) => itemIndex !== index)
    const shouldClearVideo = replVideoUrl === removed?.url
    const nextVideoUrl = shouldClearVideo ? '' : replVideoUrl
    setReplHistory(nextHistory)
    if (shouldClearVideo) setReplVideoUrl('')
    persistReplaceVideoState({ replHistory: nextHistory, replVideoUrl: nextVideoUrl })
  }, [persistReplaceVideoState, replHistoryRef, replVideoUrl, setReplHistory, setReplVideoUrl])

  return {
    handleReplaceProviderChange,
    handleClearReplaceCharacterImage,
    handleReplaceCharacterFileSelected,
    handleClearReplaceReferenceVideo,
    handleReplaceReferenceVideoFileSelected,
    handleReplaceResolutionChange,
    handleResetReplaceResult,
    handleSelectReplaceHistory,
    handleRemoveReplaceHistoryItem,
  }
}
