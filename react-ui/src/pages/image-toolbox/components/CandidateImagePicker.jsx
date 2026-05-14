import { Check, Copy, Download, Eye, ImagePlus, Pin, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import Lightbox from '../../../components/Lightbox'
import { MAX_IMAGE_COUNT } from '../constants'
import { assetUrl, downloadAsset } from '../helpers'

const slotLabel = index => `槽位 ${index + 1}`

export function CandidateImagePicker({
  batches = [],
  selectedSlots = [],
  styleAnchorImage,
  view = 'all',
  layout = 'grid',
  showSummary = true,
  onToggleCandidate,
  onFillBatch,
  onRemove,
  onSetAnchor,
  onClearSlot,
  onMoveSlot,
  onClearSlots,
  highlightedTaskId = '',
  highlightedBatchId = '',
  slotFooter = null,
}) {
  const [preview, setPreview] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)
  const selectedUrls = useMemo(() => selectedSlots.filter(Boolean).map(item => item.url), [selectedSlots])
  const selectedSet = useMemo(() => new Set(selectedUrls), [selectedUrls])
  const selectedCount = selectedUrls.length
  const missingCount = Math.max(0, MAX_IMAGE_COUNT - selectedCount)
  const totalImages = batches.reduce((sum, batch) => sum + (batch.images?.length || 0), 0)
  const showSlots = view === 'all' || view === 'slots'
  const showPool = view === 'all' || view === 'pool'

  const handleDrop = (targetIndex) => {
    if (dragIndex === null || dragIndex === targetIndex) return
    onMoveSlot(dragIndex, targetIndex)
    setDragIndex(null)
  }

  return (
    <div className={`image-tool-candidate-picker is-${layout}`}>
      {showSummary && (
        <div className="image-tool-candidate-summary">
          <strong>素材池 {totalImages} 张，成片槽位 {selectedCount}/{MAX_IMAGE_COUNT}</strong>
          <span>{missingCount ? `九宫格还差 ${missingCount} 张` : '9 个槽位已填满，可生成九宫格'}</span>
        </div>
      )}

      {showSlots && (
        <div className="image-tool-slot-board">
          <div className="image-tool-slot-board-head">
            <strong>9 图成片槽位</strong>
            <button type="button" onClick={onClearSlots} disabled={!selectedCount}>
              <RotateCcw size={14} />清空槽位
            </button>
          </div>
          <div className="image-tool-slot-grid">
            {Array.from({ length: MAX_IMAGE_COUNT }, (_, index) => {
              const slot = selectedSlots[index]
              return (
                <article
                  key={index}
                  className={`image-tool-slot-card ${slot ? 'is-filled' : ''}`}
                  draggable={Boolean(slot)}
                  onDragStart={() => slot && setDragIndex(index)}
                  onDragOver={event => event.preventDefault()}
                  onDrop={() => handleDrop(index)}
                >
                  {slot ? (
                    <>
                      <button type="button" className="image-tool-slot-preview" onClick={() => setPreview(slot)}>
                        <img src={assetUrl(slot.url)} alt={slotLabel(index)} loading="lazy" decoding="async" />
                      </button>
                      <button type="button" className="image-tool-slot-remove" onClick={() => onClearSlot(index)} title="移出槽位">
                        <X size={13} />
                      </button>
                      <span>{slotLabel(index)}</span>
                    </>
                  ) : (
                    <div className="image-tool-slot-empty">
                      <Plus size={16} />
                      <span>{slotLabel(index)}</span>
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        </div>
      )}
      {showSlots && slotFooter}

      {showPool && !batches.length && (
        <div className="image-tool-empty"><ImagePlus size={22} />生成后的候选素材会出现在这里</div>
      )}

      {showPool && batches.map((batch, batchIndex) => {
        const isLocated = Boolean(
          (highlightedTaskId && batch.task_id === highlightedTaskId)
          || (highlightedBatchId && batch.id === highlightedBatchId),
        )
        return (
        <section
          key={batch.id || batchIndex}
          className={`image-tool-candidate-batch ${isLocated ? 'is-located' : ''}`}
          data-image-task-id={batch.task_id || undefined}
          data-image-batch-id={batch.id || undefined}
        >
          <div className="image-tool-candidate-batch-head">
            <div>
              <strong>{batch.label || `第 ${batchIndex + 1} 批`}</strong>
              <span>成功 {batch.images?.length || 0}/{batch.requested_count || batch.images?.length || 0}，失败 {batch.failures?.length || 0}</span>
            </div>
            <button type="button" onClick={() => onFillBatch(batch.images || [])} disabled={!batch.images?.length || selectedCount >= MAX_IMAGE_COUNT}>
              <Plus size={14} />本批填入空槽
            </button>
          </div>
          <div className="image-tool-candidate-grid">
            {(batch.images || []).map((image, index) => {
              const selected = selectedSet.has(image.url)
              const isAnchor = styleAnchorImage?.url === image.url
              return (
                <article key={`${image.url}-${index}`} className={`image-tool-candidate-card ${selected ? 'is-selected' : ''} ${isAnchor ? 'is-anchor' : ''} ${isLocated ? 'is-located' : ''}`}>
                  <button type="button" className="image-tool-candidate-preview" onClick={() => setPreview(image)}>
                    <img src={assetUrl(image.url)} alt={`候选素材 ${index + 1}`} loading="lazy" decoding="async" />
                  </button>
                  <button type="button" className="image-tool-candidate-check" onClick={() => onToggleCandidate(image)} title={selected ? '移出槽位' : '放入槽位'}>
                    {selected ? <Check size={14} /> : <Plus size={14} />}
                  </button>
                  {isAnchor && <span className="image-tool-anchor-badge">样板</span>}
                  <div className="image-tool-candidate-meta">
                    <span>{image.filename || `候选 ${index + 1}`}</span>
                    <small>{selected ? '已进槽位' : '未进槽位'} · {batch.label || `第 ${batchIndex + 1} 批`}</small>
                  </div>
                  <div className="image-tool-candidate-actions">
                    <button type="button" onClick={() => setPreview(image)}><Eye size={14} />预览</button>
                    <button type="button" onClick={() => onSetAnchor(image)}><Pin size={14} />设样板</button>
                    <button type="button" onClick={() => downloadAsset(image.url, image.filename)}><Download size={14} />下载</button>
                    <button type="button" onClick={() => navigator.clipboard.writeText(image.url)}><Copy size={14} />复制</button>
                    <button type="button" onClick={() => onRemove(image.url)}><Trash2 size={14} />删除</button>
                  </div>
                </article>
              )
            })}
          </div>
        </section>
        )
      })}

      {preview && (
        <Lightbox src={assetUrl(preview.url)} alt={preview.filename || '候选素材预览'} onClose={() => setPreview(null)} />
      )}
    </div>
  )
}
