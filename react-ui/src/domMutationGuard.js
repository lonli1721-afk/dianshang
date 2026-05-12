export function installDomMutationGuard() {
  if (typeof window === 'undefined' || typeof Node === 'undefined') return
  if (window.__gameVideoDomMutationGuardInstalled) return
  window.__gameVideoDomMutationGuardInstalled = true

  const originalRemoveChild = Node.prototype.removeChild
  const originalInsertBefore = Node.prototype.insertBefore

  try {
    Node.prototype.removeChild = function guardedRemoveChild(child) {
      if (child && child.parentNode !== this) {
        return child
      }
      return originalRemoveChild.call(this, child)
    }

    Node.prototype.insertBefore = function guardedInsertBefore(newNode, referenceNode) {
      if (referenceNode && referenceNode.parentNode !== this) {
        return this.appendChild(newNode)
      }
      return originalInsertBefore.call(this, newNode, referenceNode)
    }
  } catch {
    window.__gameVideoDomMutationGuardInstalled = false
  }
}
