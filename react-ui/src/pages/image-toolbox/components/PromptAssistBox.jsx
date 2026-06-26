import { Copy, FileImage, Loader2, LockKeyhole, PenLine, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { FRIEND_CIRCLE_NINE_GRID_STYLE, REVERSE_MODELS, STYLE_LOCK_OPTIONS } from '../constants'
import { assetUrl, displayError, updateImageToolWorkspacePrompt } from '../helpers'
import { polishImagePrompt, reverseStylePrompt } from '../imageToolboxApi'
import { Field } from './Field'
import { ImageGrid } from './ImageGrid'
import { UploadTile } from './UploadTile'

const PROMPT_SOURCE_MODES = [
  { id: 'manual', label: '手动输入', hint: '自己写内容和画风', icon: PenLine },
  { id: 'reverse', label: '参考图反推', hint: '从图片提取风格提示词', icon: FileImage },
  { id: 'polish', label: 'AI 润色', hint: '把当前提示词整理清楚', icon: Sparkles },
]

export function PromptAssistBox({
  theme,
  visualStyle,
  onThemeChange,
  onVisualStyleChange,
  uploadImages,
  setNotice,
  styleLock,
  onStyleLockChange,
  styleLockOptions,
  onStyleLockOptionsChange,
  variationPolicy,
  onVariationPolicyChange,
  styleAnchorImage,
  onStyleAnchorChange,
  onApplyFriendCirclePreset,
  disabled = false,
}) {
  const [mode, setMode] = useState('manual')
  const [styleRefs, setStyleRefs] = useState([])
  const [model, setModel] = useState('gemini-2.5-flash')
  const [loading, setLoading] = useState(false)
  const [reversePayload, setReversePayload] = useState(null)
  const [reversePromptMode, setReversePromptMode] = useState('full')

  const applyPromptPayload = (data) => {
    const nextTheme = (data.theme || '').trim()
    const nextStyle = (data.prompt || data.visual_style || data.style_summary || '').trim()
    if (nextTheme) onThemeChange(nextTheme)
    if (nextStyle) onVisualStyleChange(nextStyle)
  }

  const applyReversePayload = (data, promptMode = reversePromptMode) => {
    const nextTheme = (data.theme || data.subject || '').trim()
    const fullPrompt = (data.prompt || data.visual_style || data.style_summary || '').trim()
    const summaryPrompt = (data.style_summary || data.visual_style || fullPrompt).trim()
    if (nextTheme) onThemeChange(nextTheme)
    const nextStyle = promptMode === 'summary' ? summaryPrompt : fullPrompt
    onVisualStyleChange(nextStyle)
    updateImageToolWorkspacePrompt({ theme: nextTheme, visualStyle: nextStyle, reversePayload: data })
  }

  const applyStyleRefs = (images) => {
    setStyleRefs(images)
    setReversePayload(null)
  }

  const toggleStyleLockOption = (id) => {
    const current = new Set(styleLockOptions)
    if (current.has(id)) {
      current.delete(id)
    } else {
      current.add(id)
    }
    onStyleLockOptionsChange(Array.from(current))
  }

  const applyFriendCirclePreset = () => {
    onVisualStyleChange(FRIEND_CIRCLE_NINE_GRID_STYLE)
    onStyleLockChange('strict')
    onVariationPolicyChange('subject_only')
    onStyleLockOptionsChange(STYLE_LOCK_OPTIONS.map(item => item.id))
    onApplyFriendCirclePreset?.()
  }

  const runReverseStyle = async ({ setAnchor = true } = {}) => {
    if (!styleRefs.length) {
      setNotice('请先上传一张要参考风格的图片。')
      return
    }

    setLoading(true)
    setNotice('')
    try {
      const data = await reverseStylePrompt({ image_url: styleRefs[0].url, model })
      setReversePayload(data)
      setReversePromptMode('full')
      applyReversePayload(data, 'full')
      if (setAnchor) onStyleAnchorChange?.(styleRefs[0])
      setNotice(setAnchor ? '已反推提示词，并设为风格样板。' : '已反推并填入提示词。')
    } catch (error) {
      setNotice(displayError(error))
    } finally {
      setLoading(false)
    }
  }

  const runPolish = async () => {
    if (!theme.trim() && !visualStyle.trim()) {
      setNotice('请先填写画面内容或画风提示词，再让 AI 润色。')
      return
    }

    setLoading(true)
    setNotice('')
    try {
      const data = await polishImagePrompt({ theme, visual_style: visualStyle, model })
      applyPromptPayload(data)
      setNotice('已润色并回填提示词。')
    } catch (error) {
      setNotice(displayError(error))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="image-tool-prompt-assist">
      <Field label="画面内容">
        <textarea rows={2} value={theme} onChange={event => onThemeChange(event.target.value)} placeholder="例：户外保温杯商品图，杯身、杯盖、手提绳、包装盒等素材组合" />
      </Field>
      <Field label="画风提示词">
        <textarea rows={3} value={visualStyle} onChange={event => onVisualStyleChange(event.target.value)} placeholder="例：电商主图九宫格素材，干净棚拍质感，白底或浅色底，统一光影和构图" />
      </Field>
      <div className="image-tool-style-lock">
        <div className="image-tool-style-lock-head">
          <strong><LockKeyhole size={15} />风格锁定</strong>
          <button type="button" onClick={applyFriendCirclePreset} disabled={disabled}>
            <Sparkles size={14} />一键锁定朋友圈九图风格
          </button>
        </div>
        {styleAnchorImage?.url && (
          <div className={`image-tool-style-anchor ${styleLock === 'off' ? 'is-off' : ''}`}>
            <img src={assetUrl(styleAnchorImage.url)} alt="当前风格样板" />
            <span>{styleLock === 'off' ? '已保留样板图，但关闭锁定时不会用于生成' : '后续批次会优先贴近这张样板图'}</span>
            <button type="button" onClick={() => onStyleAnchorChange?.(null)} disabled={disabled} title="移除样板图">
              <Trash2 size={13} />移除样板
            </button>
          </div>
        )}
        <div className="image-tool-form-grid">
          <Field label="锁定强度">
            <select value={styleLock} onChange={event => onStyleLockChange(event.target.value)}>
              <option value="strict">严格锁定</option>
              <option value="soft">柔性锁定</option>
              <option value="off">关闭锁定</option>
            </select>
          </Field>
          <Field label="变化策略">
            <select value={variationPolicy} onChange={event => onVariationPolicyChange(event.target.value)}>
              <option value="subject_only">只变主体内容</option>
              <option value="creative">允许轻微创意变化</option>
            </select>
          </Field>
        </div>
        <div className="image-tool-style-lock-options">
          {STYLE_LOCK_OPTIONS.map(item => (
            <label key={item.id}>
              <input
                type="checkbox"
                checked={styleLockOptions.includes(item.id)}
                disabled={styleLock === 'off'}
                onChange={() => toggleStyleLockOption(item.id)}
              />
              <span>{item.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="image-tool-mode-grid image-tool-prompt-source-grid">
        {PROMPT_SOURCE_MODES.map(item => {
          const Icon = item.icon
          return (
            <button key={item.id} type="button" className={mode === item.id ? 'is-active' : ''} onClick={() => setMode(item.id)}>
              <strong><Icon size={15} />{item.label}</strong>
              <span>{item.hint}</span>
            </button>
          )
        })}
      </div>

      {mode === 'reverse' && (
        <div className="image-tool-assist-panel">
          <UploadTile
            label="上传 1 张参考图反推风格"
            disabled={disabled || loading}
            multiple={false}
            onFiles={files => uploadImages(files.slice(0, 1), { limit: 1, current: [], onChange: applyStyleRefs })}
          />
          <ImageGrid
            images={styleRefs}
            onRemove={() => {
              setStyleRefs([])
              setReversePayload(null)
            }}
            emptyText="还没有参考图"
            showActions
            styleAnchorImage={styleAnchorImage}
            onSetAnchor={image => onStyleAnchorChange?.(image)}
          />
          <Field label="反推模型">
            <select value={model} onChange={event => setModel(event.target.value)}>
              {REVERSE_MODELS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <div className="image-tool-action-row">
            <button type="button" className="image-tool-secondary" disabled={disabled || loading || !styleRefs.length} onClick={() => runReverseStyle({ setAnchor: true })}>
              {loading ? <Loader2 className="spin" size={16} /> : <FileImage size={16} />}
              反推并设为样板
            </button>
            <button type="button" className="image-tool-secondary" disabled={disabled || loading || !styleRefs.length} onClick={() => runReverseStyle({ setAnchor: false })}>
              只反推提示词
            </button>
          </div>
          {reversePayload && (
            <div className="image-tool-assist-result">
              <div>
                <strong>反推摘要：{reversePayload.style_summary || reversePayload.visual_style || '-'}</strong>
                <button type="button" onClick={() => navigator.clipboard.writeText(reversePayload.prompt || reversePayload.visual_style || '')}>
                  <Copy size={14} />复制完整提示词
                </button>
              </div>
              <p><strong>画面内容：</strong>{reversePayload.theme || '-'}</p>
              <p><strong>负面词：</strong>{reversePayload.negative_prompt || '-'}</p>
              <p><strong>状态：</strong>已应用到上方“画面内容”和“画风提示词”。</p>
              <div className="image-tool-action-row">
                <button
                  type="button"
                  className={`image-tool-secondary ${reversePromptMode === 'full' ? 'is-active' : ''}`}
                  onClick={() => {
                    setReversePromptMode('full')
                    applyReversePayload(reversePayload, 'full')
                  }}
                >
                  使用完整提示词
                </button>
                <button
                  type="button"
                  className={`image-tool-secondary ${reversePromptMode === 'summary' ? 'is-active' : ''}`}
                  onClick={() => {
                    setReversePromptMode('summary')
                    applyReversePayload(reversePayload, 'summary')
                  }}
                >
                  只使用画风摘要
                </button>
              </div>
              <details>
                <summary>完整提示词</summary>
                <textarea readOnly rows={5} value={reversePayload.prompt || ''} />
              </details>
            </div>
          )}
        </div>
      )}

      {mode === 'polish' && (
        <div className="image-tool-assist-panel">
          <Field label="润色模型">
            <select value={model} onChange={event => setModel(event.target.value)}>
              {REVERSE_MODELS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <button type="button" className="image-tool-secondary" disabled={disabled || loading} onClick={runPolish}>
            {loading ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            AI 润色当前提示词
          </button>
        </div>
      )}

    </div>
  )
}
