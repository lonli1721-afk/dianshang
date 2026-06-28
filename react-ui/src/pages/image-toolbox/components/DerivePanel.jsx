import { Loader2, Palette, Sparkles, Stamp, Wand2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ASPECT_OPTIONS, DERIVE_MODELS_BY_PROVIDER, DERIVE_MODES } from '../constants'
import {
  addImagesToImageToolWorkspaceSlots,
  displayError,
  imageResultsFromPayload,
  loadImageToolWorkspace,
  normalizeWatermarkSettings,
  noticeToneFromMessage,
  persistImageToolWorkspace,
  setImageToolWorkspaceStyleAnchor,
} from '../helpers'
import { deriveImages, listWatermarkFonts, uploadWatermarkFont, watermarkImages } from '../imageToolboxApi'
import { Field } from './Field'
import { ImageGrid } from './ImageGrid'
import { PanelNotice } from './PanelNotice'
import { ResultGrid } from './ResultGrid'
import { TaskQueuePanel } from './TaskQueuePanel'
import { UploadTile } from './UploadTile'
import { WatermarkControls } from './WatermarkControls'

export function DerivePanel({
  uploadImages,
  notify,
  jimengModels,
  geminiModels,
  openaiModels = [],
  tasks = [],
  submitTask,
  taskNotice = null,
  cancelTask,
  deleteTask,
  refreshTasks,
  locateRequest = null,
  onLocateTask,
}) {
  const [refs, setRefs] = useState([])
  const [mode, setMode] = useState('fine_tune')
  const [instruction, setInstruction] = useState('')
  const [provider, setProvider] = useState(DERIVE_MODELS_BY_PROVIDER.jimeng)
  const [model, setModel] = useState('seedream-4.5')
  const [aspect, setAspect] = useState('1:1')
  const [loading, setLoading] = useState(false)
  const [watermarking, setWatermarking] = useState(false)
  const [result, setResult] = useState({ images: [], prompt: '' })
  const [watermarkResult, setWatermarkResult] = useState({ images: [], grid: null })
  const [resultTaskId, setResultTaskId] = useState('')
  const [highlightedTaskId, setHighlightedTaskId] = useState('')
  const [appliedTaskIds, setAppliedTaskIds] = useState([])
  const [panelNotice, setPanelNotice] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const initialWatermarkSettings = useMemo(() => normalizeWatermarkSettings(loadImageToolWorkspace().watermarkSettings), [])
  const [savedWatermarkSettings, setSavedWatermarkSettings] = useState(initialWatermarkSettings)
  const [text, setText] = useState(initialWatermarkSettings.text)
  const [position, setPosition] = useState(initialWatermarkSettings.position)
  const [fontStyle, setFontStyle] = useState(initialWatermarkSettings.fontStyle)
  const [fontOptions, setFontOptions] = useState([])
  const [selectedFontId, setSelectedFontId] = useState(initialWatermarkSettings.selectedFontId)
  const [fontUrl, setFontUrl] = useState(initialWatermarkSettings.fontUrl)
  const [fontName, setFontName] = useState(initialWatermarkSettings.fontName)
  const [color, setColor] = useState(initialWatermarkSettings.color)
  const [opacity, setOpacity] = useState(initialWatermarkSettings.opacity)
  const [strokeColor, setStrokeColor] = useState(initialWatermarkSettings.strokeColor)
  const [outputMode, setOutputMode] = useState(initialWatermarkSettings.outputMode)
  const [fontUploading, setFontUploading] = useState(false)
  const modelOptions = useMemo(
    () => (provider === DERIVE_MODELS_BY_PROVIDER.gemini
      ? geminiModels
      : provider === DERIVE_MODELS_BY_PROVIDER.openai
        ? openaiModels
        : jimengModels),
    [geminiModels, jimengModels, openaiModels, provider],
  )
  const deriveResultImages = result.images || []
  const draftWatermarkSettings = normalizeWatermarkSettings({
    text,
    position,
    fontStyle,
    selectedFontId,
    fontUrl,
    fontName,
    color,
    opacity,
    strokeColor,
    outputMode,
  })
  const outputNeedsGrid = draftWatermarkSettings.outputMode !== 'separate'
  const canWatermarkWithSettings = (settings) => {
    const resolved = normalizeWatermarkSettings(settings)
    return deriveResultImages.length > 0 && resolved.text.trim() && (resolved.outputMode === 'separate' || deriveResultImages.length === 9)
  }
  const canWatermark = canWatermarkWithSettings(draftWatermarkSettings)
  const canGenerateSavedWatermark = canWatermarkWithSettings(savedWatermarkSettings)
  const savedWatermarkOutputLabel = savedWatermarkSettings.outputMode === 'separate' ? '单图' : savedWatermarkSettings.outputMode === 'grid' ? '九宫格' : '单图+九宫格'
  const savedWatermarkDisabledReason = !deriveResultImages.length
    ? '请先生成图片衍生结果。'
    : !savedWatermarkSettings.text.trim()
      ? '请先保存水印文字。'
      : savedWatermarkSettings.outputMode !== 'separate' && deriveResultImages.length !== 9
        ? `九宫格水印需要 9 张图片，当前衍生结果为 ${deriveResultImages.length} 张。`
        : ''
  const watermarkSummary = `${deriveResultImages.length} 张衍生结果，水印：${savedWatermarkSettings.text.trim() || '未设置'} · ${savedWatermarkOutputLabel}`

  const showPanelNotice = useCallback((message, tone) => {
    if (!message) {
      setPanelNotice(null)
      return
    }
    const resolvedTone = tone || noticeToneFromMessage(message)
    setPanelNotice({ message, tone: resolvedTone })
    notify?.({ scope: 'toast', message, tone: resolvedTone })
  }, [notify])

  const panelUploadImages = useCallback((files, options) => (
    uploadImages(files, { ...options, setNotice: showPanelNotice })
  ), [showPanelNotice, uploadImages])

  useEffect(() => {
    const completed = tasks.filter(task => (
      task.status === 'completed'
      && task.type === 'derive'
      && !appliedTaskIds.includes(task.task_id)
    ))
    if (!completed.length) return
    const latest = completed[0]
    const payload = latest.result_payload || {}
    setResult({ images: imageResultsFromPayload(payload), prompt: payload.prompt || '' })
    setWatermarkResult({ images: [], grid: null })
    setResultTaskId(latest.task_id)
    setAppliedTaskIds(prev => [...prev, ...completed.map(task => task.task_id)].slice(-60))
    showPanelNotice(`图片衍生任务已完成 ${completed.length} 个，结果已更新。`, 'success')
  }, [tasks, appliedTaskIds, showPanelNotice])

  useEffect(() => {
    const task = locateRequest?.task
    if (!task || task.type !== 'derive') return
    if (task.status !== 'completed' || !task.result_payload) {
      showPanelNotice('这个图片衍生任务还没有可查看的结果。', 'warning')
      return
    }
    const payload = task.result_payload || {}
    setResult({ images: imageResultsFromPayload(payload), prompt: payload.prompt || '' })
    setWatermarkResult({ images: [], grid: null })
    setResultTaskId(task.task_id)
    setHighlightedTaskId(task.task_id)
    setAppliedTaskIds(prev => Array.from(new Set([...prev, task.task_id])).slice(-60))
    showPanelNotice('已定位到该图片衍生任务结果。', 'success')

    const selector = `[data-image-task-id="${task.task_id}"]`
    const scrollTimer = window.setTimeout(() => {
      document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 80)
    const clearTimer = window.setTimeout(() => setHighlightedTaskId(''), 3200)
    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(clearTimer)
    }
  }, [locateRequest, showPanelNotice])

  useEffect(() => {
    let alive = true
    listWatermarkFonts('图片衍生')
      .then(data => {
        if (!alive) return
        const fonts = data.fonts || []
        setFontOptions(fonts)
        if (fonts.length) setSelectedFontId(prev => prev || fonts[0].id)
      })
      .catch(error => {
        if (alive) showPanelNotice(displayError(error), 'error')
      })
    return () => { alive = false }
  }, [showPanelNotice])

  useEffect(() => {
    if (!modelOptions.length) return
    if (!modelOptions.some(item => item.id === model)) {
      const fallbackId = provider === DERIVE_MODELS_BY_PROVIDER.openai ? 'gpt-image-2' : 'seedream-4.5'
      const preferred = modelOptions.find(item => item.id === fallbackId) || modelOptions[0]
      queueMicrotask(() => setModel(preferred.id))
    }
  }, [modelOptions, model, provider])

  const runDerive = async () => {
    if (!refs.length) {
      showPanelNotice('请先上传参考图。', 'error')
      return
    }

    setLoading(true)
    showPanelNotice('')
    try {
      if (submitTask) {
        await submitTask('derive', {
          reference_urls: refs.map(item => item.url),
          mode,
          instruction,
          provider,
          model,
          aspect_ratio: aspect,
        })
        showPanelNotice('已提交图片衍生任务，可继续提交其他任务或切换页面等待。', 'success')
        return
      }
      const data = await deriveImages({
        reference_urls: refs.map(item => item.url),
        mode,
        instruction,
        provider,
        model,
        aspect_ratio: aspect,
      })
      setResult({ images: imageResultsFromPayload(data), prompt: data.prompt || '' })
      setWatermarkResult({ images: [], grid: null })
      setResultTaskId('')
    } catch (error) {
      showPanelNotice(displayError(error), 'error')
    } finally {
      setLoading(false)
    }
  }

  const addImageToWorkspace = (image) => {
    const inserted = addImagesToImageToolWorkspaceSlots([image])
    showPanelNotice(inserted ? '已加入九图工作区素材槽。' : '九图工作区槽位已满，或这张图已在槽位里。', inserted ? 'success' : 'warning')
  }

  const setWorkspaceAnchor = (image) => {
    if (setImageToolWorkspaceStyleAnchor(image)) {
      showPanelNotice('已设为九图工作区风格样板。', 'success')
    }
  }

  const uploadFont = async (files) => {
    const file = files[0]
    if (!file) return

    setFontUploading(true)
    try {
      const data = await uploadWatermarkFont(file)
      setFontUrl(data.url)
      setFontName(file.name)
      const customId = `custom:${data.url}`
      setSelectedFontId(customId)
      setFontOptions(prev => [
        {
          id: customId,
          name: file.name.replace(/\.[^.]+$/, ''),
          source: '上传字体',
          preview_url: data.preview_url,
          font_url: data.url,
        },
        ...prev.filter(item => item.id !== customId),
      ])
      showPanelNotice(`已使用字体：${file.name}`, 'success')
    } catch (error) {
      showPanelNotice(displayError(error), 'error')
    } finally {
      setFontUploading(false)
    }
  }

  const saveWatermarkSettings = (settings = draftWatermarkSettings) => {
    const nextSettings = normalizeWatermarkSettings(settings)
    const workspace = loadImageToolWorkspace()
    persistImageToolWorkspace({
      ...workspace,
      watermarkSettings: nextSettings,
    })
    setSavedWatermarkSettings(nextSettings)
    showPanelNotice('水印设置已保存，后续生成会沿用这套设置。', 'success')
    return nextSettings
  }

  const buildWatermarkPayload = (settings = savedWatermarkSettings) => {
    const resolvedSettings = normalizeWatermarkSettings(settings)
    return {
      image_urls: deriveResultImages.map(item => item.url),
      text: resolvedSettings.text,
      position: resolvedSettings.position,
      font_style: resolvedSettings.fontStyle,
      font_id: resolvedSettings.selectedFontId.startsWith('custom:') ? '' : resolvedSettings.selectedFontId,
      font_url: resolvedSettings.selectedFontId.startsWith('custom:') ? resolvedSettings.fontUrl : '',
      color: resolvedSettings.color,
      opacity: resolvedSettings.opacity,
      stroke_color: resolvedSettings.strokeColor,
      output_mode: resolvedSettings.outputMode,
    }
  }

  const runWatermark = async (settings = savedWatermarkSettings, closeDrawer = false) => {
    const resolvedSettings = normalizeWatermarkSettings(settings)
    if (!deriveResultImages.length) {
      showPanelNotice('请先生成图片衍生结果。', 'error')
      return
    }
    if (!resolvedSettings.text.trim()) {
      showPanelNotice('请先填写水印文字。', 'error')
      return
    }
    if (resolvedSettings.outputMode !== 'separate' && deriveResultImages.length !== 9) {
      showPanelNotice(`九宫格水印需要 9 张图片，当前衍生结果为 ${deriveResultImages.length} 张。`, 'error')
      return
    }

    setWatermarking(true)
    try {
      const data = await watermarkImages(buildWatermarkPayload(resolvedSettings))
      setWatermarkResult({ images: data.images || [], grid: data.grid || null })
      if (closeDrawer) setDrawerOpen(false)
      showPanelNotice('衍生图片水印已生成。', 'success')
    } catch (error) {
      showPanelNotice(displayError(error), 'error')
    } finally {
      setWatermarking(false)
    }
  }

  const deriveTasks = tasks.filter(task => task.type === 'derive')

  const deleteDeriveTask = async (taskId) => {
    await deleteTask?.(taskId)
    if (!resultTaskId || resultTaskId === taskId) {
      setResult({ images: [], prompt: '' })
      setWatermarkResult({ images: [], grid: null })
      setResultTaskId('')
    }
    showPanelNotice('已删除衍生任务和当前衍生结果。', 'success')
  }

  const clearDeriveHistory = async () => {
    const finished = deriveTasks.filter(task => !['queued', 'running'].includes(task.status))
    await Promise.allSettled(finished.map(task => deleteTask?.(task.task_id)))
    setResult({ images: [], prompt: '' })
    setWatermarkResult({ images: [], grid: null })
    setResultTaskId('')
    showPanelNotice('已清理图片衍生历史和当前结果。', 'success')
  }

  return (
    <section className="image-tool-layout">
      <div className="image-tool-panel image-tool-config-panel">
        <div className="image-tool-panel-title"><Wand2 size={18} />图片一键衍生</div>
        <div className="image-tool-mode-grid">
          {DERIVE_MODES.map(item => (
            <button
              key={item.id}
              type="button"
              className={mode === item.id ? 'is-active' : ''}
              onClick={() => {
                setMode(item.id)
                if (item.id !== 'creative_fusion' && refs.length > 1) setRefs(refs.slice(0, 1))
              }}
            >
              <strong>{item.label}</strong>
              <span>{item.hint}</span>
            </button>
          ))}
        </div>
        <UploadTile
          label={`上传参考图，最多 ${mode === 'creative_fusion' ? 4 : 1} 张`}
          disabled={loading}
          onFiles={files => panelUploadImages(files, { limit: mode === 'creative_fusion' ? 4 : 1, current: refs, onChange: setRefs })}
        />
        <ImageGrid
          images={refs}
          onRemove={index => setRefs(prev => prev.filter((_, i) => i !== index))}
          emptyText="还没有参考图"
          onSetAnchor={setWorkspaceAnchor}
          showActions
        />
        <Field label="补充要求">
          <textarea rows={5} value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="例：把整体质感改成高质量国漫 2D，保留人物姿势和画面构图" />
        </Field>
        <div className="image-tool-form-grid">
          <Field label="服务商">
            <select value={provider} onChange={event => setProvider(event.target.value)}>
              <option value={DERIVE_MODELS_BY_PROVIDER.jimeng}>即梦 / Seedream</option>
              <option value={DERIVE_MODELS_BY_PROVIDER.gemini}>Gemini 图片</option>
              <option value={DERIVE_MODELS_BY_PROVIDER.openai}>OpenAI Image</option>
            </select>
          </Field>
          <Field label="模型">
            <select value={model} onChange={event => setModel(event.target.value)}>
              {(modelOptions.length ? modelOptions : [{ id: model, name: model }]).map(item => (
                <option key={item.id} value={item.id}>{item.name || item.id}</option>
              ))}
            </select>
          </Field>
          <Field label="比例">
            <select value={aspect} onChange={event => setAspect(event.target.value)}>
              {ASPECT_OPTIONS.map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </Field>
        </div>
        <button type="button" className="image-tool-primary" disabled={loading} onClick={runDerive}>
          {loading ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
          提交衍生任务
        </button>
        <div className="image-tool-left-task-slot">
          <TaskQueuePanel
            tasks={deriveTasks}
            notice={taskNotice}
            onCancel={cancelTask}
            onDelete={deleteDeriveTask}
            onClearFinished={clearDeriveHistory}
            onRefresh={refreshTasks}
            onLocate={onLocateTask}
            canClearFinished={deriveTasks.some(task => !['queued', 'running'].includes(task.status)) || result.images.length > 0}
            compact
          />
        </div>
        <div className="image-tool-setting-summary">
          <div>
            <strong>衍生水印</strong>
            <span>{watermarkSummary}</span>
          </div>
          <div className="image-tool-setting-actions">
            <button type="button" disabled={!deriveResultImages.length || watermarking} onClick={() => setDrawerOpen(true)}>
              <Stamp size={15} />水印设置
            </button>
            <button type="button" disabled={watermarking || !canGenerateSavedWatermark} title={savedWatermarkDisabledReason || '生成衍生水印图'} onClick={() => runWatermark(savedWatermarkSettings, false)}>
              {watermarking ? <Loader2 className="spin" size={15} /> : <Stamp size={15} />}生成水印图
            </button>
          </div>
        </div>
        <PanelNotice notice={panelNotice} />
      </div>
      <div className="image-tool-panel image-tool-workspace-panel">
        <div className="image-tool-panel-title"><Palette size={18} />衍生结果</div>
        <div
          className={`image-tool-result-locate ${highlightedTaskId && highlightedTaskId === resultTaskId ? 'is-located' : ''}`}
          data-image-task-id={resultTaskId || undefined}
        >
          <ResultGrid
            images={result.images}
            prompt={result.prompt}
            onAddImageToWorkspace={addImageToWorkspace}
            onSetAnchor={setWorkspaceAnchor}
          />
        </div>
        {(watermarkResult.images.length > 0 || watermarkResult.grid) && (
          <div className="image-tool-watermark-result">
            <div className="image-tool-panel-title"><Stamp size={18} />水印结果</div>
            <ResultGrid
              images={watermarkResult.images}
              grid={watermarkResult.grid}
              onAddImageToWorkspace={addImageToWorkspace}
              onSetAnchor={setWorkspaceAnchor}
            />
          </div>
        )}
      </div>
      {drawerOpen && (
        <div className="image-tool-drawer-backdrop" role="presentation" onClick={() => setDrawerOpen(false)}>
          <aside className="image-tool-drawer" onClick={event => event.stopPropagation()}>
            <div className="image-tool-drawer-head">
              <strong>衍生图片水印</strong>
              <button type="button" onClick={() => setDrawerOpen(false)} title="关闭">
                <X size={16} />
              </button>
            </div>
            <WatermarkControls
              text={text}
              setText={setText}
              outputMode={outputMode}
              setOutputMode={setOutputMode}
              position={position}
              setPosition={setPosition}
              fontStyle={fontStyle}
              setFontStyle={setFontStyle}
              opacity={opacity}
              setOpacity={setOpacity}
              color={color}
              setColor={setColor}
              strokeColor={strokeColor}
              setStrokeColor={setStrokeColor}
              fontOptions={fontOptions}
              selectedFontId={selectedFontId}
              setSelectedFontId={setSelectedFontId}
              fontUrl={fontUrl}
              setFontUrl={setFontUrl}
              fontName={fontName}
              setFontName={setFontName}
              fontUploading={fontUploading}
              uploadFont={uploadFont}
              disabled={watermarking || loading}
            />
            {outputNeedsGrid && deriveResultImages.length !== 9 && (
              <div className="image-tool-inline-warning">九宫格水印需要 9 张图片，当前衍生结果为 {deriveResultImages.length} 张。</div>
            )}
            <div className="image-tool-drawer-action-grid">
              <button type="button" className="image-tool-secondary" disabled={watermarking || loading} onClick={() => saveWatermarkSettings(draftWatermarkSettings)}>
                <Stamp size={16} />保存设置
              </button>
              <button
                type="button"
                className="image-tool-primary"
                disabled={watermarking || !canWatermark}
                onClick={() => {
                  const nextSettings = saveWatermarkSettings(draftWatermarkSettings)
                  runWatermark(nextSettings, true)
                }}
              >
                {watermarking ? <Loader2 className="spin" size={16} /> : <Stamp size={16} />}
                保存并生成
              </button>
            </div>
          </aside>
        </div>
      )}
    </section>
  )
}
