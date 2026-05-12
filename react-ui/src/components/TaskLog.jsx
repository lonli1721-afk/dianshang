import { useState, useEffect, useRef } from 'react'
import { Sparkles, CheckCircle, XCircle, Loader2, Clock, ChevronDown, ChevronUp } from 'lucide-react'

export { TaskProvider } from './TaskLogProvider'

function formatElapsed(ms) {
  if (ms < 1000) return '< 1s'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

export default function TaskLog({ tasks, onClear, onTaskClick }) {
  const [collapsed, setCollapsed] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const listRef = useRef(null)

  const running = tasks.filter(t => t.status === 'running').length
  const done = tasks.filter(t => t.status === 'done').length
  const failed = tasks.filter(t => t.status === 'error').length

  useEffect(() => {
    if (running === 0) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [running])

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--bg-secondary)', borderLeft: '1px solid var(--border)',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Sparkles size={14} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>任务日志</span>
          {running > 0 && (
            <span style={{
              padding: '1px 8px', borderRadius: 10, fontSize: 10,
              background: 'rgba(16,185,129,0.1)', color: 'var(--accent)',
              fontWeight: 600,
            }}>
              {running} 进行中
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {tasks.length > 0 && (
            <button onClick={onClear} style={{
              padding: '2px 8px', borderRadius: 4, fontSize: 10,
              background: 'var(--bg-tertiary)', color: 'var(--text-muted)',
            }}>清空</button>
          )}
          <button onClick={() => setCollapsed(!collapsed)} style={{
            background: 'none', color: 'var(--text-muted)', padding: 2,
          }}>
            {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div style={{
        padding: '6px 14px', borderBottom: '1px solid var(--border)',
        display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)',
      }}>
        <span>总计 {tasks.length}</span>
        {done > 0 && <span style={{ color: 'var(--success)' }}>成功 {done}</span>}
        {failed > 0 && <span style={{ color: 'var(--danger)' }}>失败 {failed}</span>}
        {running > 0 && <span style={{ color: 'var(--info)' }}>运行中 {running}</span>}
      </div>

      {/* Task list */}
      {!collapsed && (
        <div ref={listRef} style={{ flex: 1, overflow: 'auto', padding: '6px 8px' }}>
          {tasks.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              暂无任务
            </div>
          )}
          {tasks.map(task => (
            <div key={task.id} onClick={() => task.meta && onTaskClick?.(task.meta)} style={{
              padding: '8px 10px', borderRadius: 8, marginBottom: 4,
              background: task.status === 'running' ? 'var(--accent-light)' : 'transparent',
              border: `1px solid ${task.status === 'running' ? 'rgba(16,185,129,0.15)' : 'transparent'}`,
              transition: 'all 0.2s',
              cursor: task.meta ? 'pointer' : 'default',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                {task.status === 'running' && <Loader2 size={12} className="spin" style={{ color: 'var(--accent)' }} />}
                {task.status === 'done' && <CheckCircle size={12} style={{ color: 'var(--success)' }} />}
                {task.status === 'error' && <XCircle size={12} style={{ color: 'var(--danger)' }} />}
                <span style={{
                  fontSize: 12, fontWeight: 500, flex: 1,
                  color: task.status === 'error' ? 'var(--danger)' : 'var(--text-primary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {task.label}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 18 }}>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{task.message}</span>
                <div style={{ flex: 1 }} />
                <span style={{
                  fontSize: 10, color: 'var(--text-muted)',
                  display: 'flex', alignItems: 'center', gap: 3,
                }}>
                  <Clock size={9} />
                  {formatElapsed(task.status === 'running' ? now - task.startTime : task.elapsed)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
