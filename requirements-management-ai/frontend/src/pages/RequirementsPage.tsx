import { useEffect, useState, useCallback } from 'react'
import {
  ListChecks, ChevronDown, User, Shield, Zap, CheckCircle,
  XCircle, RefreshCw, FileText, Loader2
} from 'lucide-react'
import { useStore } from '../store'
import { assignExperts, checkCompliance } from '../api/client'
import type { Requirement } from '../types'
import clsx from 'clsx'

const PRIORITY_COLORS: Record<string, string> = {
  high:   'bg-red-500/20 text-red-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low:    'bg-green-500/20 text-green-400',
}
const STATUS_COLORS: Record<string, string> = {
  extracted: 'bg-blue-500/20 text-blue-400',
  reviewed:  'bg-yellow-500/20 text-yellow-400',
  approved:  'bg-green-500/20 text-green-400',
  rejected:  'bg-red-500/20 text-red-400',
}
const DOMAIN_ICONS: Record<string, React.ElementType> = {
  security: Shield, performance: Zap, integration: ListChecks,
}

export function RequirementsPage() {
  const { requirements, setRequirements, updateRequirement } = useStore()
  const [filter,    setFilter]   = useState('all')
  const [search,    setSearch]   = useState('')
  const [docFilter, setDocFilter]= useState('all')
  const [expanded,  setExpanded] = useState<string | null>(null)
  const [loading,   setLoading]  = useState(false)
  const [docIds,    setDocIds]   = useState<string[]>([])

  // Always fetch fresh from Aurora
  const fetchRequirements = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/requirements')
      const data = await resp.json()
      const reqs = data.requirements || []
      setRequirements(reqs)
      // Build unique document list for filter
      const ids = [...new Set(reqs.map((r: Requirement) => r.document_id).filter(Boolean))] as string[]
      setDocIds(ids)
    } catch (e) {
      console.error('Failed to fetch requirements:', e)
    } finally {
      setLoading(false)
    }
  }, [setRequirements])

  // Fetch on mount only — DocumentsPage pushes new reqs into store after extraction
  useEffect(() => { fetchRequirements() }, [])

  const filtered = requirements.filter((r) => {
    const matchDoc    = docFilter === 'all' || r.document_id === docFilter
    const matchFilter = filter === 'all' || r.priority === filter || r.status === filter || r.domain === filter
    const matchSearch = !search ||
      r.description?.toLowerCase().includes(search.toLowerCase()) ||
      r.requirement_id?.toLowerCase().includes(search.toLowerCase()) ||
      r.document_id?.toLowerCase().includes(search.toLowerCase())
    return matchDoc && matchFilter && matchSearch
  })

  const counts = {
    all:      requirements.length,
    high:     requirements.filter((r) => r.priority === 'high').length,
    pending:  requirements.filter((r) => r.status === 'extracted').length,
    approved: requirements.filter((r) => r.status === 'approved').length,
  }

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

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-surface-600">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="font-semibold text-white">Requirements</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              {requirements.length} requirements across {docIds.length} documents
            </p>
          </div>
          <button
            onClick={fetchRequirements}
            disabled={loading}
            className="btn-ghost text-sm"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {/* Document filter */}
        {docIds.length > 1 && (
          <div className="flex gap-2 mb-3 flex-wrap">
            <button
              onClick={() => setDocFilter('all')}
              className={clsx('px-3 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1',
                docFilter === 'all' ? 'bg-brand-600 text-white' : 'bg-surface-700 text-gray-400 hover:text-white')}
            >
              <FileText size={10} /> All Documents
            </button>
            {docIds.map((id) => (
              <button
                key={id}
                onClick={() => setDocFilter(id)}
                className={clsx('px-3 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1',
                  docFilter === id ? 'bg-brand-600 text-white' : 'bg-surface-700 text-gray-400 hover:text-white')}
              >
                <FileText size={10} />
                {id}
                <span className="opacity-60">
                  ({requirements.filter(r => r.document_id === id).length})
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Priority / status filters */}
        <div className="flex gap-2 flex-wrap">
          {[
            { id: 'all',       label: `All (${counts.all})` },
            { id: 'high',      label: `High (${counts.high})` },
            { id: 'extracted', label: `Pending (${counts.pending})` },
            { id: 'approved',  label: `Approved (${counts.approved})` },
          ].map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                filter === id ? 'bg-surface-500 text-white' : 'bg-surface-700 text-gray-400 hover:text-white'
              )}
            >
              {label}
            </button>
          ))}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search requirements..."
            className="input text-xs py-1.5 ml-auto w-52"
          />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-6 space-y-2">
        {loading && requirements.length === 0 && (
          <div className="flex items-center justify-center py-12 text-gray-500 gap-2">
            <Loader2 size={18} className="animate-spin" />
            Loading requirements...
          </div>
        )}

        {!loading && filtered.length === 0 && requirements.length > 0 && (
          <div className="text-center py-12 text-gray-500">
            <ListChecks size={40} className="mx-auto mb-3 opacity-30" />
            <p>No requirements match the current filter</p>
          </div>
        )}

        {!loading && requirements.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <ListChecks size={40} className="mx-auto mb-3 opacity-30" />
            <p>No requirements yet</p>
            <p className="text-sm mt-1">Go to Documents → upload a PDF → click Extract Reqs</p>
          </div>
        )}

        {filtered.map((req) => {
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
                    {req.priority && (
                      <span className={clsx('badge', PRIORITY_COLORS[req.priority] || 'bg-surface-600 text-gray-400')}>
                        {req.priority}
                      </span>
                    )}
                    {req.status && (
                      <span className={clsx('badge', STATUS_COLORS[req.status] || 'bg-surface-600 text-gray-400')}>
                        {req.status}
                      </span>
                    )}
                    <span className="badge bg-surface-600 text-gray-400">{req.domain}</span>
                    <span className="badge bg-surface-700 text-gray-500 text-xs">
                      <FileText size={9} /> {req.document_id}
                    </span>
                    {req.confidence_score > 0 && (
                      <span className="text-xs text-gray-500 ml-auto">
                        {(req.confidence_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-200 mt-1 line-clamp-2">{req.description}</p>
                </div>
                <ChevronDown
                  size={16}
                  className={clsx('text-gray-500 shrink-0 transition-transform mt-1', isExpanded && 'rotate-180')}
                />
              </div>

              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-surface-600 space-y-4 animate-slide-up">
                  {req.acceptance_criteria && req.acceptance_criteria.length > 0 && (
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
                      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Compliance</p>
                      <p className="text-sm text-gray-300 bg-surface-700 rounded-lg p-3">
                        {req.compliance.compliance_text}
                      </p>
                    </div>
                  )}

                  <div className="flex gap-2 flex-wrap">
                    <button onClick={() => handleAssign(req)} className="btn-primary text-xs py-1.5">
                      <User size={12} /> Assign Experts
                    </button>
                    <button
                      onClick={() => handleCompliance(req)}
                      className="btn-primary text-xs py-1.5 bg-surface-600 hover:bg-surface-500"
                    >
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
      </div>
    </div>
  )
}
