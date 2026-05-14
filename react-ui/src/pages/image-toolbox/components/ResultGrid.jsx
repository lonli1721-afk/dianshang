import { Copy, Download, Eye, Pin, Plus } from 'lucide-react'
import { useState } from 'react'
import Lightbox from '../../../components/Lightbox'
import { assetUrl, downloadAsset } from '../helpers'

function ResultCard({ image, label, onPreview, onAddImageToWorkspace, onSetAnchor }) {
  return (
    <div className="image-tool-result-card">
      <button type="button" className="image-tool-result-preview" onClick={() => onPreview(image)}>
        <img src={assetUrl(image.url)} alt={label} loading="lazy" decoding="async" />
      </button>
      <div className="image-tool-result-actions">
        <button type="button" onClick={() => onPreview(image)}><Eye size={14} />预览</button>
        <button type="button" onClick={() => downloadAsset(image.url, image.filename || `${label}.png`)}><Download size={14} />下载</button>
        <button type="button" onClick={() => navigator.clipboard.writeText(image.url)}><Copy size={14} />复制链接</button>
        {onAddImageToWorkspace && (
          <button type="button" onClick={() => onAddImageToWorkspace(image)}><Plus size={14} />入槽</button>
        )}
        {onSetAnchor && (
          <button type="button" onClick={() => onSetAnchor(image)}><Pin size={14} />样板</button>
        )}
      </div>
    </div>
  )
}

export function ResultGrid({ images = [], grid, prompt, onAddImageToWorkspace, onSetAnchor }) {
  const [preview, setPreview] = useState(null)
  if (!images.length && !grid && !prompt) return null

  return (
    <>
      <div className="image-tool-results">
        {prompt && (
          <div className="image-tool-prompt-box">
            <div>
              <strong>实际使用提示词</strong>
              <button type="button" onClick={() => navigator.clipboard.writeText(prompt)}><Copy size={14} />复制</button>
            </div>
            <p>{prompt}</p>
          </div>
        )}

        {grid && (
          <div className="image-tool-grid-output">
            <div className="image-tool-panel-title">九宫格合成图</div>
            <ResultCard image={grid} label="九宫格结果" onPreview={setPreview} />
          </div>
        )}

        {!!images.length && (
          <div className="image-tool-result-grid">
            {images.map((image, index) => (
              <ResultCard
                image={image}
                label={`结果 ${index + 1}`}
                key={`${image.url}-${index}`}
                onPreview={setPreview}
                onAddImageToWorkspace={onAddImageToWorkspace}
                onSetAnchor={onSetAnchor}
              />
            ))}
          </div>
        )}
      </div>
      {preview && (
        <Lightbox src={assetUrl(preview.url)} alt={preview.filename || '图片预览'} onClose={() => setPreview(null)} />
      )}
    </>
  )
}
