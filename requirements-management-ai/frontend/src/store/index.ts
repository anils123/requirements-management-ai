import { create } from 'zustand'
import type { Message, Document, Requirement, Expert, Workspace } from '../types'
import { v4 as uuid } from 'crypto'

function uid() { return Math.random().toString(36).slice(2) }

interface AppState {
  // Chat
  messages:       Message[]
  sessionId:      string
  isStreaming:    boolean
  addMessage:     (msg: Omit<Message, 'id' | 'timestamp'>) => void
  setStreaming:   (v: boolean) => void
  clearChat:      () => void

  // Documents
  documents:      Document[]
  addDocument:    (doc: Document) => void
  updateDocument: (id: string, patch: Partial<Document>) => void

  // Requirements
  requirements:   Requirement[]
  setRequirements:(reqs: Requirement[]) => void
  updateRequirement: (id: string, patch: Partial<Requirement>) => void

  // Experts
  experts:        Expert[]
  setExperts:     (experts: Expert[]) => void

  // Workspaces
  workspaces:     Workspace[]
  activeWorkspace: string | null
  setActiveWorkspace: (id: string) => void

  // UI
  sidebarOpen:    boolean
  setSidebarOpen: (v: boolean) => void
  activeTab:      string
  setActiveTab:   (tab: string) => void
}

export const useStore = create<AppState>((set) => ({
  // Chat
  messages:    [],
  sessionId:   uid(),
  isStreaming: false,
  addMessage:  (msg) => set((s) => ({
    messages: [...s.messages, { ...msg, id: uid(), timestamp: new Date() }],
  })),
  setStreaming: (v) => set({ isStreaming: v }),
  clearChat:   () => set({ messages: [], sessionId: uid() }),

  // Documents
  documents:      [],
  addDocument:    (doc) => set((s) => ({ documents: [doc, ...s.documents] })),
  updateDocument: (id, patch) => set((s) => ({
    documents: s.documents.map((d) => d.id === id ? { ...d, ...patch } : d),
  })),

  // Requirements
  requirements:   [],
  setRequirements: (reqs) => set({ requirements: reqs }),
  updateRequirement: (id, patch) => set((s) => ({
    requirements: s.requirements.map((r) =>
      r.requirement_id === id ? { ...r, ...patch } : r
    ),
  })),

  // Experts
  experts:    [],
  setExperts: (experts) => set({ experts }),

  // Workspaces
  workspaces: [
    { id: 'ws-1', name: 'Bid 2024-Q4', description: 'Q4 infrastructure bid', documents: 3, requirements: 47, created_at: '2024-10-01', status: 'active' },
    { id: 'ws-2', name: 'Project Alpha', description: 'Cloud migration project', documents: 7, requirements: 100, created_at: '2024-09-15', status: 'active' },
  ],
  activeWorkspace: 'ws-1',
  setActiveWorkspace: (id) => set({ activeWorkspace: id }),

  // UI
  sidebarOpen: true,
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  activeTab:   'chat',
  setActiveTab: (tab) => set({ activeTab: tab }),
}))
