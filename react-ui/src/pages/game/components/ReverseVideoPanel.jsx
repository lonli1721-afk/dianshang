import { Loader2, Scan, Upload, X } from 'lucide-react'
import { mediaUrl } from '../gameVideoPageHelpers'

export default function ReverseVideoPanel({
  active,
  videoUrl,
  durationSeconds,
  model,
  models,
  result,
  loading,
  history,
  formatDurationSeconds,
  onUploadVideo,
  onClearVideo,
  onModelChange,
  onAnalyze,
  onResultChange,
  onCopyResult,
  onSelectHistory,
  onRemoveHistoryItem,
}) {
  if (!active) return null

  const canReverse = !!videoUrl && !loading
  const buttonBg = canReverse ? 'var(--accent-gradient)' : 'var(--bg-primary)'
  const buttonColor = canReverse ? '#fff' : 'var(--text-muted)'
  const buttonBorder = canReverse ? 'none' : '1px solid var(--border)'

  return (
    <div>
      <div style={{ maxWidth: 700, margin: '0 auto' }}>
        <div style={{ background: 'var(--bg-secondary)', borderRadius: 14, border: '1px solid var(--border)', padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Scan size={18} color="var(--accent)" />
            <span style={{ fontSize: 15, fontWeight: 600 }}>视频反推提示词</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>上传视频，AI 自动分析并生成可复刻的提示词</span>
          </div>

          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              {videoUrl ? (
                <>
                  <div style={{ position: 'relative' }}>
                    <video src={mediaUrl(videoUrl)} controls preload="none" style={{ width: '100%', maxHeight: 240, borderRadius: 10, background: '#000', display: 'block' }} />
                    <button onClick={onClearVideo} style={{ position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,0.7)', color: '#fff', borderRadius: 6, padding: 3, lineHeight: 0 }}><X size={14} /></button>
                  </div>
                  {formatDurationSeconds(durationSeconds) && (
                    <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                      检测到真实时长 {formatDurationSeconds(durationSeconds)}
                    </div>
                  )}
                </>
              ) : (
                <button onClick={onUploadVideo} style={{
                  width: '100%', padding: '40px 0', borderRadius: 10, background: 'var(--bg-primary)',
                  border: '2px dashed var(--border)', color: 'var(--text-muted)', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
                }}>
                  <Upload size={28} style={{ opacity: 0.4 }} />
                  <span style={{ fontSize: 13 }}>点击上传参考视频</span>
                  <span style={{ fontSize: 10, opacity: 0.6 }}>支持 mp4、webm、mov</span>
                </button>
              )}
            </div>
            <div style={{ width: 180, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <label style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, display: 'block' }}>分析模型</label>
                <select value={model} onChange={event => onModelChange(event.target.value)} style={{
                  width: '100%', padding: '6px 8px', borderRadius: 6, background: 'var(--bg-primary)',
                  border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 11,
                }}>
                  {models.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </div>
              <button onClick={onAnalyze} disabled={!canReverse} style={{
                padding: '10px 0', borderRadius: 8, fontSize: 12, fontWeight: 600,
                background: buttonBg,
                color: buttonColor,
                border: buttonBorder,
                cursor: canReverse ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
              }}>
                {loading ? <><Loader2 size={13} className="spin" /> 分析中...</> : <><Scan size={13} /> 反推提示词</>}
              </button>
            </div>
          </div>

          {result && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>反推结果</span>
                <button type="button" onMouseDown={event => event.preventDefault()} onClick={onCopyResult} style={{
                  padding: '3px 10px', borderRadius: 5, fontSize: 10, background: 'rgba(16,185,129,0.1)',
                  color: '#10b981', border: '1px solid rgba(16,185,129,0.2)', fontWeight: 600,
                }}>复制</button>
              </div>
              <textarea
                id="game-reverse-result"
                value={result}
                onChange={event => onResultChange(event.target.value)}
                style={{
                  width: '100%', minHeight: 160, padding: 12, borderRadius: 10,
                  background: 'var(--bg-primary)', border: '1px solid var(--border)',
                  color: 'var(--text-primary)', fontSize: 12, lineHeight: 1.6, resize: 'vertical',
                }} />
              <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
                提示：可直接复制此提示词到「生成视频」或「视频替换」板块使用。
              </p>
            </div>
          )}

          {history.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>反推历史 ({history.length})</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {history.map((item, index) => {
                  const modelLabel = models.find(modelItem => modelItem.id === item.model)?.name || item.model
                  const isCurrent = item.video_url === videoUrl && item.model === model && item.result === result
                  return (
                    <div
                      key={`${item.ts}-${index}`}
                      onClick={() => onSelectHistory(item)}
                      style={{
                        display: 'flex', gap: 10, padding: 10, borderRadius: 10, cursor: 'pointer',
                        border: isCurrent ? '2px solid var(--accent)' : '1px solid var(--border)',
                        background: 'var(--bg-primary)', alignItems: 'flex-start',
                      }}
                    >
                      <div style={{ width: 100, flexShrink: 0, borderRadius: 8, overflow: 'hidden', background: '#000', lineHeight: 0 }}>
                        <video src={mediaUrl(item.video_url)} preload="none" style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }} muted playsInline />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>{modelLabel} · {item.ts ? new Date(item.ts).toLocaleString() : ''}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.45, maxHeight: 44, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{item.result}</div>
                      </div>
                      <button type="button" title="从历史中移除" onClick={event => { event.stopPropagation(); onRemoveHistoryItem(index) }} style={{ flexShrink: 0, background: 'none', color: 'var(--text-muted)', padding: 4, lineHeight: 0 }}><X size={16} /></button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
