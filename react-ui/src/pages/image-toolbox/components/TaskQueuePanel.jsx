import { Ban, ChevronDown, ChevronUp, LocateFixed, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { assetUrl, imageResultsFromPayload } from '../helpers'
import { PanelNotice } from './PanelNotice'

const TASK_LABELS = {
  generate_nine: 'AI 生成九图',
  generate_roles: '同风格角色九图',
  derive: '图片衍生',
  reverse_prompts: '图片反推',
  watermark: '水印成品',
}

const STATUS_LABELS = {
  queued: '等待中',
  running: '处理中',
  completed: '已完成',
  failed: '失败',
  canceled: '已取消',
}

const ACTIVE_STATUSES = new Set(['queued', 'running'])
const MATERIAL_TASKS = new Set(['generate_nine', 'generate_roles'])

const hasTaskResult = (task) => task.status === 'completed' && Boolean(task.result_payload)
const taskPreviewImages = (task) => {
  if (!hasTaskResult(task)) return []
  const payload = task.result_payload || {}
  const images = imageResultsFromPayload(payload)
  if (payload?.grid?.url) images.push(payload.grid)
  return images
}
const taskResultLabel = (task) => {
  if (task.status !== 'completed') return ''
  if (MATERIAL_TASKS.has(task.type)) return '已加入素材池'
  if (task.type === 'reverse_prompts') return '反推结果已更新'
  if (task.type === 'derive') return '衍生结果已更新'
  if (task.type === 'watermark') return '水印成品已生成'
  return ''
}

const taskTimestamp = (task) => {
  const value = task.started_at || task.created_at || task.updated_at
  const parsed = value ? Date.parse(value) : NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}

const elapsedSeconds = (task, now) => Math.max(0, Math.floor((now - taskTimestamp(task)) / 1000))

function TaskStatusBadge({ task, now }) {
  const active = ACTIVE_STATUSES.has(task.status)
  const seconds = elapsedSeconds(task, now)
  const label = STATUS_LABELS[task.status] || task.status

  return (
    <span className={`image-tool-task-status is-${task.status}`} title={`${STATUS_LABELS[task.status] || task.status}${active ? ` · ${seconds}s` : ''}`}>
      <span className="image-tool-task-ring">
        {active && <span className="image-tool-task-seconds">{seconds}s</span>}
        {task.status === 'completed' && (
          <svg className="image-tool-task-icon" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4.9 8.2 7.1 10.15 11.2 5.85" />
          </svg>
        )}
        {(task.status === 'failed' || task.status === 'canceled') && (
          <svg className="image-tool-task-icon" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M5.1 5.1 10.9 10.9M10.9 5.1 5.1 10.9" />
          </svg>
        )}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  )
}

export function TaskQueuePanel({
  tasks = [],
  notice,
  onCancel,
  onDelete,
  onClearFinished,
  canClearFinished,
  onRefresh,
  onLocate,
  compact = false,
  sticky = false,
  statusStrip = false,
}) {
  const [showAll, setShowAll] = useState(false)
  const [now, setNow] = useState(Date.now())
  const counts = useMemo(() => ({
    active: tasks.filter(task => ACTIVE_STATUSES.has(task.status)).length,
    completed: tasks.filter(task => task.status === 'completed').length,
    failed: tasks.filter(task => task.status === 'failed').length,
  }), [tasks])
  const finishedCount = tasks.filter(task => !ACTIVE_STATUSES.has(task.status)).length
  const canClearHistory = canClearFinished ?? finishedCount > 0
  const visibleTasks = useMemo(() => {
    const active = tasks.filter(task => ACTIVE_STATUSES.has(task.status))
    const inactive = tasks.filter(task => !ACTIVE_STATUSES.has(task.status))
    const merged = showAll ? tasks : [...active, ...inactive].slice(0, compact ? 4 : 8)
    return merged
  }, [compact, showAll, tasks])

  useEffect(() => {
    if (!tasks.some(task => ACTIVE_STATUSES.has(task.status))) return undefined
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [tasks])

  if (statusStrip) {
    const latestTasks = visibleTasks.slice(0, 3)
    return (
      <section className="image-tool-task-strip">
        <div className="image-tool-task-strip-head">
          <strong>任务</strong>
          <span>运行 {counts.active}</span>
          <span>完成 {counts.completed}</span>
          <span>失败 {counts.failed}</span>
          <button type="button" onClick={onRefresh}><RefreshCw size={13} />刷新</button>
        </div>
        <PanelNotice notice={notice} />
        <div className="image-tool-task-strip-list">
          {latestTasks.map(task => {
            const active = ACTIVE_STATUSES.has(task.status)
            return (
              <article key={task.task_id} className={`image-tool-task-pill is-${task.status}`}>
                <strong>{TASK_LABELS[task.type] || task.type}</strong>
                <TaskStatusBadge task={task} now={now} />
                {task.error && <small>{task.error}</small>}
                {active && (
                  <button type="button" onClick={() => onCancel(task.task_id).catch(() => {})}>
                    <Ban size={12} />取消
                  </button>
                )}
                {onLocate && hasTaskResult(task) && (
                  <button type="button" onClick={() => onLocate(task)}>
                    <LocateFixed size={12} />查看结果
                  </button>
                )}
                {onDelete && (
                  <button type="button" onClick={() => onDelete(task.task_id).catch(() => {})}>
                    <Trash2 size={12} />删除
                  </button>
                )}
              </article>
            )
          })}
          {!latestTasks.length && <span className="image-tool-task-strip-empty">暂无后台任务</span>}
        </div>
      </section>
    )
  }

  return (
    <section className={`image-tool-task-panel ${compact ? 'is-compact' : ''} ${sticky ? 'is-sticky' : ''} ${statusStrip ? 'is-status-strip' : ''}`}>
      <div className="image-tool-task-panel-head">
        <strong>任务队列</strong>
        <div className="image-tool-task-panel-actions">
          {onClearFinished && (
            <button type="button" onClick={() => onClearFinished().catch(() => {})} disabled={!canClearHistory}>
              <Trash2 size={14} />清理历史
            </button>
          )}
          <button type="button" onClick={onRefresh}><RefreshCw size={14} />刷新</button>
        </div>
      </div>
      <PanelNotice notice={notice} />
      {!tasks.length && (
        <div className="image-tool-task-empty">暂无后台任务，提交后会在这里持续显示进度和错误。</div>
      )}
      <div className="image-tool-task-list">
        {visibleTasks.map(task => {
          const active = task.status === 'queued' || task.status === 'running'
          const resultLabel = taskResultLabel(task)
          const previewImages = taskPreviewImages(task)
          return (
            <article key={task.task_id} className={`image-tool-task-card is-${task.status}`}>
              <div className="image-tool-task-body">
                <div className="image-tool-task-row">
                  <div className="image-tool-task-main">
                    <strong>{TASK_LABELS[task.type] || task.type}</strong>
                    <small>{task.provider || '-'} · {task.model || '-'}</small>
                  </div>
                  <span className={`image-tool-task-state is-${task.status}`}>
                    <TaskStatusBadge task={task} now={now} />
                    <span>{STATUS_LABELS[task.status] || task.status}</span>
                  </span>
                </div>
                {!!previewImages.length && (
                  <div className="image-tool-task-previews" aria-label="任务结果预览">
                    {previewImages.slice(0, 4).map((image, index) => (
                      <button
                        key={`${image.url}-${index}`}
                        type="button"
                        className="image-tool-task-preview"
                        onClick={() => onLocate?.(task)}
                        title="查看这条任务的结果"
                      >
                        <img src={assetUrl(image.url)} alt={`结果预览 ${index + 1}`} loading="lazy" decoding="async" />
                      </button>
                    ))}
                    {previewImages.length > 4 && (
                      <button type="button" className="image-tool-task-preview-more" onClick={() => onLocate?.(task)}>
                        +{previewImages.length - 4}
                      </button>
                    )}
                  </div>
                )}
                <div className="image-tool-task-foot">
                  {resultLabel && <small className="image-tool-task-result">{resultLabel}</small>}
                  {task.error && <p>{task.error}</p>}
                  <div className="image-tool-task-actions">
                    {active && (
                      <button type="button" onClick={() => onCancel(task.task_id).catch(() => {})}>
                        <Ban size={13} />取消
                      </button>
                    )}
                    {onLocate && hasTaskResult(task) && (
                      <button type="button" onClick={() => onLocate(task)}>
                        <LocateFixed size={13} />查看结果
                      </button>
                    )}
                    {onDelete && (
                      <button type="button" onClick={() => onDelete(task.task_id).catch(() => {})}>
                        <Trash2 size={13} />删除
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </article>
          )
        })}
      </div>
      {tasks.length > (compact ? 4 : 8) && (
        <button type="button" className="image-tool-task-toggle" onClick={() => setShowAll(prev => !prev)}>
          {showAll ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {showAll ? '收起历史任务' : `查看全部 ${tasks.length} 个任务`}
        </button>
      )}
    </section>
  )
}
