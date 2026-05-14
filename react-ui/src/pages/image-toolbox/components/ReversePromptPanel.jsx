import { Copy, Eraser, FileImage, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { MAX_IMAGE_COUNT, REVERSE_MODELS } from '../constants'
import { assetUrl, displayError, noticeToneFromMessage, setImageToolWorkspaceStyleAnchor } from '../helpers'
import { reverseImagePrompts } from '../imageToolboxApi'
import { Field } from './Field'
import { ImageGrid } from './ImageGrid'
import { PanelNotice } from './PanelNotice'
import { TaskQueuePanel } from './TaskQueuePanel'
import { UploadTile } from './UploadTile'

export function ReversePromptPanel({
  uploadImages,
  notify,
  tasks = [],
  submitTask,
  taskNotice = null,
  cancelTask,
  deleteTask,
  refreshTasks,
  locateRequest = null,
  onLocateTask,
}) {
  const [images, setImages] = useState([])
  const [model, setModel] = useState('gemini-2.5-flash')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState([])
  const [resultTaskId, setResultTaskId] = useState('')
  const [highlightedTaskId, setHighlightedTaskId] = useState('')
  const [appliedTaskIds, setAppliedTaskIds] = useState([])
  const [panelNotice, setPanelNotice] = useState(null)

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
      && task.type === 'reverse_prompts'
      && !appliedTaskIds.includes(task.task_id)
    ))
    if (!completed.length) return
    const latest = completed[0]
    setResults(latest.result_payload?.results || [])
    setResultTaskId(latest.task_id)
    setAppliedTaskIds(prev => [...prev, ...completed.map(task => task.task_id)].slice(-60))
    showPanelNotice(`图片反推任务已完成 ${completed.length} 个，结果已更新。`, 'success')
  }, [tasks, appliedTaskIds, showPanelNotice])

  useEffect(() => {
    const task = locateRequest?.task
    if (!task || task.type !== 'reverse_prompts') return
    if (task.status !== 'completed' || !task.result_payload) {
      showPanelNotice('这个图片反推任务还没有可查看的结果。', 'warning')
      return
    }
    setResults(task.result_payload?.results || [])
    setResultTaskId(task.task_id)
    setHighlightedTaskId(task.task_id)
    setAppliedTaskIds(prev => Array.from(new Set([...prev, task.task_id])).slice(-60))
    showPanelNotice('已定位到该图片反推任务结果。', 'success')

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

  const runReverse = async () => {
    if (!images.length) {
      showPanelNotice('请先上传要反推的图片。', 'error')
      return
    }

    setLoading(true)
    showPanelNotice('')
    try {
      if (submitTask) {
        await submitTask('reverse_prompts', {
          image_urls: images.map(item => item.url),
          model,
        })
        showPanelNotice('已提交图片反推任务，可继续提交其他任务或切换页面等待。', 'success')
        return
      }
      const data = await reverseImagePrompts({
        image_urls: images.map(item => item.url),
        model,
      })
      setResults(data.results || [])
      setResultTaskId('')
    } catch (error) {
      showPanelNotice(displayError(error), 'error')
    } finally {
      setLoading(false)
    }
  }

  const setWorkspaceAnchor = (image) => {
    if (setImageToolWorkspaceStyleAnchor(image)) {
      showPanelNotice('已设为九图工作区风格样板。', 'success')
    }
  }

  const copyAllReversePrompts = () => {
    const text = results
      .filter(item => item.ok && item.prompt)
      .map((item, index) => `图${index + 1}\n${item.prompt}`)
      .join('\n\n')
    if (text) navigator.clipboard.writeText(text)
  }

  const reverseTasks = tasks.filter(task => task.type === 'reverse_prompts')

  const deleteReverseTask = async (taskId) => {
    await deleteTask?.(taskId)
    if (!resultTaskId || resultTaskId === taskId) {
      setResults([])
      setResultTaskId('')
    }
    showPanelNotice('已删除反推任务和当前反推结果。', 'success')
  }

  const clearReverseHistory = async () => {
    const finished = reverseTasks.filter(task => !['queued', 'running'].includes(task.status))
    await Promise.allSettled(finished.map(task => deleteTask?.(task.task_id)))
    setResults([])
    setResultTaskId('')
    showPanelNotice('已清理图片反推历史和当前结果。', 'success')
  }

  return (
    <section className="image-tool-layout">
      <div className="image-tool-panel image-tool-config-panel">
        <div className="image-tool-panel-title"><FileImage size={18} />批量反推图片提示词</div>
        <UploadTile
          label="上传图片，最多 9 张"
          disabled={loading}
          onFiles={files => panelUploadImages(files, { limit: MAX_IMAGE_COUNT, current: images, onChange: setImages })}
        />
        <ImageGrid
          images={images}
          onRemove={index => setImages(prev => prev.filter((_, i) => i !== index))}
          onSetAnchor={setWorkspaceAnchor}
          showActions
        />
        <Field label="分析模型">
          <select value={model} onChange={event => setModel(event.target.value)}>
            {REVERSE_MODELS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </Field>
        <button type="button" className="image-tool-primary" disabled={loading} onClick={runReverse}>
          {loading ? <Loader2 className="spin" size={16} /> : <Eraser size={16} />}
          提交反推任务
        </button>
        <div className="image-tool-left-task-slot">
          <TaskQueuePanel
            tasks={reverseTasks}
            notice={taskNotice}
            onCancel={cancelTask}
            onDelete={deleteReverseTask}
            onClearFinished={clearReverseHistory}
            onRefresh={refreshTasks}
            onLocate={onLocateTask}
            canClearFinished={reverseTasks.some(task => !['queued', 'running'].includes(task.status)) || results.length > 0}
            compact
          />
        </div>
        <PanelNotice notice={panelNotice} />
      </div>
      <div className="image-tool-panel image-tool-workspace-panel">
        <div className="image-tool-panel-title">
          <FileImage size={18} />反推结果
          <button type="button" className="image-tool-copy-all" onClick={copyAllReversePrompts} disabled={!results.some(item => item.ok && item.prompt)}>
            <Copy size={14} />复制全部完整提示词
          </button>
        </div>
        <div
          className={`image-tool-reverse-list image-tool-result-locate ${highlightedTaskId && highlightedTaskId === resultTaskId ? 'is-located' : ''}`}
          data-image-task-id={resultTaskId || undefined}
        >
          {results.map((item, index) => (
            <article key={`${item.image_url}-${index}`} className={`image-tool-reverse-card ${item.ok ? '' : 'is-failed'} ${highlightedTaskId && highlightedTaskId === resultTaskId ? 'is-located' : ''}`}>
              <img src={assetUrl(item.image_url)} alt={`反推图 ${index + 1}`} loading="lazy" decoding="async" />
              <div>
                <h3>图 {index + 1}</h3>
                {item.ok ? (
                  <>
                    <p><strong>画面内容：</strong>{item.theme || item.subject || '-'}</p>
                    <p><strong>画风摘要：</strong>{item.style_summary || item.style || '-'}</p>
                    <p><strong>画风提示词：</strong>{item.visual_style || '-'}</p>
                    <p><strong>负面词：</strong>{item.negative_prompt || '-'}</p>
                    <p><strong>爆点：</strong>{(item.selling_points || []).join('、') || '-'}</p>
                    <textarea readOnly rows={6} value={item.prompt || ''} aria-label={`图 ${index + 1} 完整提示词`} />
                    <div className="image-tool-reverse-actions">
                      <button type="button" onClick={() => navigator.clipboard.writeText(item.prompt || '')}><Copy size={14} />复制完整提示词</button>
                      <button type="button" onClick={() => navigator.clipboard.writeText(item.negative_prompt || '')}><Copy size={14} />复制负面词</button>
                      <button type="button" onClick={() => setWorkspaceAnchor({ url: item.image_url, filename: item.image_url?.split('/').pop() || '' })}>设为样板</button>
                    </div>
                  </>
                ) : (
                  <p>{item.error || '反推失败'}</p>
                )}
              </div>
            </article>
          ))}
          {!results.length && <div className="image-tool-empty"><FileImage size={22} />等待反推结果</div>}
        </div>
      </div>
    </section>
  )
}
