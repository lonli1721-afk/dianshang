import { createContext, useContext } from 'react'

export const TaskContext = createContext(null)

export function useTaskLog() {
  const ctx = useContext(TaskContext)
  if (!ctx) throw new Error('useTaskLog must be used within <TaskProvider>')
  return ctx
}
