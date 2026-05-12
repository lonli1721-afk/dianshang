import { useCallback, useRef } from 'react'

export function useTextInsertionActions() {
  const pendingSelectionRestoreRef = useRef(null)

  const restorePendingSelection = useCallback(() => {
    const pending = pendingSelectionRestoreRef.current
    if (!pending) return
    const el = document.getElementById(pending.elementId)
    if (!el) return
    el.focus()
    el.setSelectionRange(pending.caret, pending.caret)
    pendingSelectionRestoreRef.current = null
  }, [])

  const insertTextAtCursor = useCallback((elementId, text, applyValue) => {
    const el = document.getElementById(elementId)
    if (!el) return
    const start = el.selectionStart ?? el.value.length
    const end = el.selectionEnd ?? start
    const before = el.value.slice(0, start)
    const after = el.value.slice(end)
    const newValue = before + text + after
    const newCaret = start + text.length
    pendingSelectionRestoreRef.current = { elementId, caret: newCaret }
    applyValue(newValue)
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          restorePendingSelection()
        })
      })
    }
  }, [restorePendingSelection])

  return { insertTextAtCursor }
}
