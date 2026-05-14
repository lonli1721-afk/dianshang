import { X } from 'lucide-react'

export function ToastStack({ toasts = [], onDismiss }) {
  if (!toasts.length) return null

  return (
    <div className="image-tool-toast-stack" aria-live="polite">
      {toasts.map(toast => (
        <article key={toast.id} className={`image-tool-toast is-${toast.tone || 'info'}`}>
          <span>{toast.message}</span>
          <button type="button" onClick={() => onDismiss(toast.id)} title="关闭提示">
            <X size={14} />
          </button>
        </article>
      ))}
    </div>
  )
}
