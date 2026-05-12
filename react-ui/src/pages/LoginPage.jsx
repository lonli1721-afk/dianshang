import { memo, useMemo, useState } from 'react'
import { Sparkles, User, LogIn, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react'

const pageStyle = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  position: 'relative',
  overflow: 'hidden',
}

const orbStyle = {
  position: 'absolute',
  borderRadius: '50%',
  willChange: 'transform',
  pointerEvents: 'none',
}

const cardWrapStyle = {
  width: 420,
  position: 'relative',
  zIndex: 1,
  animation: 'fadeIn 0.6s ease-out',
}

const glassLayerStyle = {
  position: 'absolute',
  inset: 0,
  borderRadius: 24,
  background: 'var(--bg-glass)',
  backdropFilter: 'blur(40px) saturate(1.5)',
  WebkitBackdropFilter: 'blur(40px) saturate(1.5)',
  border: '1px solid var(--border-accent)',
  boxShadow: 'var(--shadow-lg), var(--glow)',
  pointerEvents: 'none',
  transform: 'translateZ(0)',
}

const contentStyle = {
  position: 'relative',
  padding: '44px 40px',
  borderRadius: 24,
  contain: 'layout paint',
}

const inputBaseStyle = {
  width: '100%',
  borderRadius: 12,
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontSize: 14,
  outline: 'none',
  transition: 'border-color 0.2s, box-shadow 0.2s',
}

const BackgroundOrbs = memo(function BackgroundOrbs() {
  return (
    <>
      <div style={{
        ...orbStyle,
        width: 500,
        height: 500,
        background: 'radial-gradient(circle, rgba(139,92,246,0.15) 0%, transparent 70%)',
        top: '-10%',
        left: '-10%',
        filter: 'blur(60px)',
        animation: 'gradientShift 8s ease-in-out infinite',
      }} />
      <div style={{
        ...orbStyle,
        width: 400,
        height: 400,
        background: 'radial-gradient(circle, rgba(6,182,212,0.12) 0%, transparent 70%)',
        bottom: '-5%',
        right: '-5%',
        filter: 'blur(50px)',
        animation: 'gradientShift 10s ease-in-out infinite reverse',
      }} />
      <div style={{
        ...orbStyle,
        width: 300,
        height: 300,
        background: 'radial-gradient(circle, rgba(99,102,241,0.1) 0%, transparent 70%)',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        filter: 'blur(40px)',
      }} />
    </>
  )
})

function LoginForm({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPwd, setShowPwd] = useState(false)
  const focusRing = useMemo(() => '0 0 0 3px rgba(139,92,246,0.15), var(--glow)', [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) { setError('请输入用户名和密码'); return }
    setLoading(true)
    setError('')
    try {
      const base = import.meta.env.VITE_API_URL || ''
      const res = await fetch(`${base}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || '登录失败')
      }
      const data = await res.json()
      localStorage.setItem('token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      onLogin(data.user, data.token)
    } catch (err) {
      setError(err.message || '登录失败，请检查网络连接')
    }
    setLoading(false)
  }

  return (
    <div style={cardWrapStyle}>
      <div style={glassLayerStyle} />
      <div style={contentStyle}>
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{
            width: 60, height: 60, borderRadius: 18, margin: '0 auto 18px',
            background: 'linear-gradient(135deg, #8b5cf6, #6366f1, #06b6d4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 8px 32px rgba(139,92,246,0.35)',
          }}>
            <Sparkles size={28} color="#fff" />
          </div>
          <h1 style={{
            fontSize: 26, fontWeight: 700, margin: 0,
            background: 'linear-gradient(135deg, var(--text-primary), var(--accent))',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>玩皮AI</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8, letterSpacing: 0.5 }}>AI 视频创作平台</p>
        </div>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{
              padding: '10px 14px', borderRadius: 10, marginBottom: 18,
              background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.25)',
              color: '#fb7185', fontSize: 12, display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <AlertCircle size={14} /> {error}
            </div>
          )}

          <div style={{ marginBottom: 18 }}>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8, display: 'block', fontWeight: 500 }}>用户名</label>
            <div style={{ position: 'relative' }}>
              <User size={16} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text" value={username} onChange={e => setUsername(e.target.value)}
                placeholder="请输入用户名"
                autoFocus
                autoComplete="username"
                spellCheck={false}
                style={{
                  ...inputBaseStyle,
                  padding: '12px 14px 12px 42px',
                }}
                onFocus={e => { e.target.style.borderColor = 'var(--accent)'; e.target.style.boxShadow = focusRing }}
                onBlur={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none' }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 28 }}>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8, display: 'block', fontWeight: 500 }}>密码</label>
            <div style={{ position: 'relative' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)' }}>
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              <input
                type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
                placeholder="请输入密码"
                autoComplete="current-password"
                style={{
                  ...inputBaseStyle,
                  padding: '12px 42px 12px 42px',
                }}
                onFocus={e => { e.target.style.borderColor = 'var(--accent)'; e.target.style.boxShadow = focusRing }}
                onBlur={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none' }}
              />
              <button type="button" onClick={() => setShowPwd(!showPwd)} style={{
                position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 2,
              }}>
                {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button type="submit" disabled={loading} style={{
            width: '100%', padding: '13px 0', borderRadius: 12,
            background: loading ? 'var(--bg-tertiary)' : 'var(--accent-gradient-2)',
            color: '#fff', fontSize: 14, fontWeight: 600,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            cursor: loading ? 'not-allowed' : 'pointer',
            border: 'none', transition: 'all 0.3s',
            boxShadow: loading ? 'none' : '0 4px 20px rgba(139,92,246,0.3)',
            letterSpacing: 1,
          }}>
            {loading ? <Loader2 size={18} className="spin" /> : <LogIn size={18} />}
            {loading ? '登录中...' : '登 录'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 24, fontSize: 11, color: 'var(--text-muted)', letterSpacing: 0.3 }}>
          玩皮AI v2.0
        </div>
      </div>
    </div>
  )
}

const MemoLoginForm = memo(LoginForm)

export default function LoginPage({ onLogin }) {
  return (
    <div style={pageStyle}>
      <BackgroundOrbs />
      <MemoLoginForm onLogin={onLogin} />
    </div>
  )
}
