import { Target } from 'lucide-react'

function BriefField({ label, children }) {
  return (
    <label className="viral-field">
      <span>{label}</span>
      {children}
    </label>
  )
}

export default function AnalysisBriefStrip({
  expanded,
  form = {},
  models = [],
  activeModel,
  platformOptions = [],
  onToggleExpanded = () => {},
  onFormChange = () => {},
}) {
  return (
    <div className={`viral-condition-strip is-embedded ${expanded ? 'is-open' : ''}`}>
      <div className="viral-condition-summary">
        <Target size={16} />
        <strong>{form.game_type || '未命名游戏'}</strong>
        <span>{form.target_user || '目标用户未填'}</span>
        <span>{form.platform || '平台未填'}</span>
        <span>{activeModel?.name}</span>
        <em>{form.optimization_goal || '优化目标未填'}</em>
      </div>
      <button type="button" className="viral-button muted compact" onClick={onToggleExpanded}>
        {expanded ? '收起投放条件' : '展开投放条件'}
      </button>
      {expanded && (
        <div className="viral-creative-brief">
          <div className="viral-condition-help">
            <strong>这块是分析 Brief</strong>
            <span>用于告诉 AI：这批爆款素材属于什么游戏、面向谁、投到哪里、这次想优化什么。填写得越具体，后面的爆点判断和改版脚本越贴近实际投放。</span>
          </div>
          <div className="viral-field-grid">
            <BriefField label="游戏类型">
              <input value={form.game_type || ''} onChange={event => onFormChange('game_type', event.target.value)} placeholder="例：找不同、SLG、放置卡牌" />
            </BriefField>
            <BriefField label="目标用户">
              <input value={form.target_user || ''} onChange={event => onFormChange('target_user', event.target.value)} placeholder="例：18-35 岁休闲玩家" />
            </BriefField>
            <BriefField label="投放平台">
              <select value={form.platform || ''} onChange={event => onFormChange('platform', event.target.value)}>
                {platformOptions.map(item => <option key={item} value={item}>{item}</option>)}
              </select>
            </BriefField>
            <BriefField label="分析模型">
              <select value={form.model || ''} onChange={event => onFormChange('model', event.target.value)}>
                {models.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </BriefField>
            <BriefField label="优化目标">
              <textarea value={form.optimization_goal || ''} onChange={event => onFormChange('optimization_goal', event.target.value)} placeholder="例：提升前三秒停留和点击率" rows={3} />
            </BriefField>
          </div>
        </div>
      )}
    </div>
  )
}
