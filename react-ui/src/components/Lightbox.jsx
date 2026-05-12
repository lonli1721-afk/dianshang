import { useState, useEffect } from 'react'
import { X, ZoomIn, ZoomOut, Download } from 'lucide-react'

export default function Lightbox({ src, type = 'image', alt = '', onClose }) {
  const [scale, setScale] = useState(1)

  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  if (!src) return null

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'zoom-out',
      }}
    >
      {/* Controls */}
      <div
        onClick={e => e.stopPropagation()}
        style={{
          position: 'absolute', top: 16, right: 16,
          display: 'flex', gap: 8, zIndex: 201,
        }}
      >
        <button
          onClick={() => setScale(s => Math.min(s + 0.3, 4))}
          style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'rgba(255,255,255,0.15)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            backdropFilter: 'blur(8px)',
          }}
        ><ZoomIn size={18} /></button>
        <button
          onClick={() => setScale(s => Math.max(s - 0.3, 0.3))}
          style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'rgba(255,255,255,0.15)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            backdropFilter: 'blur(8px)',
          }}
        ><ZoomOut size={18} /></button>
        <a
          href={src} target="_blank" rel="noreferrer" download
          onClick={e => e.stopPropagation()}
          style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'rgba(255,255,255,0.15)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            backdropFilter: 'blur(8px)', textDecoration: 'none',
          }}
        ><Download size={18} /></a>
        <button
          onClick={onClose}
          style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'rgba(255,255,255,0.2)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            backdropFilter: 'blur(8px)',
          }}
        ><X size={18} /></button>
      </div>

      {/* Content */}
      <div onClick={e => e.stopPropagation()} style={{ cursor: 'default' }}>
        {type === 'video' ? (
          <video
            src={src}
            controls
            autoPlay
            preload="none"
            style={{
              maxWidth: '90vw', maxHeight: '85vh',
              borderRadius: 12,
              transform: `scale(${scale})`,
              transition: 'transform 0.2s',
              boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            }}
          />
        ) : (
          <img
            src={src}
            alt={alt}
            loading="lazy"
            decoding="async"
            style={{
              maxWidth: '90vw', maxHeight: '85vh',
              borderRadius: 12, objectFit: 'contain',
              transform: `scale(${scale})`,
              transition: 'transform 0.2s',
              boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            }}
          />
        )}
      </div>
    </div>
  )
}
