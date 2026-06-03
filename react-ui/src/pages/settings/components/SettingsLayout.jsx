import { Settings } from 'lucide-react'

export default function SettingsLayout({
  navItems,
  activeNav,
  onNavChange,
  hasUpdateDot,
  children,
}) {
  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      <div style={{
        width: 200, flexShrink: 0, padding: '24px 12px',
        borderRight: '1px solid var(--border)', background: 'var(--bg-secondary)',
        overflow: 'auto',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, padding: '0 8px' }}>
          <Settings size={18} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 16, fontWeight: 600 }}>系统设置</span>
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', padding: '0 8px', marginBottom: 16 }}>配置本地系统功能与版本信息</p>
        {navItems.map(item => {
          const active = activeNav === item.id
          return (
            <div key={item.id} onClick={() => onNavChange(item.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer', marginBottom: 2,
              background: active ? 'var(--accent-light)' : 'transparent',
              border: active ? '1px solid var(--border-accent)' : '1px solid transparent',
              transition: 'all 0.15s',
            }}>
              <item.icon size={16} style={{ color: active ? 'var(--accent)' : 'var(--text-muted)' }} />
              <span style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? 'var(--accent)' : 'var(--text-primary)' }}>{item.label}</span>
              {item.id === 'update' && hasUpdateDot && (
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444', marginLeft: 'auto' }} />
              )}
            </div>
          )
        })}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
        <div style={{ maxWidth: activeNav === 'usage' ? 1080 : 660 }}>
          {children}
        </div>
      </div>
    </div>
  )
}
