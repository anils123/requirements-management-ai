import { useState } from 'react'
import { FileText, CheckCircle, Loader2, AlertCircle, Layers, ArrowRight } from 'lucide-react'
import { DocumentUpload } from '../components/DocumentUpload'
import { useStore } from '../store'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

const STATUS_CONFIG = {
  uploading:  { icon: Loader2,     color: 'text-blue-400',   label: 'Uploading',   spin: true  },
  processing: { icon: Loader2,     color: 'text-yellow-400', label: 'Processing',  spin: true  },
  ready:      { icon: CheckCircle, color: 'text-green-400',  label: 'Ready',       spin: false },
  error:      { icon: AlertCircle, color: 'text-red-400',    label: 'Error',       spin: false },
}

export function DocumentsPage() {
  const { documents, setRequirements, setActiveTab } = useStore()
  const [extracting, setExtracting] = useState<string | null>(null)
  const [extractError, setExtractError] = useState<Record<string, string>>({})

  const handleExtract = async (docId: string, docName: string) => {
    setExtracting(docId)
    setExtractError((prev) => ({ ...prev, [docId]: '' }))

    try {
      // document_id = s3_key with bids/ prefix stripped and extension removed
      // Must match what the Lambda stores: LIKE %document_id% against document_path
      // e.g. s3_key='bids/CH_Charging System.pdf' -> document_id='CH_Charging System'
      const documentId = docId
        .replace(/^bids\//, '')   // strip bids/ prefix
        .replace(/\.[^.]+$/, '')  // strip file extension

      const resp = await fetch('/api/requirements', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          document_id:         documentId,
          extraction_criteria: {
            types:      ['functional', 'non-functional'],
            priorities: ['high', 'medium', 'low'],
          },
        }),
      })

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)
      }

      const data = await resp.json()
      const reqs = data.requirements || []

      if (reqs.length === 0) {
        throw new Error('No requirements found. Make sure the document was processed first.')
      }

      setRequirements(reqs)
      // Navigate to Requirements tab automatically
      setActiveTab('requirements')

    } catch (err: any) {
      console.error('Extract error:', err)
      setExtractError((prev) => ({
        ...prev,
        [docId]: err?.message || 'Extraction failed',
      }))
    } finally {
      setExtracting(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-surface-600">
        <h1 className="font-semibold text-white">Documents</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Upload bid documents — PDF, TXT, or DOC — for automated requirements extraction
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <DocumentUpload />

        {documents.length > 0 && (
          <div>
            <h2 className="text-sm font-medium text-gray-400 mb-3 uppercase tracking-wider">
              Uploaded Documents
            </h2>
            <div className="space-y-2">
              {documents.map((doc) => {
                const cfg        = STATUS_CONFIG[doc.status]
                const Icon       = cfg.icon
                const isExtracting = extracting === doc.id
                const error      = extractError[doc.id]

                return (
                  <div key={doc.id} className="card space-y-2">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-surface-600 rounded-lg flex items-center justify-center shrink-0">
                        <FileText size={18} className="text-brand-400" />
                      </div>

                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-200 truncate">
                          {doc.name}
                        </p>
                        <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                          <span>{(doc.size_bytes / 1024 / 1024).toFixed(1)} MB</span>
                          {doc.chunks > 0 && (
                            <span className="text-brand-400">{doc.chunks} chunks indexed</span>
                          )}
                          {doc.pages && <span>{doc.pages} pages</span>}
                          <span>
                            {formatDistanceToNow(new Date(doc.uploaded_at), { addSuffix: true })}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        {/* Status badge */}
                        <div className={clsx('flex items-center gap-1.5 text-xs', cfg.color)}>
                          <Icon size={14} className={cfg.spin ? 'animate-spin' : ''} />
                          {cfg.label}
                        </div>

                        {/* Extract button — only shown when ready */}
                        {doc.status === 'ready' && (
                          <button
                            onClick={() => handleExtract(doc.id, doc.name)}
                            disabled={isExtracting}
                            className="btn-primary text-xs py-1.5 px-3 min-w-[110px] justify-center"
                          >
                            {isExtracting ? (
                              <>
                                <Loader2 size={12} className="animate-spin" />
                                Extracting...
                              </>
                            ) : (
                              <>
                                <Layers size={12} />
                                Extract Reqs
                                <ArrowRight size={10} />
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Error message */}
                    {error && (
                      <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-xs text-red-400">
                        <AlertCircle size={12} className="mt-0.5 shrink-0" />
                        {error}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {documents.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <FileText size={48} className="mx-auto mb-4 opacity-20" />
            <p className="font-medium">No documents uploaded yet</p>
            <p className="text-sm mt-1">
              Drag & drop a bid PDF or TXT file above to get started
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
