import { FileDown, Loader2, Plus, Settings, Video } from 'lucide-react'

export function GenerateVideoActions({
  processingCount,
  completedCount,
  estimateTotalCost,
  onAddScene,
  onGenerateAll,
  onDownloadAll,
  onOpenSettings,
}) {
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <button onClick={onAddScene} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '7px 13px', borderRadius: 7, fontSize: 12, fontWeight: 500, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}><Plus size={14} /> 添加场景</button>
      <button onClick={onGenerateAll} disabled={processingCount > 0} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '7px 15px', borderRadius: 7, fontSize: 12, fontWeight: 600, background: processingCount > 0 ? 'var(--bg-tertiary)' : 'var(--accent-gradient)', color: '#fff' }}>
        {processingCount > 0 ? <><Loader2 size={13} className="spin" /> 生成中 ({processingCount})</> : <><Video size={13} /> 全部生成{estimateTotalCost != null && <span style={{ opacity: 0.8, fontWeight: 400 }}> ≈{estimateTotalCost}</span>}</>}
      </button>
      {completedCount > 0 && (
        <button onClick={onDownloadAll} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '7px 13px', borderRadius: 7, fontSize: 12, fontWeight: 600, background: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)' }}><FileDown size={14} /> 全部导出 ({completedCount})</button>
      )}
      <button onClick={onOpenSettings} title="API 设置" style={{ background: 'none', color: 'var(--text-muted)', padding: '6px 8px' }}><Settings size={16} /></button>
    </div>
  )
}

export default function GenerateVideoPanel({
  active,
  scenes,
  renderSceneCard,
  onAddScene,
}) {
  if (!active) return null

  return (
    <div style={{ width: '100%', maxWidth: 1520, margin: '0 auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <button onClick={onAddScene} style={{ padding: 16, borderRadius: 14, background: 'none', border: '2px dashed var(--border)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: 14, cursor: 'pointer' }}>
          <Plus size={17} /> 添加新场景
        </button>
        {scenes.map(scene => renderSceneCard(scene))}
      </div>
    </div>
  )
}
