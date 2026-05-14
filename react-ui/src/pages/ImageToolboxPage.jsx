import { BadgeCheck } from 'lucide-react'
import { useState } from 'react'
import { DERIVE_MODELS_BY_PROVIDER, IMAGE_TOOL_TABS, PAID_FEATURE_NOTICE } from './image-toolbox/constants'
import { DerivePanel } from './image-toolbox/components/DerivePanel'
import { PanelNotice } from './image-toolbox/components/PanelNotice'
import { ReversePromptPanel } from './image-toolbox/components/ReversePromptPanel'
import { ToastStack } from './image-toolbox/components/ToastStack'
import { ToolTabs } from './image-toolbox/components/ToolTabs'
import { WatermarkPanel } from './image-toolbox/components/WatermarkPanel'
import { useImageToolNotifications } from './image-toolbox/useImageToolNotifications'
import { useImageToolboxModels } from './image-toolbox/useImageToolboxModels'
import { useImageToolTasks } from './image-toolbox/useImageToolTasks'
import { useImageUploadQueue } from './image-toolbox/useImageUploadQueue'

const tabForTask = (type) => (type === 'derive' ? 'derive' : type === 'reverse_prompts' ? 'reverse' : 'watermark')

export default function ImageToolboxPage() {
  const [activeTab, setActiveTab] = useState('watermark')
  const [locateRequest, setLocateRequest] = useState(null)
  const { globalNotice, taskNotice, toasts, notify, taskNotify, uploadNotify, dismissToast, clearGlobalNotice } = useImageToolNotifications()
  const { imageModels, modelsLoaded } = useImageToolboxModels()
  const { uploadImages } = useImageUploadQueue(uploadNotify)
  const { tasks, submitTask, cancelTask, deleteTask, clearFinishedTasks, refreshTasks } = useImageToolTasks(taskNotify)

  const jimengModels = imageModels.filter(model => model.provider === DERIVE_MODELS_BY_PROVIDER.jimeng)
  const geminiModels = imageModels.filter(model => model.provider === DERIVE_MODELS_BY_PROVIDER.gemini)
  const modelProps = { jimengModels, geminiModels }
  const taskProps = { tasks, submitTask, taskNotice, cancelTask, deleteTask, refreshTasks }
  const locateTask = (task) => {
    if (!task?.task_id) return
    setActiveTab(tabForTask(task.type))
    clearGlobalNotice()
    setLocateRequest({ taskId: task.task_id, taskType: task.type, task, nonce: Date.now() })
  }
  const sharedPanelProps = { uploadImages, notify, ...taskProps, locateRequest, onLocateTask: locateTask }

  return (
    <div className="image-toolbox">
      <header className="image-tool-header">
        <div>
          <h1>图片工具箱</h1>
          <p>九图成片、图片衍生和批量图片反推集中处理，结果仅保存在当前账号目录。</p>
        </div>
        <div className="image-tool-badge"><BadgeCheck size={16} />图片流程</div>
      </header>

      <ToolTabs
        tabs={IMAGE_TOOL_TABS}
        activeTab={activeTab}
        onChange={tabId => {
          setActiveTab(tabId)
          clearGlobalNotice()
        }}
        disabledNotice={PAID_FEATURE_NOTICE}
      />

      <PanelNotice notice={globalNotice} className="image-tool-alert" />

      <div className="image-tool-shell">
        <div className="image-tool-main">
          {activeTab === 'watermark' && (
            <WatermarkPanel
              {...modelProps}
              modelsLoaded={modelsLoaded}
              clearFinishedTasks={clearFinishedTasks}
              {...sharedPanelProps}
            />
          )}
          {activeTab === 'derive' && (
            <DerivePanel {...modelProps} {...sharedPanelProps} />
          )}
          {activeTab === 'reverse' && (
            <ReversePromptPanel {...sharedPanelProps} />
          )}
        </div>
      </div>
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}
