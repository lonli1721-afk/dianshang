import { useCallback } from 'react'
import { api } from '../../services/api'
import { getErrorMessage } from './gameVideoPageHelpers'
import { buildSceneVideoGenerationPayload } from './sceneVideoGenerationPayload'

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export function useSceneVideoGenerationActions({
  currentProjectId,
  scenes,
  models,
  updateScene,
  registerTaskPolling,
  getSceneGenerationBlockReason,
}) {
  const generateOneScene = useCallback(async (sceneId) => {
    const scene = scenes.find(item => item.id === sceneId)
    if (!scene) return
    const selectedModel = models.find(item => item.id === scene.model)
    const provider = selectedModel?.provider || scene.provider || 'jimeng'
    const blockReason = getSceneGenerationBlockReason(scene)
    if (blockReason) {
      alert(blockReason)
      return
    }
    const prevHistory = [...(scene.videoHistory || [])]
    if (scene.videoUrl) {
      prevHistory.push({ url: scene.videoUrl, prompt: scene.prompt, model: scene.model, ts: Date.now() })
    }
    updateScene(
      sceneId,
      { status: 'generating', videoUrl: '', error: '', startTime: Date.now(), videoHistory: prevHistory },
      { saveImmediately: true },
    )
    try {
      const body = buildSceneVideoGenerationPayload({
        currentProjectId,
        scene,
        selectedModel,
        provider,
      })
      const result = await api.post('/api/game/generate_video', body)
      if (result.task_record_warning) alert(result.task_record_warning)
      if (result.task_id) {
        updateScene(
          sceneId,
          { provider, taskId: result.task_id, status: 'processing' },
          { saveImmediately: true },
        )
        registerTaskPolling(result.task_id, (updates) => updateScene(
          sceneId,
          updates,
          { saveImmediately: updates.status === 'completed' || updates.status === 'failed' },
        ))
      }
    } catch (error) {
      updateScene(
        sceneId,
        { status: 'failed', error: getErrorMessage(error, '生成失败') },
        { saveImmediately: true },
      )
    }
  }, [
    currentProjectId,
    getSceneGenerationBlockReason,
    models,
    registerTaskPolling,
    scenes,
    updateScene,
  ])

  const generateAll = useCallback(async () => {
    const pending = scenes.filter(scene => scene.status !== 'processing' && scene.status !== 'generating')
    const runnable = []
    let skippedCount = 0
    for (const scene of pending) {
      if (!scene.prompt.trim()) continue
      if (getSceneGenerationBlockReason(scene)) {
        skippedCount += 1
        continue
      }
      runnable.push(scene)
    }
    if (!runnable.length) {
      alert('没有可生成的场景')
      return
    }
    if (skippedCount > 0) {
      alert(`已跳过 ${skippedCount} 个场景：请检查参考视频模式下的视频和模型配置`)
    }
    for (let index = 0; index < runnable.length; index += 1) {
      await generateOneScene(runnable[index].id)
      if (index < runnable.length - 1) await wait(800)
    }
  }, [generateOneScene, getSceneGenerationBlockReason, scenes])

  return {
    generateOneScene,
    generateAll,
  }
}
