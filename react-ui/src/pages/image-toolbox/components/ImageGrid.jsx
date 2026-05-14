import { Check, Copy, Download, Eye, Pin, Plus, X } from 'lucide-react'
import { useState } from 'react'
import Lightbox from '../../../components/Lightbox'
import { assetUrl, downloadAsset } from '../helpers'

export function ImageGrid({
  images,
  onRemove,
  emptyText = '还没有图片',
  selectedUrls = [],
  styleAnchorImage,
  onToggle,
  onSetAnchor,
  showActions = false,
}) {
  const [preview, setPreview] = useState(null)
  const selectedSet = new Set(selectedUrls)

  if (!images.length) {
    return <div className="image-tool-empty"><Plus size={22} />{emptyText}</div>
  }

  return (
    <>
      <div className="image-tool-grid">
        {images.map((image, index) => {
          const selected = selectedSet.has(image.url)
          const isAnchor = styleAnchorImage?.url === image.url
          return (
            <div className={`image-tool-thumb ${selected ? 'is-selected' : ''} ${isAnchor ? 'is-anchor' : ''}`} key={`${image.url}-${index}`}>
              <button type="button" className="image-tool-thumb-preview" onClick={() => setPreview(image)}>
                <img src={assetUrl(image.url)} alt={image.name || `图片 ${index + 1}`} loading="lazy" decoding="async" />
              </button>
              {isAnchor && <span className="image-tool-anchor-badge">样板</span>}
              <div className="image-tool-thumb-meta">
                <span>{image.name || image.filename || `图片 ${index + 1}`}</span>
                {selected && <small>已进槽位</small>}
              </div>
              {showActions && (
                <div className="image-tool-thumb-actions">
                  {onToggle && (
                    <button type="button" onClick={() => onToggle(image)}>
                      {selected ? <Check size={14} /> : <Plus size={14} />}
                      {selected ? '移出' : '入槽'}
                    </button>
                  )}
                  <button type="button" onClick={() => setPreview(image)}><Eye size={14} />预览</button>
                  {onSetAnchor && <button type="button" onClick={() => onSetAnchor(image)}><Pin size={14} />样板</button>}
                  <button type="button" onClick={() => downloadAsset(image.url, image.filename || image.name)}><Download size={14} />下载</button>
                  <button type="button" onClick={() => navigator.clipboard.writeText(image.url)}><Copy size={14} />复制</button>
                </div>
              )}
              {onRemove && (
                <button type="button" className="image-tool-remove" onClick={() => onRemove(index)} title="移除">
                  <X size={14} />
                </button>
              )}
            </div>
          )
        })}
      </div>
      {preview && (
        <Lightbox src={assetUrl(preview.url)} alt={preview.filename || preview.name || '图片预览'} onClose={() => setPreview(null)} />
      )}
    </>
  )
}
