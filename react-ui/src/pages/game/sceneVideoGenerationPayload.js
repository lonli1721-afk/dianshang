import { normalizeVideoResolutionForModel } from './gameVideoModelUtils.js'

export function buildSceneVideoGenerationPayload({
  currentProjectId,
  scene,
  selectedModel,
  provider,
}) {
  return {
    project_id: currentProjectId || '',
    prompt: scene.prompt,
    provider,
    model: scene.model,
    duration: scene.duration,
    aspect_ratio: scene.aspectRatio,
    resolution: normalizeVideoResolutionForModel(scene.videoResolution, selectedModel),
    character_refs: scene.charImages.map(image => image.url),
    scene_refs: scene.sceneImages.map(image => image.url),
    reference_video_url: scene.videoMode === 'reference_video' ? scene.refVideoUrl : '',
    advanced_reference_videos: scene.videoMode === 'advanced_video'
      ? (scene.advancedRefVideos || []).map(video => video.url)
      : [],
  }
}
