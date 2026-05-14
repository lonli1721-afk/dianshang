import { MAX_IMAGE_BYTES } from './constants'
import { displayError } from './helpers'
import { uploadGameImage } from './imageToolboxApi'

export function useImageUploadQueue(setNotice) {
  const uploadImages = async (files, { limit, current, onChange, setNotice: scopedNotice }) => {
    const notify = scopedNotice || setNotice
    notify?.('')
    const accepted = files
      .filter(file => file.type.startsWith('image/') && file.size <= MAX_IMAGE_BYTES)
      .slice(0, Math.max(0, limit - current.length))

    if (!accepted.length) {
      notify?.(`最多上传 ${limit} 张图片，且单张不能超过 12 MiB。`)
      return
    }

    try {
      const uploaded = []
      for (const file of accepted) {
        const result = await uploadGameImage(file)
        uploaded.push({ url: result.url, name: file.name.replace(/\.[^.]+$/, '') })
      }
      onChange([...current, ...uploaded])
    } catch (error) {
      notify?.(displayError(error))
    }
  }

  return { uploadImages }
}
