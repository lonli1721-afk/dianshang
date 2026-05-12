import { useCallback } from 'react'

export function useWorkbenchTabPersistence({
  currentProjectId,
  genScenes,
  replScenes,
  genScenesRef,
  replScenesRef,
  runImmediateSceneSave,
  tabStateRef,
}) {
  const persistStandaloneImageState = useCallback((patch) => {
    const standaloneImage = { ...tabStateRef.current.standaloneImage, ...patch }
    return runImmediateSceneSave(genScenes, replScenes, currentProjectId, {
      ...tabStateRef.current,
      standaloneImage,
    })
  }, [genScenes, replScenes, currentProjectId, runImmediateSceneSave, tabStateRef])

  const persistReplaceVideoState = useCallback((patch) => {
    const replaceVideo = { ...tabStateRef.current.replaceVideo, ...patch }
    return runImmediateSceneSave(genScenesRef.current, replScenesRef.current, currentProjectId, {
      ...tabStateRef.current,
      replaceVideo,
    })
  }, [currentProjectId, genScenesRef, replScenesRef, runImmediateSceneSave, tabStateRef])

  return {
    persistStandaloneImageState,
    persistReplaceVideoState,
  }
}
