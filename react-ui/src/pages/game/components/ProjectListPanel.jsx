import { FolderOpen, Gamepad2, Pencil, Plus, Settings, Trash2 } from 'lucide-react'

export default function ProjectListPanel({
  projects,
  showNewProject,
  newProjectName,
  renamingProjectId,
  renamingProjectName,
  imageLightboxOverlay,
  onOpenSettings,
  onStartNewProject,
  onNewProjectNameChange,
  onCreateProject,
  onCancelNewProject,
  onOpenProject,
  onDeleteProject,
  onStartRenameProject,
  onRenameProjectNameChange,
  onSaveProjectRename,
  onCancelProjectRename,
}) {
  return (
    <div style={{ padding: 32, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <Gamepad2 size={28} color="var(--accent)" />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>游戏视频素材工具</h1>
        <div style={{ flex: 1 }} />
        <button onClick={onOpenSettings} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 8, fontSize: 12, background: 'var(--bg-secondary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
          <Settings size={14} /> API 设置
        </button>
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        {showNewProject ? (
          <div style={{ display: 'flex', gap: 8, flex: 1 }}>
            <input id="game-new-project-name" value={newProjectName} onChange={e => onNewProjectNameChange(e.target.value)} onKeyDown={e => e.key === 'Enter' && onCreateProject()} placeholder="输入项目名称..." autoFocus
              style={{ flex: 1, padding: '10px 14px', borderRadius: 10, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 14 }} />
            <button onClick={onCreateProject} style={{ padding: '10px 20px', borderRadius: 10, fontSize: 13, fontWeight: 600, background: 'var(--accent-gradient)', color: '#fff' }}>创建</button>
            <button onClick={onCancelNewProject} style={{ padding: '10px 14px', borderRadius: 10, fontSize: 13, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>取消</button>
          </div>
        ) : (
          <button onClick={onStartNewProject} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px', borderRadius: 10, fontSize: 14, fontWeight: 600, background: 'var(--accent-gradient)', color: '#fff', boxShadow: '0 4px 14px rgba(139,92,246,0.25)' }}>
            <Plus size={18} /> 新建项目
          </button>
        )}
      </div>
      {projects.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)', background: 'var(--bg-secondary)', borderRadius: 16, border: '1px solid var(--border)' }}>
          <Gamepad2 size={48} style={{ opacity: 0.3, marginBottom: 16 }} /><div style={{ fontSize: 15 }}>还没有项目，点击上方"新建项目"开始</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {projects.map(p => (
            <div key={p.id} onClick={() => { if (renamingProjectId === p.id) return; onOpenProject(p) }} style={{ padding: 20, borderRadius: 14, cursor: renamingProjectId === p.id ? 'default' : 'pointer', background: 'var(--bg-secondary)', border: '1px solid var(--border)', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.transform = renamingProjectId === p.id ? 'none' : 'translateY(-2px)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                  <FolderOpen size={18} color="var(--accent)" style={{ flexShrink: 0 }} />
                  {renamingProjectId === p.id ? (
                    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, flex: 1 }} onClick={e => e.stopPropagation()}>
                      <input
                        value={renamingProjectName}
                        onChange={e => onRenameProjectNameChange(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') onSaveProjectRename(); if (e.key === 'Escape') onCancelProjectRename() }}
                        autoFocus
                        style={{ flex: 1, minWidth: 120, padding: '6px 10px', borderRadius: 8, background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 14 }}
                      />
                      <button type="button" onClick={onSaveProjectRename} style={{ padding: '6px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, background: 'var(--accent-gradient)', color: '#fff', border: 'none', cursor: 'pointer' }}>保存</button>
                      <button type="button" onClick={onCancelProjectRename} style={{ padding: '6px 12px', borderRadius: 8, fontSize: 12, background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border)', cursor: 'pointer' }}>取消</button>
                    </div>
                  ) : (
                    <span style={{ fontSize: 15, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
                  )}
                </div>
                {renamingProjectId !== p.id && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                    <button
                      type="button"
                      title="重命名项目"
                      onClick={e => { e.stopPropagation(); onStartRenameProject(p) }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600,
                        background: 'var(--bg-primary)', color: 'var(--text-secondary)', border: '1px solid var(--border)', cursor: 'pointer', whiteSpace: 'nowrap',
                      }}
                    >
                      <Pencil size={13} />重命名
                    </button>
                    <button type="button" title="删除项目" onClick={e => { e.stopPropagation(); onDeleteProject(p.id) }} style={{ background: 'none', color: 'var(--text-muted)', padding: 6, cursor: 'pointer', lineHeight: 0 }}><Trash2 size={16} /></button>
                  </div>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(p.created_at).toLocaleDateString()}</div>
            </div>
          ))}
        </div>
      )}
      {imageLightboxOverlay}
    </div>
  )
}
