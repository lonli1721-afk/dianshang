import { useState, useEffect } from 'react'
import { Minus, Square, X, Copy, LogOut, User, Sparkles } from 'lucide-react'

export default function TitleBar({ user, onLogout }) {
  const [maximized, setMaximized] = useState(false)
  const isElectron = !!window.electronAPI

  useEffect(() => {
    if (!isElectron) return
    window.electronAPI.isMaximized().then(setMaximized)
    const unsub = window.electronAPI.onMaximizedChange(setMaximized)
    return unsub
  }, [isElectron])

  const btnStyle = {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    width: 46,
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s, color 0.15s',
  }

  return (
    <div style={{
      height: 'var(--titlebar-height)',
      background: 'var(--bg-secondary)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      WebkitAppRegion: 'drag',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
      paddingRight: isElectron ? 0 : 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingLeft: 18 }}>
        <div style={{
          width: 22, height: 22,
          background: 'var(--accent-gradient)',
          borderRadius: 7,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 8px rgba(139,92,246,0.2)',
        }}>
          <Sparkles size={12} color="#fff" />
        </div>
        <span style={{
          fontSize: 13, fontWeight: 600,
          background: 'linear-gradient(135deg, var(--text-secondary), var(--accent))',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
        }}>玩皮AI</span>
      </div>

      {user && user.username !== 'local' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, WebkitAppRegion: 'no-drag' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 10px', borderRadius: 20,
            background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
          }}>
            <div style={{
              width: 18, height: 18, borderRadius: '50%',
              background: 'var(--accent-gradient)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <User size={10} color="#fff" />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 500 }}>
              {user.display_name || user.username}
            </span>
          </div>
          {onLogout && (
            <button onClick={onLogout} style={{
              background: 'none', border: 'none', color: 'var(--text-muted)',
              display: 'flex', alignItems: 'center', gap: 4, fontSize: 11,
              cursor: 'pointer', padding: '5px 10px', borderRadius: 6,
              transition: 'all 0.2s',
            }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(244,63,94,0.1)'; e.currentTarget.style.color = '#f43f5e' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <LogOut size={12} /> 退出
            </button>
          )}
        </div>
      )}

      {isElectron && (
        <div style={{ display: 'flex', height: '100%', WebkitAppRegion: 'no-drag' }}>
          <button style={btnStyle}
            onMouseEnter={e => e.target.style.background = 'var(--bg-hover)'}
            onMouseLeave={e => e.target.style.background = 'none'}
            onClick={() => window.electronAPI.minimize()}>
            <Minus size={14} />
          </button>
          <button style={btnStyle}
            onMouseEnter={e => e.target.style.background = 'var(--bg-hover)'}
            onMouseLeave={e => e.target.style.background = 'none'}
            onClick={() => window.electronAPI.toggleMaximize()}>
            {maximized ? <Copy size={12} /> : <Square size={12} />}
          </button>
          <button style={{...btnStyle}}
            onMouseEnter={e => { e.target.style.background = '#e81123'; e.target.style.color = '#fff' }}
            onMouseLeave={e => { e.target.style.background = 'none'; e.target.style.color = 'var(--text-muted)' }}
            onClick={() => window.electronAPI.close()}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
