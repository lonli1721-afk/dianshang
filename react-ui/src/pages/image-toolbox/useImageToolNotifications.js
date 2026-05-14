import { useCallback, useState } from 'react'
import { noticeToneFromMessage } from './helpers'

export function useImageToolNotifications() {
  const [globalNotice, setGlobalNotice] = useState(null)
  const [taskNotice, setTaskNotice] = useState(null)
  const [toasts, setToasts] = useState([])

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(item => item.id !== id))
  }, [])

  const notify = useCallback((event = {}) => {
    const payload = typeof event === 'string' ? { message: event } : event
    const message = payload.message || ''
    if (!message) return
    const tone = payload.tone || noticeToneFromMessage(message)
    if (payload.scope === 'global') {
      setGlobalNotice({ tone, message })
      return
    }
    if (payload.scope === 'task') setTaskNotice({ tone, message })
    const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`
    setToasts(prev => [...prev.slice(-3), { id, tone, message }])
    window.setTimeout(() => dismissToast(id), 3600)
  }, [dismissToast])

  const taskNotify = useCallback((message) => {
    if (!message) {
      setTaskNotice(null)
      return
    }
    notify({ scope: 'task', message, tone: noticeToneFromMessage(message, 'error') })
  }, [notify])

  const uploadNotify = useCallback((message) => {
    if (message) notify({ scope: 'toast', message })
  }, [notify])

  return {
    globalNotice,
    taskNotice,
    toasts,
    notify,
    taskNotify,
    uploadNotify,
    dismissToast,
    clearGlobalNotice: () => setGlobalNotice(null),
  }
}
