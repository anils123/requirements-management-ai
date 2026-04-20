import { useEffect } from 'react'
import { Users, Mail, Briefcase, Activity } from 'lucide-react'
import { useStore } from '../store'
import { getExperts } from '../api/client'
import clsx from 'clsx'

const AVAIL_COLORS = {
  available:   'bg-green-500/20 text-green-400',
  busy:        'bg-yellow-500/20 text-yellow-400',
  unavailable: 'bg-red-500/20 text-red-400',
}

export function ExpertsPage() {
  const { experts, setExperts } = useStore()

  useEffect(() => {
    getExperts().then(setExperts)
  }, [])

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-surface-600">
        <h1 className="font-semibold text-white">Domain Experts</h1>
        <p className="text-sm text-gray-400 mt-0.5">{experts.length} experts registered</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {experts.map((expert) => {
            const workloadPct = (expert.current_workload / expert.max_workload) * 100
            return (
              <div key={expert.expert_id} className="card space-y-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-brand-600/20 rounded-xl flex items-center justify-center">
                      <span className="text-brand-400 font-semibold text-sm">
                        {expert.name.split(' ').map((n) => n[0]).join('').slice(0, 2)}
                      </span>
                    </div>
                    <div>
                      <p className="font-medium text-gray-200 text-sm">{expert.name}</p>
                      <p className="text-xs text-gray-500">{expert.department}</p>
                    </div>
                  </div>
                  <span className={clsx('badge text-xs', AVAIL_COLORS[expert.availability_status])}>
                    {expert.availability_status}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Mail size={12} />
                  <span className="truncate">{expert.email}</span>
                </div>

                {/* Workload bar */}
                <div>
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span className="flex items-center gap-1"><Activity size={10} /> Workload</span>
                    <span>{expert.current_workload}/{expert.max_workload}</span>
                  </div>
                  <div className="h-1.5 bg-surface-600 rounded-full overflow-hidden">
                    <div
                      className={clsx(
                        'h-full rounded-full transition-all',
                        workloadPct > 80 ? 'bg-red-500' : workloadPct > 50 ? 'bg-yellow-500' : 'bg-green-500'
                      )}
                      style={{ width: `${workloadPct}%` }}
                    />
                  </div>
                </div>

                {/* Skills */}
                <div>
                  <p className="text-xs text-gray-500 mb-2">Specializations</p>
                  <div className="flex flex-wrap gap-1">
                    {expert.specializations.slice(0, 4).map((s) => (
                      <span key={s} className="badge bg-brand-600/20 text-brand-400 text-xs">{s}</span>
                    ))}
                    {expert.specializations.length > 4 && (
                      <span className="badge bg-surface-600 text-gray-500 text-xs">+{expert.specializations.length - 4}</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs text-gray-500 mb-2">Skills</p>
                  <div className="flex flex-wrap gap-1">
                    {expert.skills.slice(0, 5).map((s) => (
                      <span key={s} className="badge bg-surface-600 text-gray-400 text-xs">{s}</span>
                    ))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {experts.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <Users size={40} className="mx-auto mb-3 opacity-30" />
            <p>No experts loaded</p>
          </div>
        )}
      </div>
    </div>
  )
}
