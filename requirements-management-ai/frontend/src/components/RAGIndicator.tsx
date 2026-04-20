import { Brain, RefreshCw, Eye, GitBranch, Layers } from 'lucide-react'
import type { RAGInfo } from '../types'
import clsx from 'clsx'

interface Props { ragInfo: RAGInfo }

const STRATEGY_LABELS: Record<string, string> = {
  hybrid:      'Hybrid Search',
  vector_only: 'Vector Search',
  text_only:   'BM25 Search',
  decomposed:  'Decomposed',
}

export function RAGIndicator({ ragInfo }: Props) {
  const badges = [
    { active: true,                    icon: Layers,    label: STRATEGY_LABELS[ragInfo.strategy] || ragInfo.strategy, color: 'bg-blue-500/20 text-blue-400' },
    { active: ragInfo.corrective_used, icon: RefreshCw, label: 'CRAG',        color: 'bg-orange-500/20 text-orange-400' },
    { active: ragInfo.hyde_used,       icon: Brain,     label: 'HyDE',        color: 'bg-purple-500/20 text-purple-400' },
    { active: ragInfo.reranked,        icon: GitBranch, label: 'Re-ranked',   color: 'bg-green-500/20 text-green-400' },
    { active: ragInfo.hallucination_check, icon: Eye,   label: 'Grounded',   color: 'bg-teal-500/20 text-teal-400' },
  ]

  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {badges.filter((b) => b.active).map(({ icon: Icon, label, color }) => (
        <span key={label} className={clsx('badge text-xs', color)}>
          <Icon size={10} />
          {label}
        </span>
      ))}
      {ragInfo.sub_queries && ragInfo.sub_queries.length > 0 && (
        <span className="badge bg-yellow-500/20 text-yellow-400 text-xs">
          {ragInfo.sub_queries.length} sub-queries
        </span>
      )}
    </div>
  )
}
