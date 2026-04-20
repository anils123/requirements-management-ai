import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { Activity, Database, Cpu, Zap, TrendingUp, Users, FileText, ListChecks, RefreshCw } from 'lucide-react'
import { getStats } from '../api/client'
import type { SystemStats } from '../types'

const COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b']

const MOCK_DAILY = [
  { day: 'Mon', docs: 2, reqs: 28 },
  { day: 'Tue', docs: 5, reqs: 67 },
  { day: 'Wed', docs: 3, reqs: 41 },
  { day: 'Thu', docs: 8, reqs: 112 },
  { day: 'Fri', docs: 4, reqs: 55 },
  { day: 'Sat', docs: 1, reqs: 14 },
  { day: 'Sun', docs: 3, reqs: 38 },
]

const DOMAIN_DATA = [
  { name: 'Security',     value: 32 },
  { name: 'Performance',  value: 24 },
  { name: 'Integration',  value: 19 },
  { name: 'Data',         value: 15 },
  { name: 'Compliance',   value: 10 },
]

const RAG_PIPELINE = [
  { name: 'Hybrid Search',    status: 'healthy', latency: '45ms' },
  { name: 'CRAG',             status: 'healthy', latency: '120ms' },
  { name: 'HyDE',             status: 'healthy', latency: '80ms' },
  { name: 'Re-ranking',       status: 'healthy', latency: '95ms' },
  { name: 'Semantic Cache',   status: 'healthy', latency: '3ms' },
  { name: 'Knowledge Graph',  status: 'degraded', latency: 'N/A' },
]

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType; label: string; value: string | number; sub?: string; color: string
}) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
        <Icon size={22} />
      </div>
      <div>
        <p className="text-2xl font-bold text-white">{value}</p>
        <p className="text-sm text-gray-400">{label}</p>
        {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export function AdminPage() {
  const [stats, setStats]     = useState<SystemStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getStats().then((s) => { setStats(s); setLoading(false) })
  }, [])

  const refresh = () => {
    setLoading(true)
    getStats().then((s) => { setStats(s); setLoading(false) })
  }

  if (loading || !stats) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-600">
        <div>
          <h1 className="font-semibold text-white">Admin Dashboard</h1>
          <p className="text-sm text-gray-400 mt-0.5">System statistics and RAG pipeline health</p>
        </div>
        <button onClick={refresh} className="btn-ghost text-sm">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={FileText}    label="Total Documents"    value={stats.total_documents}    sub={`+${stats.documents_today} today`}  color="bg-blue-500/20 text-blue-400" />
          <StatCard icon={ListChecks}  label="Requirements"       value={stats.total_requirements} sub={`${stats.pending_reviews} pending`} color="bg-purple-500/20 text-purple-400" />
          <StatCard icon={Users}       label="Domain Experts"     value={stats.total_experts}      color="bg-green-500/20 text-green-400" />
          <StatCard icon={Zap}         label="API Calls Today"    value={stats.api_calls_today}    sub={`${(stats.cache_hit_rate * 100).toFixed(0)}% cache hit`} color="bg-yellow-500/20 text-yellow-400" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Activity chart */}
          <div className="card">
            <h2 className="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
              <TrendingUp size={16} className="text-brand-400" /> Weekly Activity
            </h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={MOCK_DAILY} barGap={4}>
                <XAxis dataKey="day" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: '#1e1e35', border: '1px solid #2e2e50', borderRadius: '8px', color: '#e5e7eb' }}
                  cursor={{ fill: '#2e2e50' }}
                />
                <Bar dataKey="docs" name="Documents" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="reqs" name="Requirements" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Domain distribution */}
          <div className="card">
            <h2 className="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
              <Database size={16} className="text-brand-400" /> Requirements by Domain
            </h2>
            <div className="flex items-center gap-4">
              <ResponsiveContainer width="50%" height={180}>
                <PieChart>
                  <Pie data={DOMAIN_DATA} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={3}>
                    {DOMAIN_DATA.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2">
                {DOMAIN_DATA.map((d, i) => (
                  <div key={d.name} className="flex items-center gap-2 text-xs">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: COLORS[i] }} />
                    <span className="text-gray-400">{d.name}</span>
                    <span className="text-gray-600 ml-auto">{d.value}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* RAG Pipeline health */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
            <Cpu size={16} className="text-brand-400" /> RAG Pipeline Health
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {RAG_PIPELINE.map((item) => (
              <div key={item.name} className="bg-surface-700 rounded-lg px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-300">{item.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{item.latency}</p>
                </div>
                <div className={`w-2.5 h-2.5 rounded-full ${item.status === 'healthy' ? 'bg-green-400 animate-pulse-slow' : 'bg-yellow-400'}`} />
              </div>
            ))}
          </div>
        </div>

        {/* Confidence score */}
        <div className="card">
          <h2 className="text-sm font-medium text-gray-300 mb-4 flex items-center gap-2">
            <Activity size={16} className="text-brand-400" /> Average Extraction Confidence
          </h2>
          <div className="flex items-center gap-4">
            <div className="text-4xl font-bold text-white">{(stats.avg_confidence * 100).toFixed(1)}%</div>
            <div className="flex-1">
              <div className="h-3 bg-surface-600 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-brand-600 to-brand-400 rounded-full"
                  style={{ width: `${stats.avg_confidence * 100}%` }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">Target: 90% · Current: {(stats.avg_confidence * 100).toFixed(1)}%</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
