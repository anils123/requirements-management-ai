import { useEffect, useState } from 'react'
import { ListChecks, Filter, ChevronDown, User, Shield, Zap, CheckCircle, Clock, XCircle, AlertTriangle } from 'lucide-react'
import { useStore } from '../store'
import { getRequirements, assignExperts, checkCompliance } from '../api/client'
import type { Requirement } from '../types'
import clsx from 'clsx'

const PRIORITY_COLORS = {
  high:   'bg-red-500/20 text-red-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low:    'bg-green-500/20 text-green-400',
}

const STATUS_COLORS = {
  extracted: 'bg-blue-500/20 text-blue-400',
  reviewed:  'bg-yellow-500/20 text-yellow-400',
  approved:  'bg-green-500/20 text-green-400',
  rejected:  'bg-red-500/20 text-red-400',
}

const DOMAIN_ICONS: Record<string, React.ElementType> = {
  security:    Shield,
  performance: Zap,
  integration: ListChecks,
}

export function RequirementsPage() {
  const { requirements, setRequirements, updateRequirement } = useStore()
  const [filter, setFilter]   = useState<string>('all')
  const [search, setSearch]   = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    // Fetch all requirements from Aurora on mount
    fetch('/api/requirements')
      .then((r) => r.json())
      .then((data) => {
        const reqs = data.requirements || []
        if (reqs.length > 0) setRequirements(reqs)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = requirements.filter((r) => {
    const matchFilter = filter === 'all' || r.priority === filter || r.status === filter || r.domain === filter
    const matchSearch = !search || r.description.toLowerCase().includes(search.toLowerCase()) || r.requirement_id.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  const handleAssign = async (req: Requirement) => {
    const result = await assignExperts([req])
    if (result?.assignments?.[0]) {
      updateRequirement(req.requirement_id, {
        assigned_experts: result.assignments[0].assigned_experts,
      })
    }
  }

  const handleCompliance = async (req: Requirement) => {
    const result = await checkCompliance(req)
    updateRequirement(req.requirement_id, { compliance: result })
  }

  const counts = {
    all:       requirements.length,
    high:      requirements.filter((r) => r.priority === 'high').length,
    pending:   requirements.filter((r) => r.status === 'extracted').length,
    approved:  requirements.filter((r) => r.status === 'approved').length,
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-surface-600">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-semibold text-white">Requirements</h1>
            <p className="text-sm text-gray-400 mt-0.5">{requirements.length} extracted requirements</p>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mt-4 flex-wrap">
          {[
            { id: 'all',     label: `All (${counts.all})` },
            { id: 'high',    label: `High Priority (${counts.high})` },
            { id: 'extracted', label: `Pending Review (${counts.pending})` },
            { id: 'approved',  label: `Approved (${counts.approved})` },
          ].map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                filter === id ? 'bg-brand-600 text-white' : 'bg-surface-700 text-gray-400 hover:text-white'
              )}
            >
              {label}
            </button>
          ))}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search requirements..."
            className="input text-xs py-1.5 ml-auto w-48"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-2">
        {loading && (
          <div className="text-center py-12 text-gray-500">
            <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            Loading requirements...
          </div>
        )}

        {!loading && filtered.map((req) => {
          const DomainIcon = DOMAIN_ICONS[req.domain] || ListChecks
          const isExpanded = expanded === req.requirement_id

          return (
            <div key={req.requirement_id} className="card hover:border-surface-500 transition-colors">
              <div
                className="flex items-start gap-3 cursor-pointer"
                onClick={() => setExpanded(isExpanded ? null : req.requirement_id)}
              >
                <div className="w-8 h-8 bg-surface-600 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                  <DomainIcon size={14} className="text-brand-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono text-gray-500">{req.requirement_id}</span>
                    <span className={clsx('badge', PRIORITY_COLORS[req.priority])}>{req.priority}</span>
                    <span className={clsx('badge', STATUS_COLORS[req.status])}>{req.status}</span>
                    <span className="badge bg-surface-600 text-gray-400">{req.domain}</span>
                    <span className="text-xs text-gray-500 ml-auto">
                      {(req.confidence_score * 100).toFixed(0)}% confidence
                    </span>
                  </div>
                  <p className="text-sm text-gray-200 mt-1 line-clamp-2">{req.description}</p>
                </div>
                <ChevronDown size={16} className={clsx('text-gray-500 shrink-0 transition-transform mt-1', isExpanded && 'rotate-180')} />
              </div>

              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-surface-600 space-y-4 animate-slide-up">
                  {req.acceptance_criteria.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Acceptance Criteria</p>
                      <ul className="space-y-1">
                        {req.acceptance_criteria.map((c, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                            <CheckCircle size={12} className="text-green-400 mt-0.5 shrink-0" />
                            {c}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {req.assigned_experts && req.assigned_experts.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Assigned Experts</p>
                      <div className="flex gap-2 flex-wrap">
                        {req.assigned_experts.map((e) => (
                          <div key={e.expert_id} className="flex items-center gap-2 bg-surface-600 rounded-lg px-3 py-1.5 text-xs">
                            <User size={12} className="text-brand-400" />
                            <span className="text-gray-300">{e.name}</span>
                            <span className="text-gray-500">{e.department}</span>
                            <span className="text-brand-400">{(e.combined_score * 100).toFixed(0)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {req.compliance && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Compliance Suggestion</p>
                      <p className="text-sm text-gray-300 bg-surface-700 rounded-lg p-3">{req.compliance.compliance_text}</p>
                    </div>
                  )}

                  <div className="flex gap-2 flex-wrap">
                    <button onClick={() => handleAssign(req)} className="btn-primary text-xs py-1.5">
                      <User size={12} /> Assign Experts
                    </button>
                    <button onClick={() => handleCompliance(req)} className="btn-primary text-xs py-1.5 bg-surface-600 hover:bg-surface-500">
                      <Shield size={12} /> Check Compliance
                    </button>
                    <button
                      onClick={() => updateRequirement(req.requirement_id, { status: 'approved' })}
                      className="btn-primary text-xs py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400"
                    >
                      <CheckCircle size={12} /> Approve
                    </button>
                    <button
                      onClick={() => updateRequirement(req.requirement_id, { status: 'rejected' })}
                      className="btn-primary text-xs py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400"
                    >
                      <XCircle size={12} /> Reject
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}

        {!loading && filtered.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <ListChecks size={40} className="mx-auto mb-3 opacity-30" />
            <p>No requirements found</p>
            <p className="text-sm mt-1">Upload and process a document to extract requirements</p>
          </div>
        )}
      </div>
    </div>
  )
}
