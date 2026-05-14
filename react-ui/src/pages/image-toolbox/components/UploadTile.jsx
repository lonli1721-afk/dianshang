import { useRef } from 'react'
import { Upload } from 'lucide-react'

export function UploadTile({ label, multiple = true, disabled, onFiles, accept = 'image/*' }) {
  const inputRef = useRef(null)

  return (
    <button type="button" className="image-tool-upload" disabled={disabled} onClick={() => inputRef.current?.click()}>
      <Upload size={18} />
      <span>{label}</span>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={event => {
          const files = Array.from(event.target.files || [])
          event.target.value = ''
          if (files.length) onFiles(files)
        }}
      />
    </button>
  )
}
