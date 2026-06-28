import { normalizeVideoResolutionForModel } from './gameVideoModelUtils.js'

const VIDEO_SOUND_RULE = '【声音规则】全片声音风格必须统一：不要背景音乐、BGM、配乐、音乐节奏或鼓点；不要唱歌、吟唱、Rap、歌词化表达或音乐化念白；只保留真实现场音效，并加入一条普通话广告旁白，像品牌广告解说一样自然说出来，声音干净克制，语速稳定。'

export function normalizeVideoSoundPrompt(prompt) {
  const staleVoiceoverBlocks = [
    /【声音规则】[^。]*。?/g,
    /声音规则[:：][^。]*。?/g,
    /【声音限制】[^。]*(?:背景音乐|BGM|bgm|配乐|音乐节奏|轻音乐|鼓点|现场音效|旁白)[^。]*。?/g,
    /【声音限制】不要生成[^。]*(?:旁白|配音|语音音轨)[^。]*。?/g,
    /不要生成[^。；]*(?:旁白|配音|语音音轨)[^。；]*(?:[。；]|$)/g,
    /只保留真实现场环境音[^。；]*(?:[。；]|$)/g,
    /不要(?:生成|出现|加入|使用|有)?[^。；]*(?:背景音乐|BGM|bgm|配乐|音乐节奏|轻音乐|鼓点)[^。；]*(?:[。；]|$)/g,
  ]
  const replacements = {
    BGM: '现场音效',
    bgm: '现场音效',
    背景音乐: '现场音效',
    配乐: '现场音效',
    轻音乐节奏: '现场音效',
    轻音乐: '现场音效',
    音乐节奏: '现场音效',
    低频户外广告鼓点: '现场音效',
    低频鼓点: '现场音效',
    鼓点: '现场音效',
  }
  const baseText = staleVoiceoverBlocks.reduce(
    (value, pattern) => value.replace(pattern, ''),
    String(prompt || ''),
  )
  const cleaned = Object.entries(replacements).reduce(
    (value, [source, target]) => value.replaceAll(source, target),
    baseText,
  ).replace(/\s+/g, ' ').trim()
  if (!cleaned) return ''
  return cleaned.includes(VIDEO_SOUND_RULE)
    ? cleaned
    : `${cleaned} ${VIDEO_SOUND_RULE}`.trim()
}

export function buildSceneVideoGenerationPayload({
  currentProjectId,
  scene,
  selectedModel,
  provider,
}) {
  return {
    project_id: currentProjectId || '',
    prompt: normalizeVideoSoundPrompt(scene.prompt),
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
