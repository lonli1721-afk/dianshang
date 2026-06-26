import { WATERMARK_FONT_STYLES, WATERMARK_OUTPUT_MODES, WATERMARK_POSITIONS } from '../constants'
import { assetUrl } from '../helpers'
import { Field } from './Field'
import { UploadTile } from './UploadTile'

export function WatermarkControls({
  text,
  setText,
  outputMode,
  setOutputMode,
  position,
  setPosition,
  fontStyle,
  setFontStyle,
  opacity,
  setOpacity,
  color,
  setColor,
  strokeColor,
  setStrokeColor,
  fontOptions,
  selectedFontId,
  setSelectedFontId,
  fontUrl,
  setFontUrl,
  fontName,
  setFontName,
  fontUploading,
  uploadFont,
  disabled,
}) {
  return (
    <>
      <Field label="水印文字">
        <textarea rows={3} value={text} onChange={event => setText(event.target.value)} placeholder="例：户外保温杯商品图" />
      </Field>
      <div className="image-tool-form-grid">
        <Field label="成品类型">
          <select value={outputMode} onChange={event => setOutputMode(event.target.value)}>
            {WATERMARK_OUTPUT_MODES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="位置">
          <select value={position} onChange={event => setPosition(event.target.value)}>
            {WATERMARK_POSITIONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="字体风格">
          <select value={fontStyle} onChange={event => setFontStyle(event.target.value)}>
            {WATERMARK_FONT_STYLES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="透明度">
          <input type="number" min="10" max="100" value={opacity} onChange={event => setOpacity(Number(event.target.value || 100))} />
        </Field>
        <Field label="文字颜色">
          <input type="color" value={color} onChange={event => setColor(event.target.value)} />
        </Field>
        <Field label="描边颜色">
          <input type="color" value={strokeColor} onChange={event => setStrokeColor(event.target.value)} />
        </Field>
      </div>
      <Field label="字体选择">
        <div className="image-tool-font-grid">
          {fontOptions.map(font => (
            <button
              type="button"
              key={font.id}
              className={selectedFontId === font.id ? 'is-active' : ''}
              onClick={() => {
                setSelectedFontId(font.id)
                setFontUrl(font.font_url || '')
                setFontName(font.font_url ? font.name : '')
              }}
            >
              {font.preview_url ? <img src={assetUrl(font.preview_url)} alt={font.name} loading="lazy" decoding="async" /> : null}
              <span>{font.name}</span>
              <small>{font.source}</small>
            </button>
          ))}
        </div>
      </Field>
      <UploadTile
        label={fontName ? `当前字体：${fontName}` : '上传字体文件，可用剪映字体'}
        accept=".ttf,.otf,.ttc"
        multiple={false}
        disabled={disabled || fontUploading}
        onFiles={uploadFont}
      />
      {fontUrl && (
        <button type="button" className="image-tool-secondary" disabled={disabled} onClick={() => { setFontUrl(''); setFontName(''); setSelectedFontId(fontOptions[0]?.id || '') }}>
          使用默认字体
        </button>
      )}
    </>
  )
}
