import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Trash2, Loader2, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useStore } from '../store'
import { invokeAgent } from '../api/client'
import { RAGIndicator } from '../components/RAGIndicator'
import { CitationList } from '../components/CitationList'
import type { Citation, RAGInfo } from '../types'
import clsx from 'clsx'

const SUGGESTIONS = [
  'Process the latest bid document and extract all requirements',
  'Which requirements need security expert review?',
  'Generate compliance suggestions for REQ-001',
  'Show me all high-priority functional requirements',
]

export function ChatPage() {
  const { messages, sessionId, isStreaming, addMessage, setStreaming, clearChat } = useStore()
  const [input, setInput]       = useState('')
  const [streamText, setStream] = useState('')
  const bottomRef               = useRef<HTMLDivElement>(null)
  const inputRef                = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamText])

  const send = async (text?: string) => {
    const query = (text || input).trim()
    if (!query || isStreaming) return

    setInput('')
    addMessage({ role: 'user', content: query })
    setStreaming(true)
    setStream('')

    let fullText  = ''
    let citations: Citation[] = []
    let ragInfo:   RAGInfo | undefined

    try {
      const result = await invokeAgent(sessionId, query, (chunk) => {
        fullText += chunk
        setStream(fullText)
      })
      citations = result.citations
      ragInfo   = result.ragInfo
    } catch (err: any) {
      console.error('Agent error:', err)
      fullText = `**Error:** ${err?.message || 'Could not connect to agent. Make sure the backend is running on port 8000.'}`
    }

    setStream('')
    addMessage({ role: 'assistant', content: fullText, citations, ragInfo })
    setStreaming(false)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-600">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-brand-400" />
          <h1 className="font-semibold text-white">AI Requirements Assistant</h1>
          <span className="badge bg-green-500/20 text-green-400 text-xs">
            <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
            Live
          </span>
        </div>
        <button onClick={clearChat} className="btn-ghost text-sm">
          <Trash2 size={14} /> Clear
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-6">
            <div className="w-16 h-16 bg-brand-600/20 rounded-2xl flex items-center justify-center">
              <Bot size={32} className="text-brand-400" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white mb-2">Requirements Management AI</h2>
              <p className="text-gray-400 max-w-md">
                Powered by Bedrock AgentCore with Hybrid RAG, CRAG, HyDE, and grounded citations.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-sm bg-surface-700 hover:bg-surface-600 border border-surface-500 hover:border-brand-500/50 rounded-xl p-3 text-gray-300 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={clsx('flex gap-3 animate-fade-in', msg.role === 'user' && 'flex-row-reverse')}>
            <div className={clsx(
              'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
              msg.role === 'user' ? 'bg-brand-600' : 'bg-surface-600'
            )}>
              {msg.role === 'user' ? <User size={14} className="text-white" /> : <Bot size={14} className="text-brand-400" />}
            </div>
            <div className={clsx('max-w-[75%] space-y-1', msg.role === 'user' && 'items-end flex flex-col')}>
              <div className={clsx(
                'rounded-2xl px-4 py-3 text-sm',
                msg.role === 'user'
                  ? 'bg-brand-600 text-white rounded-tr-sm'
                  : 'bg-surface-700 text-gray-200 rounded-tl-sm'
              )}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-invert prose-sm max-w-none">
                  {msg.content}
                </ReactMarkdown>
              </div>
              {msg.ragInfo && <RAGIndicator ragInfo={msg.ragInfo} />}
              {msg.citations && msg.citations.length > 0 && <CitationList citations={msg.citations} />}
              <p className="text-xs text-gray-600 px-1">
                {msg.timestamp.toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}

        {/* Streaming message */}
        {isStreaming && (
          <div className="flex gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-lg bg-surface-600 flex items-center justify-center shrink-0">
              <Bot size={14} className="text-brand-400" />
            </div>
            <div className="max-w-[75%] bg-surface-700 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-gray-200">
              {streamText ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-invert prose-sm max-w-none">
                  {streamText}
                </ReactMarkdown>
              ) : (
                <div className="flex gap-1 items-center h-5">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-bounce"
                          style={{ animationDelay: `${i * 0.15}s` }} />
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
        <div className="flex gap-3 items-end bg-surface-700 border border-surface-500 rounded-xl p-3 focus-within:border-brand-500 transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about requirements, compliance, or upload a bid document..."
            rows={1}
            className="flex-1 bg-transparent text-gray-100 placeholder-gray-500 resize-none focus:outline-none text-sm max-h-32"
            style={{ minHeight: '24px' }}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || isStreaming}
            className="btn-primary py-1.5 px-3 shrink-0"
          >
            {isStreaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-2 text-center">
          Responses grounded with citations · Hallucination detection enabled
        </p>
      </div>
    </div>
  )
}
