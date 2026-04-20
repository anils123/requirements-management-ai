import { ExternalLink, FileText } from 'lucide-react'
import type { Citation } from '../types'

interface Props { citations: Citation[] }

export function CitationList({ citations }: Props) {
  if (!citations.length) return null

  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Sources</p>
      {citations.map((c, i) => (
        <div key={i} className="flex items-start gap-2 bg-surface-700 rounded-lg px-3 py-2 text-xs">
          <FileText size={12} className="text-brand-400 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-gray-300 truncate font-mono">{c.source}</p>
            {c.text_snippet && (
              <p className="text-gray-500 mt-0.5 line-clamp-2">{c.text_snippet}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-gray-500">chunk {c.chunk_id}</span>
            <span className={`font-medium ${c.relevance_score > 0.8 ? 'text-green-400' : c.relevance_score > 0.6 ? 'text-yellow-400' : 'text-red-400'}`}>
              {(c.relevance_score * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
