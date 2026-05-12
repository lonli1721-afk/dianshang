const getBaseUrl = () => {
  if (import.meta.env.DEV) {
    return ''
  }
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }
  return ''
}

function getAuthHeaders() {
  const token = localStorage.getItem('token')
  if (token) {
    return { 'Authorization': `Bearer ${token}` }
  }
  return {}
}

function handleAuthError(res) {
  if (res.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.dispatchEvent(new Event('auth-expired'))
  }
}

function withTimeout(timeoutMs) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  return { signal: ctrl.signal, clear: () => clearTimeout(timer) }
}

const DEFAULT_TIMEOUT = 600_000

export const api = {
  async get(path, { timeout = DEFAULT_TIMEOUT } = {}) {
    const t = withTimeout(timeout)
    try {
      const res = await fetch(`${getBaseUrl()}${path}`, {
        headers: { ...getAuthHeaders() },
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      return res.json()
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('请求超时，请重试')
      throw e
    }
  },

  async post(path, body, { timeout = DEFAULT_TIMEOUT } = {}) {
    const t = withTimeout(timeout)
    try {
      const res = await fetch(`${getBaseUrl()}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      const text = await res.text()
      const data = JSON.parse(text.trim())
      if (data && data._error) throw new Error(data._error)
      return data
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('请求超时，请重试')
      throw e
    }
  },

  async put(path, body, { timeout = DEFAULT_TIMEOUT } = {}) {
    const t = withTimeout(timeout)
    try {
      const res = await fetch(`${getBaseUrl()}${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      return res.json()
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('请求超时，请重试')
      throw e
    }
  },

  async patch(path, body, { timeout = DEFAULT_TIMEOUT } = {}) {
    const t = withTimeout(timeout)
    try {
      const res = await fetch(`${getBaseUrl()}${path}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      return res.json()
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('请求超时，请重试')
      throw e
    }
  },

  async delete(path, { timeout = DEFAULT_TIMEOUT } = {}) {
    const t = withTimeout(timeout)
    try {
      const res = await fetch(`${getBaseUrl()}${path}`, {
        method: 'DELETE',
        headers: { ...getAuthHeaders() },
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      return res.json()
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('请求超时，请重试')
      throw e
    }
  },

  async sse(path, body, onChunk, onDone, onError) {
    const t = withTimeout(DEFAULT_TIMEOUT)
    let res
    try {
      res = await fetch(`${getBaseUrl()}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('请求超时，请重试')
      throw e
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'chunk') onChunk?.(data.content)
            else if (data.type === 'done') onDone?.(data.parsed)
            else if (data.type === 'error') onError?.(data.error)
          } catch (e) {
            onError?.(`Invalid stream data: ${e.message}`)
          }
        }
      }
    }
  },

  async upload(path, fileOrFormData, extra = {}) {
    let formData
    if (fileOrFormData instanceof FormData) {
      formData = fileOrFormData
    } else {
      formData = new FormData()
      formData.append('file', fileOrFormData)
    }
    for (const [k, v] of Object.entries(extra)) {
      formData.append(k, v)
    }
    const t = withTimeout(DEFAULT_TIMEOUT)
    try {
      const res = await fetch(`${getBaseUrl()}${path}`, {
        method: 'POST',
        headers: { ...getAuthHeaders() },
        body: formData,
        signal: t.signal,
      })
      t.clear()
      handleAuthError(res)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `Upload failed: HTTP ${res.status}`)
      }
      return res.json()
    } catch (e) {
      t.clear()
      if (e.name === 'AbortError') throw new Error('上传超时，请重试')
      if (/Load failed|Failed to fetch|NetworkError/i.test(e.message || '')) {
        throw new Error('上传请求没有到达后端，请刷新页面后重试；如果仍失败，检查本地前后端服务是否都在运行。')
      }
      throw e
    }
  },

  getWsUrl(path) {
    const base = getBaseUrl().replace(/^http/, 'ws')
    const token = localStorage.getItem('token')
    const sep = path.includes('?') ? '&' : '?'
    return `${base}${path}${token ? `${sep}token=${token}` : ''}`
  },
}

/**
 * Run async tasks with controlled concurrency.
 * @param {Array} items - items to process
 * @param {Function} fn - async function(item, index) => result
 * @param {number} concurrency - max parallel tasks (default 3)
 * @returns {Promise<Array>} results in order
 */
export async function runConcurrent(items, fn, concurrency = 3) {
  const results = new Array(items.length)
  let cursor = 0

  async function worker() {
    while (cursor < items.length) {
      const idx = cursor++
      try {
        results[idx] = await fn(items[idx], idx)
      } catch (e) {
        results[idx] = { _error: e }
      }
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, items.length) }, () => worker())
  await Promise.all(workers)
  return results
}
