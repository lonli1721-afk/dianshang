import { useEffect, useState } from 'react'
import { listImageModels } from './imageToolboxApi'

export function useImageToolboxModels() {
  const [imageModels, setImageModels] = useState([])
  const [modelsLoaded, setModelsLoaded] = useState(false)

  useEffect(() => {
    listImageModels().then(data => {
      setImageModels(data.models || [])
    }).catch(() => {}).finally(() => {
      setModelsLoaded(true)
    })
  }, [])

  return { imageModels, modelsLoaded }
}
