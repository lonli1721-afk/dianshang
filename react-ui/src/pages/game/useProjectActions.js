import { useCallback } from 'react'
import { api } from '../../services/api'
import {
  getErrorMessage,
  logGamePageError,
} from './gameVideoPageHelpers'

export function useProjectActions({
  currentProject,
  projectsRef,
  newProjectName,
  renamingProjectId,
  renamingProjectName,
  setProjects,
  setCurrentProject,
  setNewProjectName,
  setShowNewProject,
  setRenamingProjectId,
  setRenamingProjectName,
  openProject,
}) {
  const loadProjects = useCallback(async () => {
    try {
      const data = await api.get('/api/game/projects')
      setProjects(Array.isArray(data) ? data : [])
    } catch (e) {
      logGamePageError('loadProjects', e)
      if (!projectsRef.current.length) setProjects([])
    }
  }, [projectsRef, setProjects])

  const startNewProject = useCallback(() => {
    setShowNewProject(true)
  }, [setShowNewProject])

  const cancelNewProject = useCallback(() => {
    setShowNewProject(false)
    setNewProjectName('')
  }, [setNewProjectName, setShowNewProject])

  const createProject = useCallback(async () => {
    const name = newProjectName.trim()
    if (!name) return
    try {
      const project = await api.post('/api/game/projects', { name })
      setProjects(prev => [project, ...prev])
      openProject(project)
      setNewProjectName('')
      setShowNewProject(false)
    } catch (e) {
      alert('创建失败: ' + getErrorMessage(e, '创建失败'))
    }
  }, [newProjectName, openProject, setNewProjectName, setProjects, setShowNewProject])

  const deleteProject = useCallback(async (projectId) => {
    if (!confirm('确定删除此项目？')) return
    try {
      await api.delete(`/api/game/projects/${projectId}`)
      setProjects(prev => prev.filter(project => project.id !== projectId))
      if (currentProject?.id === projectId) setCurrentProject(null)
    } catch (e) {
      alert('删除失败: ' + getErrorMessage(e, '删除失败'))
    }
  }, [currentProject?.id, setCurrentProject, setProjects])

  const startProjectRename = useCallback((project) => {
    setRenamingProjectId(project.id)
    setRenamingProjectName(project.name || '')
  }, [setRenamingProjectId, setRenamingProjectName])

  const cancelProjectRename = useCallback(() => {
    setRenamingProjectId(null)
    setRenamingProjectName('')
  }, [setRenamingProjectId, setRenamingProjectName])

  const saveProjectRename = useCallback(async () => {
    const name = renamingProjectName.trim()
    if (!renamingProjectId || !name) {
      cancelProjectRename()
      return
    }
    try {
      await api.put(`/api/game/projects/${renamingProjectId}`, { name })
      setProjects(prev => prev.map(project => (
        project.id === renamingProjectId ? { ...project, name } : project
      )))
      if (currentProject?.id === renamingProjectId) {
        setCurrentProject(prev => (prev ? { ...prev, name } : null))
      }
    } catch (e) {
      alert('重命名失败: ' + getErrorMessage(e, '重命名失败'))
    }
    cancelProjectRename()
  }, [
    cancelProjectRename,
    currentProject?.id,
    renamingProjectId,
    renamingProjectName,
    setCurrentProject,
    setProjects,
  ])

  return {
    loadProjects,
    startNewProject,
    cancelNewProject,
    createProject,
    deleteProject,
    startProjectRename,
    cancelProjectRename,
    saveProjectRename,
  }
}
