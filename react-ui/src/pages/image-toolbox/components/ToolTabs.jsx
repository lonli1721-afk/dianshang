export function ToolTabs({ tabs, activeTab, onChange, disabledNotice }) {
  return (
    <div className="image-tool-tabs">
      {tabs.map(tab => {
        const Icon = tab.icon
        return (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? 'is-active' : ''}
            disabled={!tab.enabled}
            title={tab.enabled ? tab.label : disabledNotice}
            onClick={() => {
              if (tab.enabled) onChange(tab.id)
            }}
          >
            <Icon size={17} />
            {tab.label}
            {(tab.status || !tab.enabled) && (
              <span className="image-tool-tab-status">{tab.status || '实验中'}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
