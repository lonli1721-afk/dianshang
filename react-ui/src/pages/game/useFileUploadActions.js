import { useCallback } from 'react'
import { api } from '../../services/api'
import { getErrorMessage, logGamePageError } from './gameVideoPageHelpers'

export function useFileUploadActions({ normalizeDurationSeconds }) {
  const uploadGameFile = useCallback(async (file) => {
    const result = await api.upload('/api/game/upload', file)
    return {
      url: result.url,
      name: file.name,
      baseName: file.name.replace(/\.[^.]+$/, ''),
      durationSeconds: normalizeDurationSeconds(result.duration_seconds),
      raw: result,
    }
  }, [normalizeDurationSeconds])

  const uploadFilesWithFeedback = useCallback(async (files, { successMessage, failureLabel }) => {
    const uploaded = []
    let failedCount = 0

    for (const file of files) {
      try {
        const result = await uploadGameFile(file)
        uploaded.push({ url: result.url, name: result.baseName })
      } catch (e) {
        failedCount += 1
        logGamePageError(`${failureLabel}:${file.name}`, e)
      }
    }

    if (failedCount > 0) {
      alert(`${failureLabel}：成功 ${uploaded.length} 个，失败 ${failedCount} 个，请重试失败文件`)
    } else if (successMessage && uploaded.length > 0) {
      void successMessage
    }

    return uploaded
  }, [uploadGameFile])

  const uploadSingleFileWithFeedback = useCallback(async (file, failureLabel) => {
    try {
      const result = await uploadGameFile(file)
      return {
        url: result.url,
        name: result.name,
        durationSeconds: result.durationSeconds,
      }
    } catch (e) {
      logGamePageError(`${failureLabel}:${file.name}`, e)
      alert(`${failureLabel}：${getErrorMessage(e, '上传失败')}`)
      return null
    }
  }, [uploadGameFile])

  return {
    uploadGameFile,
    uploadFilesWithFeedback,
    uploadSingleFileWithFeedback,
  }
}
