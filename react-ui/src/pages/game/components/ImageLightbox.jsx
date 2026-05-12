import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

export default function ImageLightbox({ imageUrl, onClose }) {
  if (!imageUrl || typeof document === 'undefined') return null

  return createPortal(
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 2147483646,
        background: 'rgba(0,0,0,0.88)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24, cursor: 'zoom-out',
      }}
    >
      <button
        type="button"
        aria-label="关闭"
        onClick={(e) => { e.stopPropagation(); onClose() }}
        style={{
          position: 'absolute', top: 16, right: 16, zIndex: 2,
          background: 'rgba(255,255,255,0.12)', color: '#fff', border: 'none',
          borderRadius: 8, padding: 8, cursor: 'pointer', lineHeight: 0,
        }}
      >
        <X size={22} />
      </button>
      <img
        src={imageUrl}
        alt=""
        loading="lazy"
        decoding="async"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 6, cursor: 'default', boxShadow: '0 8px 40px rgba(0,0,0,0.5)' }}
      />
    </div>,
    document.body,
  )
}
