import { useCallback } from 'react'
import { api } from '../../services/api'
import { logGamePageError } from './gameVideoPageHelpers'

export function useProjectLoader({
  clearAllTaskPolling,
  beginProjectHydration,
  finishProjectHydration,
  setCurrentProject,
  setGenScenes,
  setReplScenes,
  modelsRef,
  makeInitialScenePair,
  normalizeScenePair,
  applyTabState,
  resumeSceneTaskPolling,
  resumeReplaceTaskPolling,
}) {
  const openProject = useCallback(async (project) => {
    clearAllTaskPolling()
    beginProjectHydration(project.id)
    setCurrentProject(project)
    try {
      const saved = await api.get(`/api/game/projects/${project.id}/scenes`)
      const data = Array.isArray(saved) ? saved : (saved || {})
      const gen = Array.isArray(data) ? data : (Array.isArray(data.generate) ? data.generate : [])
      const repl = Array.isArray(data) ? [] : (Array.isArray(data.replace) ? data.replace : [])
      const normalized = normalizeScenePair(gen, repl, modelsRef.current)
      setGenScenes(normalized.gen)
      setReplScenes(normalized.repl)
      const parsedTabState = applyTabState(!Array.isArray(data) ? data.tabState : null)
      normalized.gen.forEach((scene) => {
        resumeSceneTaskPolling(scene)
      })
      resumeReplaceTaskPolling(parsedTabState?.replaceVideo)
    } catch (e) {
      logGamePageError(`openProject:${project.id}`, e)
      const initial = makeInitialScenePair(modelsRef.current)
      setGenScenes(initial.gen)
      setReplScenes(initial.repl)
      applyTabState(null)
    } finally {
      finishProjectHydration()
    }
  }, [
    clearAllTaskPolling,
    beginProjectHydration,
    finishProjectHydration,
    setCurrentProject,
    setGenScenes,
    setReplScenes,
    modelsRef,
    makeInitialScenePair,
    normalizeScenePair,
    applyTabState,
    resumeSceneTaskPolling,
    resumeReplaceTaskPolling,
  ])

  return { openProject }
}
