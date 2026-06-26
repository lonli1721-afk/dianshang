import { BadgeCheck } from 'lucide-react'
import { useState } from 'react'
import { DERIVE_MODELS_BY_PROVIDER, IMAGE_TOOL_TABS, PAID_FEATURE_NOTICE } from './image-toolbox/constants'
import { DerivePanel } from './image-toolbox/components/DerivePanel'
import { PanelNotice } from './image-toolbox/components/PanelNotice'
import { ReversePromptPanel } from './image-toolbox/components/ReversePromptPanel'
import { StandaloneImagePanel } from './image-toolbox/components/StandaloneImagePanel'
import { ToastStack } from './image-toolbox/components/ToastStack'
import { ToolTabs } from './image-toolbox/components/ToolTabs'
import { WatermarkPanel } from './image-toolbox/components/WatermarkPanel'
import { useImageToolNotifications } from './image-toolbox/useImageToolNotifications'
import { useImageToolboxModels } from './image-toolbox/useImageToolboxModels'
import { useImageToolTasks } from './image-toolbox/useImageToolTasks'
import { useImageUploadQueue } from './image-toolbox/useImageUploadQueue'

const tabForTask = (type) => (type === 'derive' ? 'derive' : type === 'reverse_prompts' ? 'reverse' : 'watermark')

const IMAGE_TOOLBOX_READABLE_STYLE = `
  .image-tool-readable {
    font-size: 14px;
  }
  .image-tool-readable button,
  .image-tool-readable input,
  .image-tool-readable select,
  .image-tool-readable textarea,
  .image-tool-readable label,
  .image-tool-readable .image-tool-tab,
  .image-tool-readable .image-tool-mode-card,
  .image-tool-readable .image-tool-task-card,
  .image-tool-readable .image-tool-task-pill,
  .image-tool-readable .image-tool-field,
  .image-tool-readable .image-tool-empty,
  .image-tool-readable .image-tool-alert,
  .image-tool-readable .image-tool-badge,
  .image-tool-readable .image-tool-secondary,
  .image-tool-readable .image-tool-primary,
  .image-tool-readable .image-tool-setting-summary,
  .image-tool-readable .image-tool-thumb-meta,
  .image-tool-readable .image-tool-result-actions,
  .image-tool-readable .image-tool-prompt-box,
  .image-tool-readable .image-tool-assist-panel {
    font-size: 13px !important;
    line-height: 1.55 !important;
  }
  .image-tool-readable textarea {
    font-size: 14px !important;
    line-height: 1.75 !important;
  }
  .image-tool-readable small,
  .image-tool-readable .image-tool-tab-status,
  .image-tool-readable .image-tool-task-foot,
  .image-tool-readable .image-tool-inline-warning,
  .image-tool-readable .image-tool-muted {
    font-size: 12px !important;
    line-height: 1.5 !important;
  }
`

export default function ImageToolboxPage() {
  const [activeTab, setActiveTab] = useState('standalone')
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
    <>
    <style>{IMAGE_TOOLBOX_READABLE_STYLE}</style>
    <div className="image-toolbox image-tool-readable">
      <header className="image-tool-header">
        <div>
          <h1>图片工作台</h1>
          <p>电商主图、详情页切片、图片衍生和批量图片反推集中处理，结果仅保存在当前账号目录。</p>
        </div>
        <div className="image-tool-badge"><BadgeCheck size={16} />图片工作台</div>
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
          {activeTab === 'standalone' && (
            <StandaloneImagePanel
              imageModels={imageModels}
              modelsLoaded={modelsLoaded}
              onOpenImage={(url) => window.open(url, '_blank', 'noopener,noreferrer')}
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
    </>
  )
}
