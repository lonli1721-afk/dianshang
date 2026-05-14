export function PanelNotice({ notice, className = '' }) {
  const message = typeof notice === 'string' ? notice : notice?.message
  const tone = typeof notice === 'string' ? 'info' : notice?.tone || 'info'

  if (!message) return null

  return (
    <div className={`image-tool-panel-notice is-${tone} ${className}`.trim()}>
      {message}
    </div>
  )
}
