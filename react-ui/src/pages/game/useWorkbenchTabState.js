import { useCallback, useMemo, useRef, useState } from 'react'
import { DEFAULT_IMAGE_ASPECT_RATIO } from './gameVideoConstants'
import { parseTabState } from './gameVideoPageHelpers'

export function useWorkbenchTabState({
  imageModelsRef,
}) {
  const [replCharImage, setReplCharImage] = useState(null)
  const [replRefVideo, setReplRefVideo] = useState('')
  const [replRefVideoDurationSeconds, setReplRefVideoDurationSeconds] = useState(null)
  const [replPrompt, setReplPrompt] = useState('')
  const [replProvider, setReplProvider] = useState('wan')
  const [replWanMode, setReplWanMode] = useState('wan-std')
  const [replWanCheckImage, setReplWanCheckImage] = useState(false)
  const [replVideoResolution, setReplVideoResolution] = useState('720p')
  const [replStatus, setReplStatus] = useState('idle')
  const [replError, setReplError] = useState('')
  const [replVideoUrl, setReplVideoUrl] = useState('')
  const [replStartTime, setReplStartTime] = useState(null)
  const [replTaskId, setReplTaskId] = useState('')
  const [replHistory, setReplHistory] = useState([])

  const [imgGenPrompt, setImgGenPrompt] = useState('')
  const [imgGenPromptModel, setImgGenPromptModel] = useState('gemini-2.5-flash')
  const [imgGenModel, setImgGenModel] = useState('')
  const [imgGenProvider, setImgGenProvider] = useState('')
  const [imgGenRefImages, setImgGenRefImages] = useState([])
  const [imgGenEditMode, setImgGenEditMode] = useState(false)
  const [imgGenAspectRatio, setImgGenAspectRatio] = useState(DEFAULT_IMAGE_ASPECT_RATIO)
  const [imgGenQuality, setImgGenQuality] = useState('2K')
  const [imgGenHistory, setImgGenHistory] = useState([])

  const [reverseVideoUrl, setReverseVideoUrl] = useState('')
  const [reverseVideoDurationSeconds, setReverseVideoDurationSeconds] = useState(null)
  const [reverseModel, setReverseModel] = useState('gemini-3.1-pro-preview')
  const [reverseResult, setReverseResult] = useState('')
  /** @type {{ video_url: string, model: string, result: string, ts: number }[]} */
  const [reverseHistory, setReverseHistory] = useState([])

  const replaceVideo = useMemo(() => ({
    replHistory,
    replCharImage,
    replRefVideo,
    replRefVideoDurationSeconds,
    replPrompt,
    replProvider,
    replWanMode,
    replWanCheckImage,
    replVideoResolution,
    replVideoUrl,
    replTaskId,
    replStatus,
    replError,
    replStartTime,
  }), [
    replHistory,
    replCharImage,
    replRefVideo,
    replRefVideoDurationSeconds,
    replPrompt,
    replProvider,
    replWanMode,
    replWanCheckImage,
    replVideoResolution,
    replVideoUrl,
    replTaskId,
    replStatus,
    replError,
    replStartTime,
  ])

  const standaloneImage = useMemo(() => ({
    imgGenHistory,
    imgGenPrompt,
    imgGenPromptModel,
    imgGenModel,
    imgGenProvider,
    imgGenRefImages,
    imgGenEditMode,
    imgGenAspectRatio,
    imgGenQuality,
  }), [
    imgGenHistory,
    imgGenPrompt,
    imgGenPromptModel,
    imgGenModel,
    imgGenProvider,
    imgGenRefImages,
    imgGenEditMode,
    imgGenAspectRatio,
    imgGenQuality,
  ])

  const videoReverse = useMemo(() => ({
    reverseHistory,
    reverseVideoUrl,
    reverseVideoDurationSeconds,
    reverseModel,
    reverseResult,
  }), [
    reverseHistory,
    reverseVideoUrl,
    reverseVideoDurationSeconds,
    reverseModel,
    reverseResult,
  ])

  const replaceVideoSetters = useMemo(() => ({
    setReplHistory,
    setReplCharImage,
    setReplRefVideo,
    setReplRefVideoDurationSeconds,
    setReplPrompt,
    setReplProvider,
    setReplWanMode,
    setReplWanCheckImage,
    setReplVideoResolution,
    setReplVideoUrl,
    setReplTaskId,
    setReplStatus,
    setReplError,
    setReplStartTime,
  }), [])

  const standaloneImageSetters = useMemo(() => ({
    setImgGenHistory,
    setImgGenPrompt,
    setImgGenPromptModel,
    setImgGenModel,
    setImgGenProvider,
    setImgGenRefImages,
    setImgGenEditMode,
    setImgGenAspectRatio,
    setImgGenQuality,
  }), [])

  const videoReverseSetters = useMemo(() => ({
    setReverseHistory,
    setReverseVideoUrl,
    setReverseVideoDurationSeconds,
    setReverseModel,
    setReverseResult,
  }), [])

  const tabState = useMemo(() => ({
    replaceVideo: replaceVideo,
    standaloneImage: standaloneImage,
    videoReverse: videoReverse,
  }), [replaceVideo, standaloneImage, videoReverse])

  const tabStateRef = useRef({})
  tabStateRef.current = tabState

  const applyTabState = useCallback((tab) => {
    const parsed = parseTabState(tab, imageModelsRef.current || [])
    const rv = parsed.replaceVideo
    setReplHistory(rv.replHistory)
    setReplCharImage(rv.replCharImage)
    setReplRefVideo(rv.replRefVideo)
    setReplRefVideoDurationSeconds(rv.replRefVideoDurationSeconds)
    setReplPrompt(rv.replPrompt)
    setReplProvider(rv.replProvider)
    setReplWanMode(rv.replWanMode)
    setReplWanCheckImage(rv.replWanCheckImage)
    setReplVideoResolution(rv.replVideoResolution)
    setReplVideoUrl(rv.replVideoUrl)
    setReplTaskId(rv.replTaskId)
    setReplStatus(rv.replStatus)
    setReplError(rv.replError)
    setReplStartTime(rv.replStartTime)

    const si = parsed.standaloneImage
    setImgGenHistory(si.imgGenHistory)
    setImgGenPrompt(si.imgGenPrompt)
    setImgGenPromptModel(si.imgGenPromptModel)
    setImgGenModel(si.imgGenModel)
    setImgGenProvider(si.imgGenProvider)
    setImgGenRefImages(si.imgGenRefImages)
    setImgGenEditMode(si.imgGenEditMode)
    setImgGenAspectRatio(si.imgGenAspectRatio)
    setImgGenQuality(si.imgGenQuality)

    const vr = parsed.videoReverse
    setReverseHistory(vr.reverseHistory)
    setReverseVideoUrl(vr.reverseVideoUrl)
    setReverseVideoDurationSeconds(vr.reverseVideoDurationSeconds)
    setReverseModel(vr.reverseModel)
    setReverseResult(vr.reverseResult)
    return parsed
  }, [
    imageModelsRef,
    setReplHistory,
    setReplCharImage,
    setReplRefVideo,
    setReplRefVideoDurationSeconds,
    setReplPrompt,
    setReplProvider,
    setReplWanMode,
    setReplWanCheckImage,
    setReplVideoResolution,
    setReplVideoUrl,
    setReplTaskId,
    setReplStatus,
    setReplError,
    setReplStartTime,
    setImgGenHistory,
    setImgGenPrompt,
    setImgGenPromptModel,
    setImgGenModel,
    setImgGenProvider,
    setImgGenRefImages,
    setImgGenEditMode,
    setImgGenAspectRatio,
    setImgGenQuality,
    setReverseHistory,
    setReverseVideoUrl,
    setReverseVideoDurationSeconds,
    setReverseModel,
    setReverseResult,
  ])

  return {
    tabState,
    tabStateRef,
    applyTabState,
    replaceVideo,
    standaloneImage,
    videoReverse,
    replaceVideoSetters,
    standaloneImageSetters,
    videoReverseSetters,
  }
}
