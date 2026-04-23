import axios from 'axios'
import type { Document, Requirement, Expert, SystemStats } from '../types'

const API_BASE = '/api'

// Agent IDs — fetched dynamically from backend health endpoint
let AGENT_ID = 'RKKSDKKZ08'
let ALIAS_ID = 'DSSWEULJAJ'

// Fetch current IDs from backend on startup (handles alias rotations)
fetch(`${API_BASE}/health`)
  .then(r => r.json())
  .then(data => {
    if (data.agent_id)    AGENT_ID = data.agent_id
    if (data.alias_id)    ALIAS_ID = data.alias_id
  })
  .catch(() => {}) // keep hardcoded fallback if backend unreachable
const BUCKET_NAME = 'requirementsmanagementstack-documentbucketae41e5a9-v7g01d4l2urm'
const REGION      = 'us-east-1'

const http = axios.create({ baseURL: API_BASE, timeout: 30000 })

// ── Documents ─────────────────────────────────────────────────────────────────
export const uploadDocument = async (file: File): Promise<Document> => {
  const form = new FormData()
  form.append('file', file)
  form.append('document_path', `bids/${file.name}`)
  const { data } = await http.post('/documents', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const processDocument = async (documentPath: string) => {
  const { data } = await http.post('/documents', {
    document_path: documentPath,
    document_type: 'pdf',
  })
  return data
}

// ── Requirements ──────────────────────────────────────────────────────────────
export const extractRequirements = async (documentId: string): Promise<Requirement[]> => {
  const { data } = await http.post('/requirements', {
    document_id: documentId,
    extraction_criteria: {
      types:      ['functional', 'non-functional'],
      priorities: ['high', 'medium', 'low'],
    },
  })
  return data.requirements || []
}

export const getRequirements = async (): Promise<Requirement[]> => {
  try {
    const { data } = await http.get('/requirements')
    return data.requirements || []
  } catch {
    return MOCK_REQUIREMENTS
  }
}

// ── Experts ───────────────────────────────────────────────────────────────────
export const getExperts = async (): Promise<Expert[]> => {
  try {
    const { data } = await http.get('/experts')
    return data.experts || []
  } catch {
    return MOCK_EXPERTS
  }
}

export const assignExperts = async (requirements: Requirement[]) => {
  const { data } = await http.post('/experts', { requirements })
  return data
}

// ── Compliance ────────────────────────────────────────────────────────────────
export const checkCompliance = async (req: Requirement) => {
  const { data } = await http.post('/compliance', {
    requirement_id:   req.requirement_id,
    requirement_text: req.description,
    domain:           req.domain,
  })
  return data
}

// ── Stats ─────────────────────────────────────────────────────────────────────
export const getStats = async (): Promise<SystemStats> => {
  try {
    const { data } = await http.get('/stats')
    return data
  } catch {
    return MOCK_STATS
  }
}

// ── Bedrock Agent Chat ────────────────────────────────────────────────────────
export const invokeAgent = async (
  sessionId: string,
  inputText: string,
  onChunk: (text: string) => void
): Promise<{ citations: import('../types').Citation[]; ragInfo: import('../types').RAGInfo }> => {

  const citations: import('../types').Citation[] = []
  const ragInfo: import('../types').RAGInfo = {
    strategy: 'hybrid', corrective_used: false,
    hyde_used: true, reranked: true, hallucination_check: true,
  }

  const response = await fetch(`${API_BASE}/agent/invoke`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ session_id: sessionId, input_text: inputText }),
  })

  if (!response.ok) {
    const errText = await response.text().catch(() => `HTTP ${response.status}`)
    throw new Error(errText)
  }

  if (!response.body) {
    throw new Error('No response body from server')
  }

  const reader  = response.body.getReader()
  const decoder = new TextDecoder()
  let   buffer  = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Process complete SSE lines from buffer
    const lines = buffer.split('\n')
    // Keep last incomplete line in buffer
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data: ')) continue

      const data = trimmed.slice(6).trim()
      if (data === '[DONE]') continue

      try {
        const parsed = JSON.parse(data)
        if (typeof parsed.text === 'string')      onChunk(parsed.text)
        if (Array.isArray(parsed.citations))      citations.push(...parsed.citations)
        if (parsed.rag_info)                      Object.assign(ragInfo, parsed.rag_info)
      } catch {
        // Non-JSON data line — treat as plain text chunk
        if (data && data !== '[DONE]') onChunk(data)
      }
    }
  }

  return { citations, ragInfo }
}

// ── Mock data (fallback when API is unavailable) ──────────────────────────────
const MOCK_REQUIREMENTS: Requirement[] = [
  {
    requirement_id:   'REQ-001',
    document_id:      'doc-001',
    type:             'functional',
    category:         'security',
    priority:         'high',
    description:      'The system shall implement OAuth2 authentication with MFA support for all user accounts.',
    domain:           'security',
    status:           'extracted',
    confidence_score: 0.94,
    acceptance_criteria: ['OAuth2 flow implemented', 'MFA enforced for admin users'],
  },
  {
    requirement_id:   'REQ-002',
    document_id:      'doc-001',
    type:             'non-functional',
    category:         'performance',
    priority:         'high',
    description:      'API response time shall not exceed 200ms at the 95th percentile under normal load.',
    domain:           'performance',
    status:           'reviewed',
    confidence_score: 0.89,
    acceptance_criteria: ['P95 latency < 200ms', 'Load test with 1000 concurrent users'],
  },
  {
    requirement_id:   'REQ-003',
    document_id:      'doc-001',
    type:             'functional',
    category:         'integration',
    priority:         'medium',
    description:      'The system shall provide REST API endpoints conforming to OpenAPI 3.0 specification.',
    domain:           'integration',
    status:           'approved',
    confidence_score: 0.97,
    acceptance_criteria: ['OpenAPI spec published', 'All endpoints documented'],
  },
]

const MOCK_EXPERTS: Expert[] = [
  {
    expert_id:           'EXP-001',
    name:                'Security Expert',
    email:               'security@company.com',
    department:          'Cybersecurity',
    skills:              ['OAuth2', 'PKI', 'SIEM', 'Zero Trust'],
    specializations:     ['security', 'compliance', 'authentication'],
    current_workload:    2,
    max_workload:        10,
    availability_status: 'available',
  },
  {
    expert_id:           'EXP-002',
    name:                'Platform Engineer',
    email:               'platform@company.com',
    department:          'Platform Engineering',
    skills:              ['AWS', 'Kubernetes', 'Terraform'],
    specializations:     ['infrastructure', 'performance', 'scalability'],
    current_workload:    5,
    max_workload:        10,
    availability_status: 'available',
  },
]

const MOCK_STATS: SystemStats = {
  total_documents:    12,
  total_requirements: 147,
  total_experts:      6,
  pending_reviews:    23,
  avg_confidence:     0.87,
  documents_today:    3,
  api_calls_today:    284,
  cache_hit_rate:     0.62,
}
