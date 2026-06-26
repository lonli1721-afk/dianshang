import { Component, Suspense, lazy, useState, useEffect, useLayoutEffect } from 'react'
import { HashRouter, Routes, Route } from 'react-router-dom'
import { TaskProvider } from './components/TaskLog'
import TitleBar from './components/TitleBar'
import Sidebar from './components/Sidebar'
import GameVideoPage from './pages/game/GameVideoPage'
import LoginPage from './pages/LoginPage'
import { trackOperationEvent } from './services/api'

const THEME_MODES = new Set(['system', 'light', 'dark'])
const loadSettingsPage = () => import('./pages/SettingsPage')
const loadImageToolboxPage = () => import('./pages/ImageToolboxPage')
const loadBatchVideoWorkbenchPage = () => import('./pages/BatchVideoWorkbenchPage')
const SettingsPage = lazy(loadSettingsPage)
const ImageToolboxPage = lazy(loadImageToolboxPage)
const BatchVideoWorkbenchPage = lazy(loadBatchVideoWorkbenchPage)

function preloadSettingsPage() {
  void loadSettingsPage().catch(() => {})
}

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      message: error?.message || String(error || '未知前端错误'),
    }
  }

  componentDidCatch(error, info) {
    console.error('App render error', error, info)
    try {
      const token = window.localStorage.getItem('token')
      let storedUser = {}
      try {
        storedUser = JSON.parse(window.localStorage.getItem('user') || '{}') || {}
      } catch {
        storedUser = {}
      }
      fetch('/api/client-errors', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: error?.message || String(error || ''),
          stack: error?.stack || '',
          component_stack: info?.componentStack || '',
          url: window.location.href,
          user_agent: window.navigator?.userAgent || '',
          username: storedUser.username || '',
          user_id: storedUser.id || '',
        }),
      }).catch(() => {})
    } catch (e) {
      void e
    }
  }

  resetSession = () => {
    try {
      window.localStorage.removeItem('token')
      window.localStorage.removeItem('user')
      window.sessionStorage.clear()
    } catch (e) {
      void e
    }
    window.location.href = `${window.location.origin}${window.location.pathname}`
  }

  render() {
    if (this.state.hasError) {
      const message = (this.state.message || '').slice(0, 180)
      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-primary)',
          color: 'var(--text-primary)',
          padding: 24,
        }}>
          <div style={{
            maxWidth: 420,
            border: '1px solid var(--border)',
            borderRadius: 8,
            background: 'var(--bg-secondary)',
            padding: 20,
            boxShadow: 'var(--shadow)',
          }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>页面遇到异常</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 16 }}>
              已拦截本次渲染错误，请刷新页面后继续使用。若仍然出现，请联系管理员查看前端日志。
            </div>
            {message && (
              <div style={{
                fontSize: 12,
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
                marginBottom: 12,
                padding: 10,
                borderRadius: 6,
                background: 'var(--bg-tertiary)',
                wordBreak: 'break-word',
              }}>
                错误详情：{message}
              </div>
            )}
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                width: '100%',
                borderRadius: 8,
                padding: '10px 12px',
                background: 'var(--accent-gradient)',
                color: '#fff',
                fontWeight: 700,
              }}
            >
              刷新页面
            </button>
            <button
              type="button"
              onClick={this.resetSession}
              style={{
                width: '100%',
                borderRadius: 8,
                padding: '10px 12px',
                marginTop: 8,
                background: 'var(--bg-tertiary)',
                color: 'var(--text-primary)',
                fontWeight: 700,
                border: '1px solid var(--border)',
              }}
            >
              重新登录
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getStoredThemeMode() {
  const savedTheme = localStorage.getItem('wanpi_theme')
  return THEME_MODES.has(savedTheme) ? savedTheme : 'system'
}

function applyThemeMode(mode) {
  document.documentElement.setAttribute('data-theme', mode === 'system' ? getSystemTheme() : mode)
}

function RouteLoadingFallback() {
  return (
    <div style={{
      minHeight: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-primary)',
      color: 'var(--text-muted)',
    }}>
      <div style={{
        width: 32,
        height: 32,
        borderRadius: 10,
        background: 'var(--accent-gradient)',
        boxShadow: 'var(--shadow)',
        animation: 'pulse 2s ease-in-out infinite',
      }} />
    </div>
  )
}

function shouldCollapseSidebar() {
  return typeof window !== 'undefined' && window.innerWidth < 760
}

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => shouldCollapseSidebar())
  const [authEnabled, setAuthEnabled] = useState(null)
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)

  const checkAuth = async () => {
    try {
      const base = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '')
      const res = await fetch(`${base}/api/auth/status`)
      const data = await res.json()
      setAuthEnabled(data.auth_enabled)
      if (!data.auth_enabled) {
        const localUser = { id: 'local', username: 'local', role: 'admin' }
        setUser(localUser)
        localStorage.setItem('user', JSON.stringify(localUser))
        setChecking(false)
        return
      }
      const token = localStorage.getItem('token')
      if (token) {
        const meRes = await fetch(`${base}/api/auth/me`, {
          headers: { 'Authorization': `Bearer ${token}` },
        })
        if (meRes.ok) {
          const meData = await meRes.json()
          setUser(meData.user)
          localStorage.setItem('user', JSON.stringify(meData.user))
        } else {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
        }
      }
    } catch {
      if (import.meta.env.DEV) {
        const localUser = { id: 'local', username: 'local', role: 'admin' }
        setAuthEnabled(false)
        setUser(localUser)
        localStorage.setItem('user', JSON.stringify(localUser))
      } else {
        setAuthEnabled(true)
      }
    }
    setChecking(false)
  }

  useLayoutEffect(() => {
    const savedTheme = getStoredThemeMode()
    const savedColor = localStorage.getItem('wanpi_color') || ''
    applyThemeMode(savedTheme)
    if (savedColor) document.documentElement.setAttribute('data-color', savedColor)

    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (getStoredThemeMode() === 'system') {
        applyThemeMode('system')
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      void checkAuth()
    }, 0)
    const handler = () => { setUser(null) }
    window.addEventListener('auth-expired', handler)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('auth-expired', handler)
    }
  }, [])

  useEffect(() => {
    if (checking || (authEnabled && !user)) return undefined
    const timer = window.setTimeout(preloadSettingsPage, 600)
    return () => window.clearTimeout(timer)
  }, [authEnabled, checking, user])

  useEffect(() => {
    const handleResize = () => {
      if (shouldCollapseSidebar()) setSidebarCollapsed(true)
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    const handleDownloadClick = (event) => {
      const link = event.target?.closest?.('a[download]')
      if (!link) return
      const hash = window.location.hash || ''
      let area = 'download'
      if (hash.includes('image-toolbox')) area = 'download_image_toolbox'
      else if (hash.includes('batch-video-workbench')) area = 'download_batch_video_workbench'
      else if (hash.includes('video-workbench') || hash.includes('game-video') || hash === '' || hash === '#/' || hash === '#') area = 'download_video_workbench'
      trackOperationEvent({ operation: area })
    }
    document.addEventListener('click', handleDownloadClick, true)
    return () => document.removeEventListener('click', handleDownloadClick, true)
  }, [])

  const handleLogin = (userData) => { setUser(userData) }
  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }
  if (checking) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-primary)', color: 'var(--text-muted)', fontSize: 13, gap: 16,
      }}>
        <div style={{
          width: 44, height: 44, borderRadius: 14,
          background: 'var(--accent-gradient)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(139,92,246,0.3)',
          animation: 'pulse 2s ease-in-out infinite',
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3L20 7.5V16.5L12 21L4 16.5V7.5L12 3Z"/></svg>
        </div>
        <span style={{ letterSpacing: 0.5 }}>正在连接服务器...</span>
      </div>
    )
  }

  if (authEnabled && !user) {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <AppErrorBoundary>
      <TaskProvider>
        <HashRouter>
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
            <TitleBar user={user} onLogout={authEnabled ? handleLogout : null} />
            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
              <Sidebar
                collapsed={sidebarCollapsed}
                onToggle={() => setSidebarCollapsed(p => !p)}
                onPrefetchSettings={preloadSettingsPage}
                user={user}
              />
              <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg-primary)' }}>
                <Routes>
                  <Route path="/" element={<GameVideoPage />} />
                  <Route path="/video-workbench" element={<GameVideoPage />} />
                  <Route path="/game-video" element={<GameVideoPage />} />
                  <Route
                    path="/image-toolbox"
                    element={(
                      <Suspense fallback={<RouteLoadingFallback />}>
                        <ImageToolboxPage />
                      </Suspense>
                    )}
                  />
                  <Route
                    path="/batch-video-workbench"
                    element={(
                      <Suspense fallback={<RouteLoadingFallback />}>
                        <BatchVideoWorkbenchPage />
                      </Suspense>
                    )}
                  />
                  <Route
                    path="/settings"
                    element={(
                      <Suspense fallback={<RouteLoadingFallback />}>
                        <SettingsPage />
                      </Suspense>
                    )}
                  />
                </Routes>
              </main>
            </div>
          </div>
        </HashRouter>
      </TaskProvider>
    </AppErrorBoundary>
  )
}
