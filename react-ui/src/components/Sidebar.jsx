import { useLocation, useNavigate } from 'react-router-dom'
import {
  Clapperboard,
  Image as ImageIcon,
  PanelLeft,
  PanelLeftClose,
  Settings,
  Store,
  Video,
} from 'lucide-react'

const NAV_ITEMS = [
  { path: '/', label: '视频工作台', icon: Video, matches: ['/', '/video-workbench', '/game-video'] },
  { path: '/batch-video-workbench', label: '批量生成视频工作台', icon: Clapperboard },
  { path: '/image-toolbox', label: '图片工作台', icon: ImageIcon },
  { path: '/settings', label: '系统设置', icon: Settings },
]

export default function Sidebar({ collapsed, onToggle, onPrefetchSettings, user }) {
  const location = useLocation()
  const navigate = useNavigate()
  void user

  return (
    <aside style={{
      width: collapsed ? 64 : 'var(--sidebar-width)',
      background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      transition: 'width 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
      flexShrink: 0,
      overflow: 'hidden',
      position: 'relative',
    }}>
      <div style={{
        padding: collapsed ? '16px 12px' : '16px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
        borderBottom: '1px solid var(--border)',
        minHeight: 56,
      }}>
        {!collapsed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 28,
              height: 28,
              borderRadius: 9,
              background: 'var(--accent-gradient)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 2px 10px rgba(139,92,246,0.25)',
            }}>
              <Store size={14} color="#fff" />
            </div>
            <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: 0 }}>电商素材平台</span>
          </div>
        )}
        <button
          type="button"
          onClick={onToggle}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: 6,
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      <nav style={{ flex: 1, padding: '10px 8px', overflowY: 'auto' }}>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const isActive = item.matches ? item.matches.includes(location.pathname) : location.pathname === item.path
          return (
            <button
              key={item.path}
              type="button"
              onMouseEnter={item.path === '/settings' ? onPrefetchSettings : undefined}
              onFocus={item.path === '/settings' ? onPrefetchSettings : undefined}
              onClick={() => navigate(item.path)}
              title={collapsed ? item.label : undefined}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: collapsed ? '10px 0' : '10px 14px',
                justifyContent: collapsed ? 'center' : 'flex-start',
                marginBottom: 2,
                borderRadius: 10,
                background: isActive ? 'var(--nav-active-bg)' : 'transparent',
                color: isActive ? 'var(--nav-active-text)' : 'var(--text-secondary)',
                fontSize: 13,
                fontWeight: isActive ? 600 : 500,
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              <Icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
