import { Loader2, RefreshCw, Upload, User, Video, X } from 'lucide-react'
import { formatProviderVideoCacheError, isProviderVideoCacheError, mediaUrl } from '../gameVideoPageHelpers'
import { VIDEO_RESOLUTION_OPTIONS } from '../gameVideoConstants'

function selectSingleFile(accept, onSelect) {
  if (typeof document === 'undefined') return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = accept
  input.onchange = (event) => {
    const file = event.target.files?.[0]
    if (file) void onSelect(file)
  }
  input.click()
}

export default function ReplaceVideoPanel({
  active,
  providerSpecs,
  provider,
  providerSpec,
  blockReason,
  durationHint,
  charImage,
  refVideo,
  prompt,
  videoResolution,
  wanMode,
  wanCheckImage,
  status,
  error,
  videoUrl,
  taskId,
  retryingResultCache,
  startTime,
  history,
  elapsed,
  onProviderChange,
  onOpenImage,
  onClearCharacterImage,
  onCharacterFileSelected,
  onClearReferenceVideo,
  onReferenceVideoFileSelected,
  onPromptChange,
  onResolutionChange,
  onWanModeChange,
  onWanCheckImageChange,
  onRun,
  onRetryResultCache,
  onResetResult,
  onSelectHistory,
  onRemoveHistoryItem,
}) {
  if (!active) return null

  const canRunReplace = status !== 'processing' && !blockReason
  const buttonBg = canRunReplace ? 'var(--accent-gradient)' : 'rgba(124,58,237,0.14)'
  const buttonColor = canRunReplace ? '#fff' : 'rgba(124,58,237,0.95)'
  const buttonBorder = canRunReplace ? 'none' : '1px solid rgba(124,58,237,0.25)'
  const buttonShadow = canRunReplace ? '0 6px 18px rgba(59,130,246,0.22)' : 'none'
  const canRetryResultCache = !!taskId && isProviderVideoCacheError(error) && typeof onRetryResultCache === 'function'
  const displayError = formatProviderVideoCacheError(error)

  return (
    <div>
      <div style={{ maxWidth: 700, margin: '0 auto' }}>
        <div style={{ background: 'var(--bg-secondary)', borderRadius: 14, border: '1px solid var(--border)', padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <RefreshCw size={18} color="var(--accent)" />
            <span style={{ fontSize: 15, fontWeight: 600 }}>视频换人</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>上传角色图片 + 参考视频，AI 替换视频中的人物，保持动作/场景不变</span>
          </div>

          <div style={{ marginBottom: 14, display: 'flex', gap: 8 }}>
            {providerSpecs.map(item => (
              <button key={item.id} onClick={() => onProviderChange(item.id)} style={{
                flex: 1, padding: '8px 10px', borderRadius: 8, textAlign: 'left',
                background: provider === item.id ? 'rgba(139,92,246,0.1)' : 'var(--bg-primary)',
                border: provider === item.id ? '1.5px solid var(--accent)' : '1px solid var(--border)',
                cursor: 'pointer',
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: provider === item.id ? 'var(--accent)' : 'var(--text-primary)' }}>{item.label}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{item.desc}</div>
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6, display: 'block' }}>
                <User size={12} style={{ verticalAlign: -2, marginRight: 4 }} />替换角色图片（必须）
              </label>
              {charImage ? (
                <div
                  role="button"
                  tabIndex={0}
                  title="点击查看大图"
                  onClick={() => onOpenImage(charImage.url)}
                  onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onOpenImage(charImage.url) } }}
                  style={{ position: 'relative', display: 'inline-block', cursor: 'pointer' }}
                >
                  <img src={mediaUrl(charImage.url)} alt="" loading="lazy" decoding="async" style={{ width: 120, height: 120, objectFit: 'cover', borderRadius: 10, border: '2px solid var(--accent)', display: 'block', pointerEvents: 'none', userSelect: 'none' }} />
                  <button type="button" onClick={event => { event.stopPropagation(); onClearCharacterImage() }} style={{ position: 'absolute', top: 4, right: 4, background: 'rgba(0,0,0,0.7)', color: '#fff', borderRadius: 6, padding: 3, lineHeight: 0, zIndex: 1 }}><X size={12} /></button>
                </div>
              ) : (
                <button onClick={() => selectSingleFile('image/*', onCharacterFileSelected)} style={{
                  width: 120, height: 120, borderRadius: 10, background: 'var(--bg-primary)',
                  border: '2px dashed rgba(139,92,246,0.3)', color: 'var(--accent)', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}>
                  <User size={24} style={{ opacity: 0.5 }} />
                  <span style={{ fontSize: 11 }}>上传角色</span>
                </button>
              )}
            </div>

            <div style={{ flex: 2 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6, display: 'block' }}>
                <Video size={12} style={{ verticalAlign: -2, marginRight: 4 }} />参考视频（必须）
              </label>
              {refVideo ? (
                <>
                  <div style={{ position: 'relative' }}>
                    <video src={mediaUrl(refVideo)} controls preload="none" style={{ width: '100%', maxHeight: 200, borderRadius: 10, background: '#000', display: 'block' }} />
                    <button onClick={onClearReferenceVideo} style={{ position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,0.7)', color: '#fff', borderRadius: 6, padding: 3, lineHeight: 0 }}><X size={14} /></button>
                  </div>
                  {durationHint && (
                    <div style={{
                      marginTop: 6, fontSize: 11, lineHeight: 1.6,
                      color: blockReason ? '#ef4444' : '#10b981',
                    }}>
                      {durationHint}
                    </div>
                  )}
                </>
              ) : (
                <button onClick={() => selectSingleFile('video/*', onReferenceVideoFileSelected)} style={{
                  width: '100%', padding: '40px 0', borderRadius: 10, background: 'var(--bg-primary)',
                  border: '2px dashed var(--border)', color: 'var(--text-muted)', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
                }}>
                  <Upload size={24} style={{ opacity: 0.4 }} />
                  <span style={{ fontSize: 12 }}>上传要替换的原视频</span>
                  <span style={{ fontSize: 10, opacity: 0.6 }}>{providerSpec.uploadHint}</span>
                </button>
              )}
            </div>
          </div>

          {providerSpec.supports_prompt && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, display: 'block' }}>提示词（可选）</label>
              <textarea value={prompt} onChange={event => onPromptChange(event.target.value)} placeholder="可描述动作、表情等（留空则自动模仿参考视频动作）"
                style={{ width: '100%', padding: '8px 12px', borderRadius: 8, background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 12, resize: 'vertical', minHeight: 40, maxHeight: 100, boxSizing: 'border-box' }} />
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>清晰度</label>
                <select value={videoResolution} onChange={event => onResolutionChange(event.target.value)}
                  style={{ padding: '4px 8px', borderRadius: 6, background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 11 }}>
                  {VIDEO_RESOLUTION_OPTIONS
                    .filter(option => !providerSpec.supported_resolutions || providerSpec.supported_resolutions.includes(option.id))
                    .map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>1080P 更接近网页端质感，费用更高</span>
              </div>
            </div>
          )}

          {providerSpec.wan_modes && (
            <div style={{ marginBottom: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>万相模式</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {providerSpec.wan_modes.map(mode => (
                  <button key={mode.id} type="button" onClick={() => onWanModeChange(mode.id)} style={{
                    padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                    background: wanMode === mode.id ? 'rgba(139,92,246,0.12)' : 'var(--bg-primary)',
                    color: wanMode === mode.id ? 'var(--accent)' : 'var(--text-muted)',
                    border: wanMode === mode.id ? '1px solid rgba(139,92,246,0.35)' : '1px solid var(--border)',
                  }}>
                    {mode.label}<span style={{ marginLeft: 4, fontSize: 9, opacity: 0.65 }}>{mode.desc}</span>
                  </button>
                ))}
              </div>
              {providerSpec.supports_check_image && (
                <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer' }}>
                  <input type="checkbox" checked={wanCheckImage} onChange={event => onWanCheckImageChange(event.target.checked)} />
                  严格检测人像
                </label>
              )}
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <button onClick={onRun} title={blockReason} disabled={status === 'processing' || !!blockReason} style={{
              width: '100%', padding: '10px 0', borderRadius: 10, fontSize: 13, fontWeight: 700,
              background: buttonBg, color: buttonColor, border: buttonBorder, boxShadow: buttonShadow,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              cursor: canRunReplace ? 'pointer' : 'not-allowed',
            }}>
              {status === 'processing' ? <><Loader2 size={14} className="spin" /> 处理中 ({elapsed(startTime)}s)</> : <><RefreshCw size={14} /> {providerSpec.actionLabel}</>}
            </button>
            {blockReason && (
              <div style={{
                marginTop: 8,
                fontSize: 11,
                lineHeight: 1.6,
                color: 'rgba(124,58,237,0.95)',
                background: 'rgba(124,58,237,0.08)',
                border: '1px solid rgba(124,58,237,0.16)',
                borderRadius: 8,
                padding: '8px 10px',
              }}>
                {blockReason}
              </div>
            )}
          </div>

          {displayError && (
            <div style={{ fontSize: 11, color: '#ef4444', marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
              <span style={{ lineHeight: 1.6 }}>{displayError}</span>
              {canRetryResultCache && (
                <button type="button" onClick={onRetryResultCache} disabled={retryingResultCache} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '5px 9px', borderRadius: 6, fontSize: 11, fontWeight: 700, background: 'rgba(59,130,246,0.1)', color: '#2563eb', border: '1px solid rgba(59,130,246,0.2)', cursor: retryingResultCache ? 'default' : 'pointer' }}>
                  {retryingResultCache ? <Loader2 size={11} className="spin" /> : <RefreshCw size={11} />}
                  重新拉取结果
                </button>
              )}
            </div>
          )}

          {videoUrl && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>替换结果</div>
              <video src={mediaUrl(videoUrl)} controls preload="none" style={{ width: '100%', maxHeight: 360, borderRadius: 10, background: '#000', display: 'block' }} />
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <a href={mediaUrl(videoUrl)} download target="_blank" rel="noreferrer" style={{ flex: 1, padding: '8px 0', borderRadius: 6, fontSize: 12, fontWeight: 600, background: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.2)', textAlign: 'center', textDecoration: 'none' }}>下载视频</a>
                <button onClick={onResetResult} style={{ flex: 1, padding: '8px 0', borderRadius: 6, fontSize: 12, fontWeight: 600, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>重新替换</button>
              </div>
            </div>
          )}

          {history.length > 0 && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>历史记录 ({history.length})</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                {history.map((item, index) => (
                  <div key={index} style={{ borderRadius: 8, overflow: 'hidden', border: item.url === videoUrl ? '2px solid var(--accent)' : '1px solid var(--border)', background: '#000', cursor: 'pointer', position: 'relative' }}
                    onClick={() => onSelectHistory(item)}>
                    <video src={mediaUrl(item.url)} preload="none" style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }} />
                    <div style={{ padding: '4px 6px', background: 'var(--bg-tertiary)', fontSize: 10, color: 'var(--text-muted)' }}>
                      {new Date(item.ts).toLocaleString()}
                    </div>
                    <button type="button" title="从历史中移除" onClick={event => { event.stopPropagation(); onRemoveHistoryItem(index) }} style={{ position: 'absolute', top: 4, right: 4, background: 'rgba(0,0,0,0.75)', color: '#fff', borderRadius: 6, padding: 2, lineHeight: 0, zIndex: 1 }}><X size={12} /></button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: 8, background: 'rgba(139,92,246,0.05)', border: '1px solid rgba(139,92,246,0.1)' }}>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0, lineHeight: 1.8 }}>
              {providerSpec.infoText}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
