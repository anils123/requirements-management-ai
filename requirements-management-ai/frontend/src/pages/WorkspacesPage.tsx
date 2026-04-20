import { FolderOpen, Plus, FileText, ListChecks, Calendar, Archive } from 'lucide-react'
import { useStore } from '../store'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

export function WorkspacesPage() {
  const { workspaces, activeWorkspace, setActiveWorkspace } = useStore()

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-600">
        <div>
          <h1 className="font-semibold text-white">Workspaces</h1>
          <p className="text-sm text-gray-400 mt-0.5">Manage project workspaces and bid workflows</p>
        </div>
        <button className="btn-primary text-sm">
          <Plus size={14} /> New Workspace
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {workspaces.map((ws) => (
            <div
              key={ws.id}
              onClick={() => setActiveWorkspace(ws.id)}
              className={clsx(
                'card cursor-pointer transition-all hover:border-brand-500/50',
                activeWorkspace === ws.id && 'border-brand-500 bg-brand-600/5'
              )}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 bg-brand-600/20 rounded-xl flex items-center justify-center">
                  <FolderOpen size={18} className="text-brand-400" />
                </div>
                <span className={clsx(
                  'badge text-xs',
                  ws.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                )}>
                  {ws.status}
                </span>
              </div>

              <h3 className="font-semibold text-white mb-1">{ws.name}</h3>
              <p className="text-sm text-gray-400 mb-4">{ws.description}</p>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="flex items-center gap-1.5 text-gray-500">
                  <FileText size={12} className="text-brand-400" />
                  <span>{ws.documents} documents</span>
                </div>
                <div className="flex items-center gap-1.5 text-gray-500">
                  <ListChecks size={12} className="text-brand-400" />
                  <span>{ws.requirements} requirements</span>
                </div>
                <div className="flex items-center gap-1.5 text-gray-500 col-span-2">
                  <Calendar size={12} />
                  <span>Created {formatDistanceToNow(new Date(ws.created_at), { addSuffix: true })}</span>
                </div>
              </div>

              {activeWorkspace === ws.id && (
                <div className="mt-3 pt-3 border-t border-surface-600">
                  <span className="text-xs text-brand-400 font-medium">Active workspace</span>
                </div>
              )}
            </div>
          ))}

          {/* New workspace placeholder */}
          <div className="card border-dashed border-surface-500 flex flex-col items-center justify-center py-8 cursor-pointer hover:border-brand-500/50 transition-colors">
            <Plus size={24} className="text-gray-600 mb-2" />
            <p className="text-sm text-gray-500">Create new workspace</p>
          </div>
        </div>
      </div>
    </div>
  )
}
