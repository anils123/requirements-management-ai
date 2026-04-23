import { MessageSquare, FileText, ListChecks, Users, LayoutDashboard, Settings, ChevronLeft, ChevronRight, Zap, FolderOpen, GitBranch } from 'lucide-react'
import { useStore } from '../store'
import clsx from 'clsx'

const NAV = [
  { id: 'chat',         label: 'AI Chat',       icon: MessageSquare },
  { id: 'documents',    label: 'Documents',     icon: FileText },
  { id: 'requirements', label: 'Requirements',  icon: ListChecks },
  { id: 'experts',      label: 'Experts',       icon: Users },
  { id: 'graph',        label: 'Knowledge Graph', icon: GitBranch },
  { id: 'workspaces',   label: 'Workspaces',    icon: FolderOpen },
  { id: 'admin',        label: 'Admin',         icon: LayoutDashboard },
]

export function Sidebar() {
  const { sidebarOpen, setSidebarOpen, activeTab, setActiveTab, workspaces, activeWorkspace, setActiveWorkspace } = useStore()

  return (
    <aside className={clsx(
      'flex flex-col bg-surface-800 border-r border-surface-600 transition-all duration-300 shrink-0',
      sidebarOpen ? 'w-56' : 'w-14'
    )}>
      {/* Logo */}
      <div className="flex items-center gap-2 px-3 py-4 border-b border-surface-600">
        <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center shrink-0">
          <Zap size={16} className="text-white" />
        </div>
        {sidebarOpen && (
          <div className="overflow-hidden">
            <p className="text-sm font-semibold text-white truncate">ReqsAI</p>
            <p className="text-xs text-gray-500 truncate">Bedrock AgentCore</p>
          </div>
        )}
      </div>

      {/* Workspace selector */}
      {sidebarOpen && (
        <div className="px-2 py-2 border-b border-surface-600">
          <p className="text-xs text-gray-500 px-2 mb-1 uppercase tracking-wider">Workspace</p>
          {workspaces.map((ws) => (
            <button
              key={ws.id}
              onClick={() => setActiveWorkspace(ws.id)}
              className={clsx(
                'w-full text-left px-2 py-1.5 rounded-lg text-xs transition-colors truncate',
                activeWorkspace === ws.id
                  ? 'bg-brand-600/20 text-brand-400'
                  : 'text-gray-400 hover:text-white hover:bg-surface-600'
              )}
            >
              {ws.name}
            </button>
          ))}
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={clsx(
              'w-full flex items-center gap-3 px-2 py-2 rounded-lg transition-all duration-150 text-sm',
              activeTab === id
                ? 'bg-brand-600/20 text-brand-400 font-medium'
                : 'text-gray-400 hover:text-white hover:bg-surface-600'
            )}
            title={!sidebarOpen ? label : undefined}
          >
            <Icon size={18} className="shrink-0" />
            {sidebarOpen && <span className="truncate">{label}</span>}
          </button>
        ))}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="flex items-center justify-center p-3 border-t border-surface-600 text-gray-500 hover:text-white transition-colors"
      >
        {sidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </button>
    </aside>
  )
}
