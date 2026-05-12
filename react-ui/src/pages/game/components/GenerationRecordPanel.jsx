import { CheckCircle, Clock, Download, Loader2, RefreshCw, X } from 'lucide-react'
import { formatProviderVideoCacheError, isProviderVideoCacheError, mediaUrl } from '../gameVideoPageHelpers'

const RECORD_HISTORY_PREVIEW_LIMIT = 3

export default function GenerationRecordPanel({
  recordScenes,
  models,
  completedCount,
  processingCount,
  elapsed,
  retryingResultCacheTaskIds,
  onRemoveCurrentVideo,
  onRetryResultCache,
  onSelectHistoryVideo,
}) {
  const getModelName = scene => models.find(model => model.id === scene.model)?.name || scene.model
  const canRetryResultCache = scene => !!scene.taskId && isProviderVideoCacheError(scene.error) && typeof onRetryResultCache === 'function'
  const renderRetryResultCacheButton = scene => {
    if (!canRetryResultCache(scene)) return null
    const retrying = retryingResultCacheTaskIds?.has?.(scene.taskId)
    return (
      <button
        type="button"
        onClick={() => onRetryResultCache(scene.id)}
        disabled={retrying}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#2563eb', background: 'none', border: 'none', padding: 0, cursor: retrying ? 'default' : 'pointer', fontWeight: 700 }}
      >
        {retrying ? <Loader2 size={10} className="spin" /> : <RefreshCw size={10} />}
        重新拉取结果
      </button>
    )
  }

  return (
    <div style={{ width: 280, flexShrink: 0, background: 'var(--bg-secondary)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>生成记录</span>
        <div style={{ display: 'flex', gap: 6, fontSize: 11 }}>
          {completedCount > 0 && <span style={{ color: '#10b981', fontWeight: 600 }}>{completedCount} 完成</span>}
          {processingCount > 0 && <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{processingCount} 进行中</span>}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 10 }}>
        {recordScenes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 11 }}>
            <Clock size={24} style={{ opacity: 0.3, marginBottom: 8 }} /><br />点击"生成视频"开始
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {recordScenes.map(scene => (
              <div key={scene.id} style={{ background: 'var(--bg-primary)', borderRadius: 10, overflow: 'hidden', border: '1px solid var(--border)' }}>
                {scene.videoUrl ? (
                  <div style={{ position: 'relative' }}>
                    <video src={mediaUrl(scene.videoUrl)} controls preload="none" style={{ width: '100%', aspectRatio: '16/9', background: '#000', display: 'block' }} />
                    <span style={{ position: 'absolute', top: 4, left: 4, background: 'rgba(16,185,129,0.85)', color: '#fff', fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3 }}>当前</span>
                  </div>
                ) : (scene.status === 'processing' || scene.status === 'generating') ? (
                  <div style={{ width: '100%', aspectRatio: '16/9', background: 'var(--bg-tertiary)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                    <Loader2 size={20} color="var(--accent)" className="spin" />
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 5 }}>生成中 ({elapsed(scene.startTime)}s)</span>
                  </div>
                ) : scene.status === 'failed' ? (
                  <div style={{ width: '100%', aspectRatio: '16/9', background: 'var(--bg-tertiary)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, padding: 10, boxSizing: 'border-box', textAlign: 'center' }}>
                    <span style={{ color: '#ef4444', fontSize: 11 }}>生成失败</span>
                    {renderRetryResultCacheButton(scene)}
                  </div>
                ) : null}
                <div style={{ padding: '6px 10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)' }}>场景 {scene.idx}</span>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{getModelName(scene)}</span>
                  </div>
                  {scene.videoUrl && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 3 }}>
                      <a href={mediaUrl(scene.videoUrl)} download={`场景${scene.idx}.mp4`} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#10b981', textDecoration: 'none', fontWeight: 600 }}><Download size={10} /> 保存到本地</a>
                      <button type="button" onClick={() => onRemoveCurrentVideo(scene.id)} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, border: 'none', background: 'none', color: '#ef4444', fontSize: 10, padding: 0, cursor: 'pointer' }}><X size={10} /> 删除记录</button>
                    </div>
                  )}
                  {!scene.videoUrl && formatProviderVideoCacheError(scene.error) && (
                    <div style={{ marginTop: 4, fontSize: 10, lineHeight: 1.5, color: '#ef4444' }}>
                      {formatProviderVideoCacheError(scene.error)}
                    </div>
                  )}
                </div>
                {(scene.videoHistory || []).length > 0 && (
                  <div style={{ padding: '4px 10px 8px', borderTop: '1px solid var(--border)' }}>
                    <div style={{ fontSize: 9, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>历史版本</div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {(scene.videoHistory || []).slice(0, RECORD_HISTORY_PREVIEW_LIMIT).map((video, historyIndex) => (
                        <div key={historyIndex} style={{ width: 56, borderRadius: 4, overflow: 'hidden', border: '1px solid var(--border)', cursor: 'pointer', position: 'relative', background: '#000' }}
                          onClick={() => onSelectHistoryVideo(scene.id, historyIndex)}>
                          <video src={mediaUrl(video.url)} preload="none" style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block', opacity: 0.85 }} />
                          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.2)' }}>
                            <CheckCircle size={10} color="#fff" style={{ opacity: 0.8 }} />
                          </div>
                          <span style={{ position: 'absolute', bottom: 1, left: 2, fontSize: 7, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}>v{historyIndex + 1}</span>
                        </div>
                      ))}
                      {scene.videoHistory.length > RECORD_HISTORY_PREVIEW_LIMIT && (
                        <div style={{ width: 56, aspectRatio: '16/9', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-tertiary)', color: 'var(--text-muted)', fontSize: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
                          +{scene.videoHistory.length - RECORD_HISTORY_PREVIEW_LIMIT}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
