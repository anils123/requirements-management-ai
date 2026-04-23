import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Trash2, Loader2, Sparkles, Filter, FileText } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useStore } from '../store'
import { RAGIndicator } from '../components/RAGIndicator'
import { CitationList } from '../components/CitationList'
import type { Citation, RAGInfo } from '../types'
import clsx from 'clsx'

const SUGGESTIONS = [
  { text: 'What documents are available?',                    icon: '📄' },
  { text: 'List all requirements from the EFI system',        icon: '📋' },
  { text: 'What are the voltage requirements in the charging system?', icon: '⚡' },
  { text: 'Show cooling system specifications',               icon: '🌡️' },
  { text: 'What emission control requirements exist?',        icon: '🌿' },
  { text: 'Find all high priority security requirements',     icon: '🔒' },
  { text: 'Who are the domain experts for performance?',      icon: '👤' },
  { text: 'What compliance standards apply to the system?',   icon: '✅' },
]

const DOC_FILTERS = [
  { label: 'All Documents',          value: '' },
  { label: 'CH Charging System',     value: 'bids/CH_Charging System.pdf' },
  { label: 'EF EFI System',          value: 'bids/EF_EFI System.pdf' },
  { label: 'EC Emission Control',    value: 'bids/EC_Emission Control Systems.pdf' },
  { label: 'CO Cooling System',      value: 'bids/CO_Cooling System.pdf' },
  { label: 'Rail Train',             value: 'bids/rail-train (1).pdf' },
]

interface Message {
  id:        string
  role:      'user' | 'assistant'
  content:   string
  timestamp: Date
  citations?: Citation[]
  ragInfo?:   RAGInfo
  intent?:    string
}

function uid() { return Math.random().toString(36).slice(2) }

export function ChatPage() {
  const { clearChat: storeClear } = useStore()
  const [messages,   setMessages]   = useState<Message[]>([])
  const [input,      setInput]      = useState('')
  const [streaming,  setStreaming]  = useState(false)
  const [streamText, setStreamText] = useState('')
  const [docFilter,  setDocFilter]  = useState('')
  const [showFilter, setShowFilter] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamText])

  const send = async (text?: string) => {
    const query = (text || input).trim()
    if (!query || streaming) return

    setInput('')
    const userMsg: Message = {
      id: uid(), role: 'user', content: query, timestamp: new Date()
    }
    setMessages(prev => [...prev, userMsg])
    setStreaming(true)
    setStreamText('')

    let fullText  = ''
    let citations: Citation[] = []
    let ragInfo:   RAGInfo | undefined
    let intent    = ''

    try {
      const resp = await fetch('/api/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          session_id: uid(),
          input_text: query,
          doc_filter: docFilter,
          top_k:      8,
        }),
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('No response body')

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue
          const data = trimmed.slice(6).trim()
          if (data === '[DONE]') continue
          try {
            const parsed = JSON.parse(data)
            if (typeof parsed.text === 'string') {
              fullText += parsed.text
              setStreamText(fullText)
            }
            if (Array.isArray(parsed.citations)) citations = parsed.citations
            if (parsed.rag_info) {
              ragInfo = parsed.rag_info
              intent  = parsed.rag_info.intent || ''
            }
          } catch { /* non-JSON line */ }
        }
      }
    } catch (err: any) {
      fullText = `**Error:** ${err?.message || 'Could not connect to backend. Make sure it is running on port 8000.'}`
    }

    setStreamText('')
    setMessages(prev => [...prev, {
      id: uid(), role: 'assistant', content: fullText,
      timestamp: new Date(), citations, ragInfo, intent,
    }])
    setStreaming(false)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const clearAll = () => { setMessages([]); storeClear() }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-600">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-brand-400" />
          <div>
            <h1 className="font-semibold text-white">AI Requirements Assistant</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Direct RAG · pgvector search · Nova Pro · {messages.length} messages
            </p>
          </div>
          <span className="badge bg-green-500/20 text-green-400 text-xs ml-2">
            <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse inline-block mr-1" />
            Live
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilter(!showFilter)}
            className={clsx('btn-ghost text-sm', docFilter && 'text-brand-400')}
          >
            <Filter size={14} />
            {docFilter ? DOC_FILTERS.find(d => d.value === docFilter)?.label : 'All Docs'}
          </button>
          <button onClick={clearAll} className="btn-ghost text-sm">
            <Trash2 size={14} /> Clear
          </button>
        </div>
      </div>

      {/* Document filter dropdown */}
      {showFilter && (
        <div className="px-6 py-2 border-b border-surface-600 bg-surface-800">
          <p className="text-xs text-gray-500 mb-2">Filter search to a specific document:</p>
          <div className="flex gap-2 flex-wrap">
            {DOC_FILTERS.map(d => (
              <button
                key={d.value}
                onClick={() => { setDocFilter(d.value); setShowFilter(false) }}
                className={clsx(
                  'px-3 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1',
                  docFilter === d.value
                    ? 'bg-brand-600 text-white'
                    : 'bg-surface-700 text-gray-400 hover:text-white'
                )}
              >
                <FileText size={10} /> {d.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-6">
            <div className="w-16 h-16 bg-brand-600/20 rounded-2xl flex items-center justify-center">
              <Bot size={32} className="text-brand-400" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white mb-2">
                Requirements Knowledge Base
              </h2>
              <p className="text-gray-400 max-w-md text-sm">
                Search across all uploaded PDFs. Ask about requirements, specifications,
                compliance, experts, or any technical content from the documents.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-2xl">
              {SUGGESTIONS.map(s => (
                <button
                  key={s.text}
                  onClick={() => send(s.text)}
                  className="text-left text-sm bg-surface-700 hover:bg-surface-600 border border-surface-500 hover:border-brand-500/50 rounded-xl p-3 text-gray-300 transition-all flex items-start gap-2"
                >
                  <span className="text-base shrink-0">{s.icon}</span>
                  <span>{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={clsx('flex gap-3 animate-fade-in',
            msg.role === 'user' && 'flex-row-reverse')}>
            <div className={clsx(
              'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
              msg.role === 'user' ? 'bg-brand-600' : 'bg-surface-600'
            )}>
              {msg.role === 'user'
                ? <User size={14} className="text-white" />
                : <Bot  size={14} className="text-brand-400" />}
            </div>
            <div className={clsx('max-w-[80%] space-y-1',
              msg.role === 'user' && 'items-end flex flex-col')}>
              <div className={clsx(
                'rounded-2xl px-4 py-3 text-sm',
                msg.role === 'user'
                  ? 'bg-brand-600 text-white rounded-tr-sm'
                  : 'bg-surface-700 text-gray-200 rounded-tl-sm'
              )}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}
                  className="prose prose-invert prose-sm max-w-none">
                  {msg.content}
                </ReactMarkdown>
              </div>
              {msg.intent && msg.intent !== 'search' && (
                <span className="text-xs text-gray-600 px-1">
                  Intent: {msg.intent.replace('_',' ')}
                </span>
              )}
              {msg.ragInfo && <RAGIndicator ragInfo={msg.ragInfo} />}
              {msg.citations && msg.citations.length > 0 && (
                <CitationList citations={msg.citations} />
              )}
              <p className="text-xs text-gray-600 px-1">
                {msg.timestamp.toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}

        {/* Streaming */}
        {streaming && (
          <div className="flex gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-lg bg-surface-600 flex items-center justify-center shrink-0">
              <Bot size={14} className="text-brand-400" />
            </div>
            <div className="max-w-[80%] bg-surface-700 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-200">
              {streamText ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}
                  className="prose prose-invert prose-sm max-w-none">
                  {streamText}
                </ReactMarkdown>
              ) : (
                <div className="flex gap-1 items-center h-5">
                  {[0,1,2].map(i => (
                    <span key={i}
                      className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${i*0.15}s` }} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-surface-600">
        {docFilter && (
          <div className="flex items-center gap-2 mb-2 text-xs text-brand-400">
            <Filter size={10} />
            Searching in: {DOC_FILTERS.find(d => d.value === docFilter)?.label}
            <button onClick={() => setDocFilter('')} className="text-gray-500 hover:text-white ml-1">✕</button>
          </div>
        )}
        <div className="flex gap-3 items-end bg-surface-700 border border-surface-500 rounded-xl p-3 focus-within:border-brand-500 transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about requirements, specifications, compliance, or any document content..."
            rows={1}
            className="flex-1 bg-transparent text-gray-100 placeholder-gray-500 resize-none focus:outline-none text-sm max-h-32"
            style={{ minHeight: '24px' }}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || streaming}
            className="btn-primary py-1.5 px-3 shrink-0"
          >
            {streaming
              ? <Loader2 size={16} className="animate-spin" />
              : <Send size={16} />}
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-2 text-center">
          Direct RAG · pgvector semantic search · Amazon Nova Pro · Grounded citations
        </p>
      </div>
    </div>
  )
}
