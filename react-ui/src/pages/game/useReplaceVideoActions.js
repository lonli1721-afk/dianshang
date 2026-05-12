import { useCallback, useMemo } from 'react'
import { api } from '../../services/api'
import { getErrorMessage } from './gameVideoPageHelpers'
import { getReplaceVideoBlockReason as getReplaceVideoBlockReasonForProvider } from './gameVideoModelUtils'

export function useReplaceVideoActions({
  currentProjectId,
  replCharImage,
  replRefVideo,
  replRefVideoDurationSeconds,
  replPrompt,
  replProvider,
  replWanMode,
  replWanCheckImage,
  replVideoResolution,
  setReplStatus,
  setReplError,
  setReplTaskId,
  setReplStartTime,
  persistReplaceVideoState,
  resumeReplaceTaskPolling,
  formatDurationSeconds,
  normalizeDurationSeconds,
}) {
  const getReplaceVideoBlockReason = useCallback(() => {
    return getReplaceVideoBlockReasonForProvider(replProvider, {
      charImage: replCharImage,
      refVideo: replRefVideo,
      refVideoDurationSeconds: replRefVideoDurationSeconds,
    }, {
      formatDurationSeconds,
      normalizeDurationSeconds,
    })
  }, [
    formatDurationSeconds,
    normalizeDurationSeconds,
    replCharImage,
    replProvider,
    replRefVideo,
    replRefVideoDurationSeconds,
  ])

  const replaceBlockReason = useMemo(() => getReplaceVideoBlockReason(), [getReplaceVideoBlockReason])

  const handleReplaceVideo = useCallback(async () => {
    if (!replCharImage || !replRefVideo) return
    const blockReason = getReplaceVideoBlockReason()
    if (blockReason) {
      setReplError(blockReason)
      setReplStatus('failed')
      setReplTaskId('')
      persistReplaceVideoState({ replStatus: 'failed', replError: blockReason, replTaskId: '' })
      return
    }
    setReplStatus('processing')
    setReplError('')
    setReplTaskId('')
    const nextStartTime = Date.now()
    setReplStartTime(nextStartTime)
    persistReplaceVideoState({ replStatus: 'processing', replError: '', replTaskId: '', replStartTime: nextStartTime })
    try {
      const result = await api.post('/api/game/replace_video', {
        project_id: currentProjectId || '',
        ref_video_url: replRefVideo,
        character_ref: replCharImage.url,
        prompt: replPrompt,
        provider: replProvider,
        mode: replProvider === 'wan' ? replWanMode : '',
        check_image: replProvider === 'wan' ? replWanCheckImage : false,
        resolution: replProvider === 'jimeng' ? replVideoResolution : '720p',
      })
      if (result.task_record_warning) alert(result.task_record_warning)
      if (result.task_id) {
        setReplTaskId(result.task_id)
        persistReplaceVideoState({ replTaskId: result.task_id, replStatus: 'processing', replError: '', replStartTime: nextStartTime })
        resumeReplaceTaskPolling({ replTaskId: result.task_id, replStatus: 'processing' })
      }
    } catch (e) {
      const nextError = getErrorMessage(e, '替换失败')
      setReplError(nextError)
      setReplStatus('failed')
      setReplTaskId('')
      persistReplaceVideoState({ replStatus: 'failed', replError: nextError, replTaskId: '' })
    }
  }, [
    currentProjectId,
    getReplaceVideoBlockReason,
    persistReplaceVideoState,
    replCharImage,
    replPrompt,
    replProvider,
    replRefVideo,
    replVideoResolution,
    replWanCheckImage,
    replWanMode,
    resumeReplaceTaskPolling,
    setReplError,
    setReplStartTime,
    setReplStatus,
    setReplTaskId,
  ])

  return {
    replaceBlockReason,
    handleReplaceVideo,
  }
}
