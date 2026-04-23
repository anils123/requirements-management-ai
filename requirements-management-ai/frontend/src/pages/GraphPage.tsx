import { useEffect, useState } from 'react'
import { GitBranch, Search, RefreshCw, Loader2, ChevronRight, Database, Users, FileText, ListChecks, Globe } from 'lucide-react'
import clsx from 'clsx'

interface GraphStats {
  nodes: Record<string, number>
  edges: Record<string, number>
  total_nodes: number
  total_edges: number
}

interface GraphResult {
  node_id:      string
  label:        string
  properties:   Record<string, any>
  relationship?: string
  weight?:       number
  similarity?:   number
}

const LABEL_ICONS: Record<string, React.ElementType> = {
  Document:    FileText,
  Requirement: ListChecks,
  Expert:      Users,
  Domain:      Globe,
  Entity:      GitBranch,
}

const LABEL_COLORS: Record<string, string> = {
  Document:    'bg-blue-500/20 text-blue-400 border-blue-500/30',
  Requirement: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  Expert:      'bg-green-500/20 text-green-400 border-green-500/30',
  Domain:      'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  Entity:      'bg-orange-500/20 text-orange-400 border-orange-500/30',
}

const REL_COLORS: Record<string, string> = {
  CONTAINS:       'text-blue-400',
  EXTRACTED_FROM: 'text-purple-400',
  ASSIGNED_TO:    'text-green-400',
  SPECIALIZES_IN: 'text-yellow-400',
  SIMILAR_TO:     'text-pink-400',
  MENTIONS:       'text-orange-400',
}

async function callGraphAgent(action: string, params: Record<string, any> = {}) {
  const resp = await fetch('/api/search', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ action: 'graph_agent', ...params, _graph_action: action }),
  })
  // Direct Lambda call via backend
  const r = await fetch('/api/graph', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ action, ...params }),
  })
  return r.ok ? r.json() : { error: await r.text() }
}

export function GraphPage() {
  const [stats,    setStats]    = useState<GraphStats | null>(null)
  const [results,  setResults]  = useState<GraphResult[]>([])
  const [loading,  setLoading]  = useState(false)
  const [query,    setQuery]    = useState('')
  const [label,    setLabel]    = useState('')
  const [action,   setAction]   = useState('semantic_search')
  const [nodeKey,  setNodeKey]  = useState('')
  const [rel,      setRel]      = useState('')
  const [error,    setError]    = useState('')

  const loadStats = async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/graph', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ action: 'graph_stats' }),
      })
      const data = await r.json()
      setStats(data)
    } catch (e) {
      setError('Failed to load graph stats')
    } finally {
      setLoading(false)
    }
  }

  const runQuery = async () => {
    setLoading(true)
    setError('')
    setResults([])
    try {
      const params: Record<string, any> = { action }
      if (query)   params.query     = query
      if (label)   params.label     = label
      if (nodeKey) params.key       = nodeKey
      if (rel)     params.relationship = rel

      const r = await fetch('/api/graph', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(params),
      })
      const data = await r.json()
      const items = data.results || data.experts || data.documents || data.outgoing || []
      setResults(items)
      if (data.error) setError(data.error)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStats() }, [])

  const nodeTypes = stats ? Object.entries(stats.nodes) : []
  const edgeTypes = stats ? Object.entries(stats.edges) : []

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-600">
        <div className="flex items-center gap-2">
          <GitBranch size={18} className="text-brand-400" />
          <div>
            <h1 className="font-semibold text-white">Knowledge Graph</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              {stats ? `${stats.total_nodes} nodes · ${stats.total_edges} edges` : 'Loading...'}
            </p>
          </div>
        </div>
        <button onClick={loadStats} className="btn-ghost text-sm">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* Graph Stats */}
        {stats && (
          <div className="grid grid-cols-2 gap-4">
            <div className="card">
              <h2 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
                <Database size={14} className="text-brand-400" /> Node Types
              </h2>
              <div className="space-y-2">
                {nodeTypes.map(([label, count]) => {
                  const Icon  = LABEL_ICONS[label] || GitBranch
                  const color = LABEL_COLORS[label] || 'bg-surface-600 text-gray-400 border-surface-500'
                  return (
                    <div key={label} className={clsx('flex items-center justify-between px-3 py-2 rounded-lg border', color)}>
                      <div className="flex items-center gap-2">
                        <Icon size={14} />
                        <span className="text-sm font-medium">{label}</span>
                      </div>
                      <span className="text-sm font-bold">{count}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="card">
              <h2 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
                <ChevronRight size={14} className="text-brand-400" /> Relationship Types
              </h2>
              <div className="space-y-2">
                {edgeTypes.map(([rel, count]) => (
                  <div key={rel} className="flex items-center justify-between px-3 py-2 bg-surface-700 rounded-lg">
                    <span className={clsx('text-sm font-mono', REL_COLORS[rel] || 'text-gray-400')}>
                      {rel}
                    </span>
                    <span className="text-sm text-gray-400">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Query Panel */}
        <div className="card space-y-4">
          <h2 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <Search size={14} className="text-brand-400" /> Graph Query
          </h2>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Action</label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
                className="input text-sm"
              >
                <option value="semantic_search">Semantic Search</option>
                <option value="find_experts">Find Experts</option>
                <option value="past_requirements">Past Requirements</option>
                <option value="traverse">Traverse</option>
                <option value="neighbourhood">Neighbourhood</option>
                <option value="list_documents">List Documents</option>
                <option value="graph_stats">Graph Stats</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Node Label (optional)</label>
              <select value={label} onChange={(e) => setLabel(e.target.value)} className="input text-sm">
                <option value="">All labels</option>
                <option value="Requirement">Requirement</option>
                <option value="Expert">Expert</option>
                <option value="Document">Document</option>
                <option value="Domain">Domain</option>
                <option value="Entity">Entity</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Query / Domain</label>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. voltage requirements, security..."
                className="input text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Node Key (for traverse)</label>
              <input
                value={nodeKey}
                onChange={(e) => setNodeKey(e.target.value)}
                placeholder="e.g. bids/CH_Charging System.pdf"
                className="input text-sm"
              />
            </div>
          </div>

          <button onClick={runQuery} disabled={loading} className="btn-primary w-full justify-center">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {loading ? 'Querying graph...' : 'Run Graph Query'}
          </button>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        {/* Results */}
        {results.length > 0 && (
          <div>
            <h2 className="text-sm font-medium text-gray-400 mb-3">
              {results.length} results
            </h2>
            <div className="space-y-2">
              {results.map((r, i) => {
                const Icon  = LABEL_ICONS[r.label] || GitBranch
                const color = LABEL_COLORS[r.label] || 'bg-surface-700 text-gray-400 border-surface-600'
                const props = r.properties || {}
                return (
                  <div key={i} className={clsx('card border', color.split(' ')[2] || 'border-surface-600')}>
                    <div className="flex items-start gap-3">
                      <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0', color.split(' ').slice(0,2).join(' '))}>
                        <Icon size={14} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-medium text-gray-300">{r.label}</span>
                          {r.relationship && (
                            <span className={clsx('text-xs font-mono', REL_COLORS[r.relationship] || 'text-gray-500')}>
                              [{r.relationship}]
                            </span>
                          )}
                          {r.similarity !== undefined && (
                            <span className="text-xs text-brand-400 ml-auto">
                              {(r.similarity * 100).toFixed(1)}% match
                            </span>
                          )}
                          {r.weight !== undefined && r.similarity === undefined && (
                            <span className="text-xs text-gray-500 ml-auto">
                              weight={r.weight.toFixed(3)}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-200 mt-1 truncate">
                          {props.description || props.name || props._key || r.node_id}
                        </p>
                        <div className="flex gap-3 mt-1 text-xs text-gray-500 flex-wrap">
                          {props.domain     && <span>domain: {props.domain}</span>}
                          {props.priority   && <span>priority: {props.priority}</span>}
                          {props.department && <span>dept: {props.department}</span>}
                          {props.document_id && <span>doc: {props.document_id}</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
