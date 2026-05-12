import { useCallback } from 'react'

export function useSceneVideoHistoryActions({
  currentProjectId,
  genScenes,
  replScenes,
  genScenesRef,
  replScenesRef,
  setGenScenes,
  setReplScenes,
  updateScene,
  runImmediateSceneSave,
  deleteServerFilesAfterSave,
}) {
  const selectHistoryVideo = useCallback((sceneId, histIdx) => {
    const doSwap = (scene) => {
      const history = [...(scene.videoHistory || [])]
      const picked = history[histIdx]
      if (!picked) return scene
      const nextHistory = history.filter((_, index) => index !== histIdx)
      if (scene.videoUrl) {
        nextHistory.push({ url: scene.videoUrl, prompt: scene.prompt, model: scene.model, ts: Date.now() })
      }
      return { ...scene, videoUrl: picked.url, videoHistory: nextHistory }
    }
    const nextGen = genScenesRef.current.map(scene => (scene.id === sceneId ? doSwap(scene) : scene))
    const nextRepl = replScenesRef.current.map(scene => (scene.id === sceneId ? doSwap(scene) : scene))
    genScenesRef.current = nextGen
    replScenesRef.current = nextRepl
    setGenScenes(nextGen)
    setReplScenes(nextRepl)
    void runImmediateSceneSave(nextGen, nextRepl, currentProjectId)
  }, [
    currentProjectId,
    genScenesRef,
    replScenesRef,
    runImmediateSceneSave,
    setGenScenes,
    setReplScenes,
  ])

  const removeHistoryVideo = useCallback((sceneId, histIdx) => {
    const scene = [...genScenes, ...replScenes].find(item => item.id === sceneId)
    const removed = scene?.videoHistory?.[histIdx]?.url
    const removeAtIndex = item => ({
      ...item,
      videoHistory: (item.videoHistory || []).filter((_, index) => index !== histIdx),
    })
    const nextGen = genScenesRef.current.map(item => (item.id === sceneId ? removeAtIndex(item) : item))
    const nextRepl = replScenesRef.current.map(item => (item.id === sceneId ? removeAtIndex(item) : item))
    genScenesRef.current = nextGen
    replScenesRef.current = nextRepl
    setGenScenes(nextGen)
    setReplScenes(nextRepl)
    deleteServerFilesAfterSave(removed, runImmediateSceneSave(nextGen, nextRepl, currentProjectId))
  }, [
    currentProjectId,
    deleteServerFilesAfterSave,
    genScenes,
    genScenesRef,
    replScenes,
    replScenesRef,
    runImmediateSceneSave,
    setGenScenes,
    setReplScenes,
  ])

  const removeCurrentVideo = useCallback((sceneId) => {
    const scene = [...genScenes, ...replScenes].find(item => item.id === sceneId)
    const removed = scene?.videoUrl
    deleteServerFilesAfterSave(
      removed,
      updateScene(sceneId, { videoUrl: '', status: 'idle', taskId: '', startTime: null }, { saveImmediately: true }),
    )
  }, [deleteServerFilesAfterSave, genScenes, replScenes, updateScene])

  return {
    selectHistoryVideo,
    removeHistoryVideo,
    removeCurrentVideo,
  }
}
