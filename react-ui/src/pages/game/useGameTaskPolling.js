import { useCallback, useEffect, useRef } from 'react'
import { api } from '../../services/api'

const isDocumentHidden = () => (
  typeof document !== 'undefined' && document.visibilityState === 'hidden'
)

const randomDelay = (maxJitterMs) => (
  maxJitterMs > 0 ? Math.floor(Math.random() * maxJitterMs) : 0
)

export function useGameTaskPolling({
  intervalMs = 5000,
  pollLimit = 200,
  hiddenIntervalMs = 30000,
  jitterMs = 750,
  maxBackoffMs = 30000,
  onPollingError,
} = {}) {
  const activeTaskUpdatersRef = useRef(new Map())
  const activeTaskPollCountsRef = useRef(new Map())
  const activeTaskPollingRef = useRef(false)
  const pollingTimerRef = useRef(null)
  const immediatePollTimerRef = useRef(null)
  const consecutivePollingErrorsRef = useRef(0)
  const schedulePollingLoopRef = useRef(null)

  const stopPollingLoop = useCallback(() => {
    if (pollingTimerRef.current) {
      window.clearTimeout(pollingTimerRef.current)
      pollingTimerRef.current = null
    }
  }, [])

  const clearTaskPolling = useCallback((taskId) => {
    activeTaskUpdatersRef.current.delete(taskId)
    activeTaskPollCountsRef.current.delete(taskId)
    if (activeTaskUpdatersRef.current.size === 0) {
      stopPollingLoop()
    }
  }, [stopPollingLoop])

  const nextVisiblePollDelay = useCallback(() => {
    const errorCount = consecutivePollingErrorsRef.current
    const backoffMs = errorCount > 0
      ? Math.min(maxBackoffMs, intervalMs * (2 ** Math.min(errorCount, 4)))
      : intervalMs
    return backoffMs + randomDelay(jitterMs)
  }, [intervalMs, jitterMs, maxBackoffMs])

  const pollActiveTasks = useCallback(async () => {
    const taskIds = [...activeTaskUpdatersRef.current.keys()]
    if (!taskIds.length) return
    if (activeTaskPollingRef.current) {
      schedulePollingLoopRef.current?.(1000 + randomDelay(jitterMs))
      return
    }
    if (isDocumentHidden()) {
      schedulePollingLoopRef.current?.(hiddenIntervalMs + randomDelay(jitterMs))
      return
    }

    const pendingTaskIds = []
    for (const taskId of taskIds) {
      const polls = (activeTaskPollCountsRef.current.get(taskId) || 0) + 1
      activeTaskPollCountsRef.current.set(taskId, polls)
      if (polls > pollLimit) {
        const updater = activeTaskUpdatersRef.current.get(taskId)
        const timeoutMinutes = Math.max(1, Math.round((pollLimit * intervalMs) / 60000))
        updater?.({
          status: 'failed',
          error: `轮询超时（约 ${timeoutMinutes} 分钟），请刷新页面或重试`,
          taskId: '',
          startTime: null,
        })
        clearTaskPolling(taskId)
        continue
      }
      pendingTaskIds.push(taskId)
    }
    if (!pendingTaskIds.length) return

    activeTaskPollingRef.current = true
    try {
      const result = await api.post('/api/game/tasks/status/batch', { task_ids: pendingTaskIds })
      consecutivePollingErrorsRef.current = 0
      const tasks = result?.tasks || {}
      for (const taskId of pendingTaskIds) {
        const updater = activeTaskUpdatersRef.current.get(taskId)
        if (!updater) continue
        const task = tasks[taskId]
        if (!task) continue
        const status = String(task.status || '').toLowerCase()
        const progress = task.progress ?? task.progress_percent ?? task.percent ?? null
        const message = task.message || task.status_text || task.detail || ''

        if (status === 'completed' || status === 'succeeded' || status === 'success') {
          const videoUrl = task.video_url || ''
          if (!videoUrl) {
            updater({
              status: 'failed',
              error: task.error || '任务已完成但未返回视频地址',
              progress: progress ?? 1,
              message,
              startTime: null,
            })
          } else {
            updater({
              status: 'completed',
              videoUrl,
              error: '',
              progress: progress ?? 1,
              message,
              startTime: null,
            })
          }
          clearTaskPolling(taskId)
          continue
        }

        if (status === 'failed' || status === 'expired' || status === 'cancelled' || status === 'canceled') {
          updater({
            status: 'failed',
            error: task.error || '生成失败',
            progress,
            message,
            startTime: null,
          })
          clearTaskPolling(taskId)
          continue
        }

        updater({
          status: status || 'processing',
          progress,
          message,
          taskId,
        })
      }
    } catch (error) {
      consecutivePollingErrorsRef.current += 1
      if (consecutivePollingErrorsRef.current >= 3) {
        for (const taskId of pendingTaskIds) {
          const updater = activeTaskUpdatersRef.current.get(taskId)
          updater?.({
            status: 'failed',
            error: '任务状态轮询连续失败，请稍后重试',
            startTime: null,
          })
          clearTaskPolling(taskId)
        }
      }
      onPollingError?.(error)
    } finally {
      activeTaskPollingRef.current = false
      if (activeTaskUpdatersRef.current.size === 0) {
        stopPollingLoop()
      } else {
        schedulePollingLoopRef.current?.()
      }
    }
  }, [clearTaskPolling, hiddenIntervalMs, intervalMs, jitterMs, onPollingError, pollLimit, stopPollingLoop])

  const schedulePollingLoop = useCallback((delayOverride = null) => {
    if (pollingTimerRef.current || activeTaskUpdatersRef.current.size === 0) return
    const delay = delayOverride == null ? nextVisiblePollDelay() : delayOverride
    pollingTimerRef.current = window.setTimeout(() => {
      pollingTimerRef.current = null
      void pollActiveTasks()
    }, Math.max(250, delay))
  }, [nextVisiblePollDelay, pollActiveTasks])

  schedulePollingLoopRef.current = schedulePollingLoop

  const ensurePollingLoop = useCallback(() => {
    schedulePollingLoop()
  }, [schedulePollingLoop])

  const scheduleImmediatePoll = useCallback(() => {
    if (immediatePollTimerRef.current) return
    immediatePollTimerRef.current = window.setTimeout(() => {
      immediatePollTimerRef.current = null
      pollActiveTasks()
    }, 250 + randomDelay(Math.min(jitterMs, 500)))
  }, [jitterMs, pollActiveTasks])

  const clearAllTaskPolling = useCallback(() => {
    stopPollingLoop()
    if (immediatePollTimerRef.current) {
      window.clearTimeout(immediatePollTimerRef.current)
      immediatePollTimerRef.current = null
    }
    activeTaskUpdatersRef.current.clear()
    activeTaskPollCountsRef.current.clear()
    consecutivePollingErrorsRef.current = 0
  }, [stopPollingLoop])

  const registerTaskPolling = useCallback((taskId, updater) => {
    const hadTask = activeTaskUpdatersRef.current.has(taskId)
    const wasIdle = activeTaskUpdatersRef.current.size === 0
    activeTaskUpdatersRef.current.set(taskId, updater)
    if (!hadTask) {
      activeTaskPollCountsRef.current.set(taskId, 0)
    }
    ensurePollingLoop()
    if (wasIdle || !hadTask) {
      scheduleImmediatePoll()
    }
  }, [ensurePollingLoop, scheduleImmediatePoll])

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return
      if (activeTaskUpdatersRef.current.size === 0) return
      stopPollingLoop()
      scheduleImmediatePoll()
      ensurePollingLoop()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [ensurePollingLoop, scheduleImmediatePoll, stopPollingLoop])

  useEffect(() => () => {
    clearAllTaskPolling()
  }, [clearAllTaskPolling])

  return { registerTaskPolling, clearAllTaskPolling }
}
