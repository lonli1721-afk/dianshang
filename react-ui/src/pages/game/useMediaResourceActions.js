import { useCallback, useEffect, useRef } from 'react'
import { api } from '../../services/api'
import { logGamePageError } from './gameVideoPageHelpers'

const MEDIA_INFO_LOOKUP_DELAY_MS = 250
const MEDIA_INFO_LOOKUP_JITTER_MS = 500
const MEDIA_INFO_MAX_CONCURRENT = 1

const isDocumentHidden = () => (
  typeof document !== 'undefined' && document.visibilityState === 'hidden'
)

const scheduleDelay = (callback, delay) => {
  if (typeof window !== 'undefined') return window.setTimeout(callback, delay)
  return setTimeout(callback, delay)
}

const clearScheduledDelay = (timer) => {
  if (!timer) return
  if (typeof window !== 'undefined') {
    window.clearTimeout(timer)
  } else {
    clearTimeout(timer)
  }
}

export function useMediaResourceActions({ projectId }) {
  const videoDurationLookupsRef = useRef(new Map())
  const durationLookupQueueRef = useRef([])
  const durationLookupActiveRef = useRef(0)
  const durationLookupTimerRef = useRef(null)
  const durationLookupDrainRef = useRef(null)
  const pendingDeleteEntriesRef = useRef(new Map())
  const flushDeletePromiseRef = useRef(null)

  const getDeletableFileUrls = useCallback((urls) => (
    (Array.isArray(urls) ? urls : [urls])
      .filter(Boolean)
      .filter(url => typeof url === 'string' && url.includes('/api/files/'))
  ), [])

  const normalizeDurationSeconds = useCallback((value) => (
    typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
  ), [])

  const formatDurationSeconds = useCallback((value) => {
    const normalized = normalizeDurationSeconds(value)
    return normalized == null ? '' : `${normalized.toFixed(1)} 秒`
  }, [normalizeDurationSeconds])

  const drainDurationLookupQueue = useCallback(() => {
    if (durationLookupTimerRef.current) return
    if (durationLookupActiveRef.current >= MEDIA_INFO_MAX_CONCURRENT) return
    if (durationLookupQueueRef.current.length === 0) return

    const delay = MEDIA_INFO_LOOKUP_DELAY_MS + Math.floor(Math.random() * MEDIA_INFO_LOOKUP_JITTER_MS)
    durationLookupTimerRef.current = scheduleDelay(() => {
      durationLookupTimerRef.current = null
      if (isDocumentHidden()) {
        return
      }
      const entry = durationLookupQueueRef.current.shift()
      if (!entry) return

      durationLookupActiveRef.current += 1
      api.post('/api/game/media_info', { url: entry.url })
        .then(result => normalizeDurationSeconds(result?.duration_seconds))
        .then(entry.resolve)
        .catch((error) => {
          videoDurationLookupsRef.current.delete(entry.url)
          entry.reject(error)
        })
        .finally(() => {
          durationLookupActiveRef.current = Math.max(0, durationLookupActiveRef.current - 1)
          durationLookupDrainRef.current?.()
        })
    }, delay)
  }, [normalizeDurationSeconds])

  durationLookupDrainRef.current = drainDurationLookupQueue

  const fetchMissingVideoDuration = useCallback((url, onDuration) => {
    if (!url) return
    if (!videoDurationLookupsRef.current.has(url)) {
      const promise = new Promise((resolve, reject) => {
        durationLookupQueueRef.current.push({ url, resolve, reject })
        durationLookupDrainRef.current?.()
      })
      videoDurationLookupsRef.current.set(url, promise)
    }
    void videoDurationLookupsRef.current.get(url)
      .then((result) => {
        if (result != null) onDuration(result)
      })
      .catch((error) => {
        videoDurationLookupsRef.current.delete(url)
        logGamePageError(`mediaInfo:${url}`, error)
      })
  }, [])

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') durationLookupDrainRef.current?.()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [])

  useEffect(() => () => {
    clearScheduledDelay(durationLookupTimerRef.current)
    durationLookupTimerRef.current = null
    durationLookupQueueRef.current.length = 0
  }, [])

  const deleteServerFilesForProject = useCallback(async (urls, deleteProjectId = '') => {
    const list = getDeletableFileUrls(urls)
    if (!list.length) return true
    try {
      await api.post('/api/game/files/delete', {
        urls: [...new Set(list)],
        project_id: deleteProjectId || '',
      })
      return true
    } catch (e) {
      logGamePageError('deleteServerFiles', e)
      return false
    }
  }, [getDeletableFileUrls])

  const deleteServerFiles = useCallback((urls) => (
    deleteServerFilesForProject(urls, projectId || '')
  ), [deleteServerFilesForProject, projectId])

  const queueServerFilesForDeletion = useCallback((urls) => {
    const projectKey = projectId || ''
    let queued = 0
    for (const url of getDeletableFileUrls(urls)) {
      const key = `${projectKey}\n${url}`
      if (!pendingDeleteEntriesRef.current.has(key)) {
        pendingDeleteEntriesRef.current.set(key, { projectId: projectKey, url, ready: false })
      }
      queued += 1
    }
    return queued
  }, [getDeletableFileUrls, projectId])

  const markQueuedServerFilesReady = useCallback((urls = null, readyProjectId = null) => {
    const urlSet = urls == null ? null : new Set(getDeletableFileUrls(urls))
    const projectKey = readyProjectId == null ? null : readyProjectId || ''
    let marked = 0
    for (const entry of pendingDeleteEntriesRef.current.values()) {
      if (urlSet && !urlSet.has(entry.url)) continue
      if (projectKey != null && entry.projectId !== projectKey) continue
      entry.ready = true
      marked += 1
    }
    return marked
  }, [getDeletableFileUrls])

  const flushReadyServerFileDeletes = useCallback(async (projectIdFilter = null) => {
    if (flushDeletePromiseRef.current) return flushDeletePromiseRef.current

    const runFlush = async () => {
      const projectKey = projectIdFilter == null ? null : projectIdFilter || ''
      let allOk = true
      while (true) {
        const readyEntries = [...pendingDeleteEntriesRef.current.entries()]
          .filter(([, entry]) => entry.ready && (projectKey == null || entry.projectId === projectKey))
        if (!readyEntries.length) return allOk

        const groups = new Map()
        for (const [key, entry] of readyEntries) {
          if (!groups.has(entry.projectId)) groups.set(entry.projectId, [])
          groups.get(entry.projectId).push({ key, url: entry.url })
        }

        for (const [deleteProjectId, entries] of groups.entries()) {
          const ok = await deleteServerFilesForProject(entries.map(entry => entry.url), deleteProjectId)
          if (ok) {
            for (const entry of entries) pendingDeleteEntriesRef.current.delete(entry.key)
          } else {
            allOk = false
          }
        }

        if (!allOk) return false
      }
    }

    flushDeletePromiseRef.current = runFlush().finally(() => {
      flushDeletePromiseRef.current = null
    })
    return flushDeletePromiseRef.current
  }, [deleteServerFilesForProject])

  const flushQueuedServerFileDeletes = useCallback((savedProjectId = projectId || '') => {
    markQueuedServerFilesReady(null, savedProjectId || '')
    return flushReadyServerFileDeletes(savedProjectId || '')
  }, [flushReadyServerFileDeletes, markQueuedServerFilesReady, projectId])

  const deleteServerFilesAfterSave = useCallback((urls, savePromise) => {
    if (!queueServerFilesForDeletion(urls)) return
    void Promise.resolve(savePromise)
      .then((saved) => {
        if (saved) {
          markQueuedServerFilesReady(urls)
          return flushReadyServerFileDeletes()
        }
        return false
      })
      .catch((error) => {
        logGamePageError('deleteServerFilesAfterSave', error)
      })
  }, [flushReadyServerFileDeletes, markQueuedServerFilesReady, queueServerFilesForDeletion])

  return {
    normalizeDurationSeconds,
    formatDurationSeconds,
    fetchMissingVideoDuration,
    deleteServerFiles,
    deleteServerFilesAfterSave,
    flushQueuedServerFileDeletes,
  }
}
