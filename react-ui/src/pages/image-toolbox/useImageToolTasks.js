import { useCallback, useEffect, useMemo, useState } from 'react'
import { cancelImageToolTask, createImageToolTask, deleteImageToolTask, listImageToolTasks } from './imageToolboxApi'
import { displayError } from './helpers'

const ACTIVE_STATUSES = new Set(['queued', 'running'])
const HIDDEN_TASK_IDS_KEY = 'imageToolHiddenTaskIds'

const loadHiddenTaskIds = () => {
  try {
    const parsed = JSON.parse(localStorage.getItem(HIDDEN_TASK_IDS_KEY) || '[]')
    return new Set(Array.isArray(parsed) ? parsed : [])
  } catch {
    return new Set()
  }
}

const saveHiddenTaskIds = (ids) => {
  localStorage.setItem(HIDDEN_TASK_IDS_KEY, JSON.stringify([...ids].slice(-300)))
}

const deleteUnsupported = (error) => {
  const message = displayError(error)
  return message.includes('Method Not Allowed') || message.includes('HTTP 405')
}

export function useImageToolTasks(setNotice) {
  const [tasks, setTasks] = useState([])
  const [hiddenTaskIds, setHiddenTaskIds] = useState(() => loadHiddenTaskIds())
  const [loading, setLoading] = useState(false)

  const hideTaskLocally = useCallback((taskId) => {
    setHiddenTaskIds(prev => {
      const next = new Set(prev)
      next.add(taskId)
      saveHiddenTaskIds(next)
      return next
    })
    setTasks(prev => prev.filter(item => item.task_id !== taskId))
  }, [])

  const refreshTasks = useCallback(async () => {
    try {
      const data = await listImageToolTasks({ limit: 60 })
      setTasks((data.tasks || []).filter(task => !hiddenTaskIds.has(task.task_id)))
    } catch (error) {
      setNotice?.(displayError(error))
    }
  }, [hiddenTaskIds, setNotice])

  useEffect(() => {
    refreshTasks()
  }, [refreshTasks])

  const hasActiveTasks = useMemo(
    () => tasks.some(task => ACTIVE_STATUSES.has(task.status)),
    [tasks],
  )

  useEffect(() => {
    if (!hasActiveTasks) return undefined
    const timer = window.setInterval(refreshTasks, 2500)
    return () => window.clearInterval(timer)
  }, [hasActiveTasks, refreshTasks])

  const submitTask = useCallback(async (type, payload) => {
    setLoading(true)
    try {
      const task = await createImageToolTask({ type, payload })
      setTasks(prev => [task, ...prev.filter(item => item.task_id !== task.task_id)].slice(0, 60))
      window.setTimeout(refreshTasks, 800)
      return task
    } catch (error) {
      setNotice?.(displayError(error))
      throw error
    } finally {
      setLoading(false)
    }
  }, [refreshTasks, setNotice])

  const cancelTask = useCallback(async (taskId) => {
    try {
      const task = await cancelImageToolTask(taskId)
      setTasks(prev => prev.map(item => item.task_id === taskId ? task : item))
      return task
    } catch (error) {
      setNotice?.(displayError(error))
      throw error
    }
  }, [setNotice])

  const deleteTask = useCallback(async (taskId) => {
    try {
      await deleteImageToolTask(taskId)
      setTasks(prev => prev.filter(item => item.task_id !== taskId))
    } catch (error) {
      if (deleteUnsupported(error)) {
        hideTaskLocally(taskId)
        return
      }
      setNotice?.(displayError(error))
      throw error
    }
  }, [hideTaskLocally, setNotice])

  const clearFinishedTasks = useCallback(async () => {
    const finished = tasks.filter(task => !ACTIVE_STATUSES.has(task.status))
    if (!finished.length) return
    const results = await Promise.allSettled(finished.map(task => deleteImageToolTask(task.task_id)))
    const deletedIds = new Set(finished
      .filter((_, index) => results[index].status === 'fulfilled' || deleteUnsupported(results[index].reason))
      .map(task => task.task_id))
    if (deletedIds.size) {
      setHiddenTaskIds(prev => {
        const next = new Set(prev)
        deletedIds.forEach(id => next.add(id))
        saveHiddenTaskIds(next)
        return next
      })
    }
    setTasks(prev => prev.filter(task => !deletedIds.has(task.task_id)))
    const failedCount = results.filter(result => result.status === 'rejected' && !deleteUnsupported(result.reason)).length
    if (failedCount) setNotice?.(`有 ${failedCount} 个任务删除失败，请稍后重试。`)
  }, [setNotice, tasks])

  return { tasks, tasksLoading: loading, hasActiveTasks, submitTask, cancelTask, deleteTask, clearFinishedTasks, refreshTasks }
}
