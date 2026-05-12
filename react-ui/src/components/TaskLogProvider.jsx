import { useState, useCallback } from 'react'
import { TaskContext } from './taskLogState'

export function TaskProvider({ children }) {
  const [tasks, setTasks] = useState([])

  const addTask = useCallback((id, label, meta = null) => {
    const now = Date.now()
    setTasks(prev => [
      { id, label, status: 'running', startTime: now, elapsed: 0, message: '生成中...', meta },
      ...prev,
    ])
  }, [])

  const completeTask = useCallback((id, message = '已完成') => {
    setTasks(prev => prev.map(t =>
      t.id === id ? { ...t, status: 'done', message, elapsed: Date.now() - t.startTime } : t
    ))
  }, [])

  const failTask = useCallback((id, message = '生成失败') => {
    setTasks(prev => prev.map(t =>
      t.id === id ? { ...t, status: 'error', message, elapsed: Date.now() - t.startTime } : t
    ))
  }, [])

  const clearTasks = useCallback(() => {
    setTasks([])
  }, [])

  return (
    <TaskContext.Provider value={{ tasks, addTask, completeTask, failTask, clearTasks }}>
      {children}
    </TaskContext.Provider>
  )
}
