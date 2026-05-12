import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../services/api'
import {
  getErrorMessage,
  logGamePageError,
  serializeScenes,
} from './gameVideoPageHelpers'
import { SCENE_AUTOSAVE_DEBOUNCE_MS } from './gameVideoConstants'

export function useSceneAutosave({
  currentProject,
  genScenes,
  replScenes,
  tabState,
  tabStateRef,
  onSaveSuccess,
}) {
  const [saveStatus, setSaveStatus] = useState('idle')
  const [saveError, setSaveError] = useState('')

  const latestSaveTokenRef = useRef(0)
  const saveChainRef = useRef(Promise.resolve(false))
  const skipAutosaveOnceRef = useRef(false)
  const isHydratingProjectRef = useRef(false)
  const loadedProjectRef = useRef(null)
  const lastSavedPayloadRef = useRef({ projectId: '', key: '' })

  const beginProjectHydration = useCallback((projectId) => {
    latestSaveTokenRef.current += 1
    isHydratingProjectRef.current = true
    loadedProjectRef.current = projectId
    lastSavedPayloadRef.current = { projectId: projectId || '', key: '' }
    setSaveStatus('idle')
    setSaveError('')
  }, [])

  const finishProjectHydration = useCallback(() => {
    isHydratingProjectRef.current = false
  }, [])

  const saveAllScenesToServer = useCallback(async (gen, repl, projectId, tabStateOverride = null) => {
    if (!projectId) return { ok: false, skipped: true, error: '' }
    const payload = {
      generate: serializeScenes(gen),
      replace: serializeScenes(repl),
      tabState: tabStateOverride || tabStateRef.current,
    }
    const payloadKey = JSON.stringify(payload)
    if (
      lastSavedPayloadRef.current.projectId === projectId
      && lastSavedPayloadRef.current.key === payloadKey
    ) {
      return { ok: true, skipped: true, unchanged: true, error: '' }
    }
    try {
      await api.put(`/api/game/projects/${projectId}/scenes`, { scenes: payload })
      lastSavedPayloadRef.current = { projectId, key: payloadKey }
      return { ok: true, error: '' }
    } catch (e) {
      logGamePageError(`saveScenes:${projectId}`, e)
      return { ok: false, error: getErrorMessage(e, '自动保存失败') }
    }
  }, [tabStateRef])

  const beginSceneSave = useCallback(() => {
    const token = latestSaveTokenRef.current + 1
    latestSaveTokenRef.current = token
    setSaveStatus('saving')
    return token
  }, [])

  const finishSceneSave = useCallback((token, result) => {
    if (latestSaveTokenRef.current !== token) return
    if (result?.skipped) {
      if (result?.unchanged) {
        setSaveStatus('idle')
        setSaveError('')
      }
      return
    }
    if (result?.ok) {
      setSaveStatus('saved')
      setSaveError('')
      return
    }
    setSaveStatus('error')
    setSaveError(result?.error || '自动保存失败')
  }, [])

  const runSceneSave = useCallback(async (gen, repl, projectId, tabStateOverride = null, tokenOverride = null) => {
    const token = tokenOverride ?? beginSceneSave()
    const queued = saveChainRef.current.catch(() => false).then(async () => {
      if (token !== latestSaveTokenRef.current) {
        return false
      }
      const result = await saveAllScenesToServer(gen, repl, projectId, tabStateOverride)
      if (token !== latestSaveTokenRef.current) {
        return false
      }
      if (result?.ok) {
        void onSaveSuccess?.(projectId || '')
      }
      finishSceneSave(token, result)
      return result?.ok === true
    })
    saveChainRef.current = queued
    return queued
  }, [beginSceneSave, finishSceneSave, onSaveSuccess, saveAllScenesToServer])

  const runImmediateSceneSave = useCallback((gen, repl, projectId, tabStateOverride = null) => {
    skipAutosaveOnceRef.current = true
    return runSceneSave(gen, repl, projectId, tabStateOverride)
  }, [runSceneSave])

  useEffect(() => {
    if (!currentProject) return undefined
    if (loadedProjectRef.current !== currentProject.id) return undefined
    if (isHydratingProjectRef.current) return undefined
    if (skipAutosaveOnceRef.current) {
      skipAutosaveOnceRef.current = false
      return undefined
    }
    const saveToken = beginSceneSave()
    const timer = setTimeout(() => {
      void runSceneSave(genScenes, replScenes, currentProject.id, null, saveToken)
    }, SCENE_AUTOSAVE_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [genScenes, replScenes, currentProject, tabState, beginSceneSave, runSceneSave])

  useEffect(() => {
    if (saveStatus !== 'saved') return undefined
    const timer = setTimeout(() => {
      setSaveStatus('idle')
    }, 1500)
    return () => clearTimeout(timer)
  }, [saveStatus])

  return {
    saveStatus,
    saveError,
    loadedProjectRef,
    beginProjectHydration,
    finishProjectHydration,
    runSceneSave,
    runImmediateSceneSave,
  }
}
