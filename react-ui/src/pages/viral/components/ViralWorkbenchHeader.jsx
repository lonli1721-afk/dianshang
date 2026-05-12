import { Check, Plus, RefreshCw } from 'lucide-react'

function OverviewStat({ label, value, tone = '' }) {
  return (
    <div className={`viral-stat ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export default function ViralWorkbenchHeader({
  mainSummary = '',
  loading = false,
  statusText = '待分析',
  statusWarning = false,
  overviewTitle = '未命名游戏 · 投放平台',
  overviewGoal = '上传爆款素材，提取爆点并生成可编辑改版脚本',
  stats = [],
  recentAnalyses = [],
  activeAnalysisId = '',
  analysisManageMode = false,
  workflowSteps = [],
  onStartNewAnalysis = () => {},
  onRefresh = () => {},
  onToggleAnalysisManageMode = () => {},
  onActivateAnalysis = () => {},
  formatAnalysisDate = () => '',
  getHistoryStatusText = () => '',
}) {
  return (
    <>
      <header className="viral-topbar viral-creative-topbar">
        <div>
          <h1>爆款工作台</h1>
          <p>{mainSummary}</p>
        </div>
        <div className="viral-top-actions">
          <button type="button" className="viral-button ghost" onClick={onStartNewAnalysis}>
            <Plus size={16} />
            新分析
          </button>
          <button type="button" className="viral-button muted" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
            刷新
          </button>
        </div>
      </header>

      <section className="viral-creative-overview viral-overview-row">
        <div className="viral-overview-main">
          <div className="viral-creative-overview-main">
            <span className={`viral-status ${statusWarning ? 'is-warning' : ''}`}>
              {statusText}
            </span>
            <strong>{overviewTitle}</strong>
            <span>{overviewGoal}</span>
          </div>
          <div className="viral-command-stats viral-creative-stats">
            {stats.map(item => (
              <OverviewStat key={item.label} label={item.label} value={item.value} tone={item.tone || ''} />
            ))}
          </div>
        </div>

        <aside className="viral-overview-history">
          <div className="viral-overview-history-head">
            <strong>最近分析</strong>
            <button type="button" className={`viral-button muted compact ${analysisManageMode ? 'is-active' : ''}`} onClick={onToggleAnalysisManageMode}>
              {analysisManageMode ? '收起' : '管理'}
            </button>
          </div>
          <div className="viral-recent-list">
            {recentAnalyses.length === 0 && <span className="viral-empty compact">暂无历史</span>}
            {recentAnalyses.map(item => (
              <button
                type="button"
                key={item.id}
                className={`viral-recent-item ${activeAnalysisId === item.id ? 'is-active' : ''}`}
                onClick={() => onActivateAnalysis(item)}
              >
                <strong>{item.game_type || '未命名分析'}</strong>
                <span>{item.platform || '平台未填'} · {formatAnalysisDate(item.updated_at)} · {getHistoryStatusText(item)}</span>
              </button>
            ))}
          </div>
        </aside>
      </section>

      <section className="viral-workflow-strip" aria-label="爆款工作流进度">
        {workflowSteps.map((step, index) => (
          <div
            key={step.id}
            className={`viral-workflow-step ${step.done ? 'is-done' : ''} ${step.active ? 'is-active' : ''} ${step.warning ? 'is-warning' : ''}`}
          >
            <span>{step.done ? <Check size={13} /> : index + 1}</span>
            <div>
              <strong>{step.title}</strong>
              <em>{step.detail}</em>
            </div>
          </div>
        ))}
      </section>
    </>
  )
}
