import { RefreshCw, Scan, Video } from 'lucide-react'

const WORKBENCH_TABS = [
  { id: 'generate', label: '生成视频', icon: Video },
  { id: 'replace', label: '视频替换', icon: RefreshCw },
  { id: 'reverse', label: '视频反推', icon: Scan },
]

export default function WorkbenchTabs({ activeTab, onChange }) {
  return (
    <div style={{ display: 'flex', flex: 1 }}>
      {WORKBENCH_TABS.map(tab => (
        <button key={tab.id} onClick={() => onChange(tab.id)} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '11px 18px', fontSize: 13, fontWeight: activeTab === tab.id ? 600 : 400, color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-secondary)', borderBottom: activeTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent', background: 'none' }}>
          <tab.icon size={15} />{tab.label}
        </button>
      ))}
    </div>
  )
}
