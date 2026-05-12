import { useCallback } from 'react'
import { api } from '../../services/api'
import { getErrorMessage } from './gameVideoPageHelpers'

export function useReverseVideoActions({
  reverseVideoUrl,
  reverseModel,
  reverseResult,
  uploadGameFile,
  setReverseVideoUrl,
  setReverseVideoDurationSeconds,
  setReverseModel,
  setReverseResult,
  setReverseLoading,
  setReverseHistory,
}) {
  const handleReverseVideo = useCallback(async () => {
    if (!reverseVideoUrl) { alert('请先上传参考视频'); return }
    setReverseLoading(true)
    setReverseResult('')
    try {
      const d = await api.post('/api/game/analyze_video', {
        video_url: reverseVideoUrl, model: reverseModel,
      })
      const text = d.prompt || '未能生成提示词'
      setReverseResult(text)
      setReverseHistory(prev => [{
        video_url: reverseVideoUrl, model: reverseModel, result: text, ts: Date.now(),
      }, ...prev])
    } catch (e) { alert('分析失败: ' + getErrorMessage(e, '分析失败')) }
    finally { setReverseLoading(false) }
  }, [reverseModel, reverseVideoUrl, setReverseHistory, setReverseLoading, setReverseResult])

  const uploadReverseVideo = useCallback(() => {
    const input = document.createElement('input'); input.type = 'file'; input.accept = 'video/*'
    input.onchange = async (e) => {
      const file = e.target.files[0]; if (!file) return
      try {
        const r = await uploadGameFile(file)
        setReverseVideoUrl(r.url)
        setReverseVideoDurationSeconds(r.durationSeconds)
      }
      catch (e) { alert('上传失败: ' + getErrorMessage(e, '上传失败')) }
    }; input.click()
  }, [setReverseVideoDurationSeconds, setReverseVideoUrl, uploadGameFile])

  const handleClearReverseVideo = useCallback(() => {
    setReverseVideoUrl('')
    setReverseVideoDurationSeconds(null)
  }, [setReverseVideoDurationSeconds, setReverseVideoUrl])

  const handleCopyReverseResult = useCallback(() => {
    void navigator.clipboard.writeText(reverseResult)
  }, [reverseResult])

  const handleSelectReverseHistory = useCallback((item) => {
    setReverseVideoUrl(item.video_url)
    setReverseModel(item.model)
    setReverseResult(item.result)
  }, [setReverseModel, setReverseResult, setReverseVideoUrl])

  const handleRemoveReverseHistoryItem = useCallback((idx) => {
    setReverseHistory(prev => prev.filter((_, i) => i !== idx))
  }, [setReverseHistory])

  return {
    handleReverseVideo,
    uploadReverseVideo,
    handleClearReverseVideo,
    handleCopyReverseResult,
    handleSelectReverseHistory,
    handleRemoveReverseHistoryItem,
  }
}
