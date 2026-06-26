import { api } from '../../services/api'

export function listImageModels() {
  return api.get('/api/game/image_models')
}

export function uploadGameImage(file) {
  return api.upload('/api/game/upload', file)
}

export function watermarkImages(payload) {
  return api.post('/api/image-tools/watermark', payload)
}

export function splitGridImage(payload) {
  return api.post('/api/image-tools/split-grid', payload)
}

export function generateNineImages(payload) {
  return api.post('/api/image-tools/generate-nine', payload)
}

export function generateRoleImages(payload) {
  return api.post('/api/image-tools/generate-roles', payload)
}

export function reverseStylePrompt(payload) {
  return api.post('/api/image-tools/reverse-style', payload)
}

export function polishImagePrompt(payload) {
  return api.post('/api/image-tools/prompt-polish', payload)
}

export function suggestRoleItems(payload) {
  return api.post('/api/image-tools/role-suggestions', payload)
}

export function listWatermarkFonts(previewText = '户外保温杯商品图') {
  return api.get(`/api/image-tools/fonts?preview_text=${encodeURIComponent(previewText)}`)
}

export function uploadWatermarkFont(file) {
  return api.upload('/api/image-tools/fonts/upload', file)
}

export function deriveImages(payload) {
  return api.post('/api/image-tools/derive', payload)
}

export function reverseImagePrompts(payload) {
  return api.post('/api/image-tools/reverse-prompts', payload)
}

export function createImageToolTask(payload) {
  return api.post('/api/image-tools/tasks', payload)
}

export function listImageToolTasks({ limit = 50, status = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  return api.get(`/api/image-tools/tasks?${params.toString()}`, { timeout: 30_000 })
}

export function getImageToolTask(taskId) {
  return api.get(`/api/image-tools/tasks/${encodeURIComponent(taskId)}`, { timeout: 30_000 })
}

export function cancelImageToolTask(taskId) {
  return api.post(`/api/image-tools/tasks/${encodeURIComponent(taskId)}/cancel`, {}, { timeout: 30_000 })
}

export function deleteImageToolTask(taskId) {
  return api.delete(`/api/image-tools/tasks/${encodeURIComponent(taskId)}`, { timeout: 30_000 })
}
