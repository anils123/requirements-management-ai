export interface Message {
  id:         string
  role:       'user' | 'assistant'
  content:    string
  timestamp:  Date
  citations?: Citation[]
  ragInfo?:   RAGInfo
}

export interface Citation {
  source:          string
  chunk_id:        number
  relevance_score: number
  text_snippet?:   string
}

export interface RAGInfo {
  strategy:          'hybrid' | 'vector_only' | 'text_only' | 'decomposed'
  corrective_used:   boolean
  hyde_used:         boolean
  reranked:          boolean
  hallucination_check: boolean
  sub_queries?:      string[]
}

export interface Document {
  id:           string
  name:         string
  s3_key:       string
  status:       'uploading' | 'processing' | 'ready' | 'error'
  chunks:       number
  pages?:       number
  uploaded_at:  string
  size_bytes:   number
}

export interface Requirement {
  requirement_id:      string
  document_id:         string
  type:                'functional' | 'non-functional'
  category:            string
  priority:            'high' | 'medium' | 'low'
  description:         string
  domain:              string
  status:              'extracted' | 'reviewed' | 'approved' | 'rejected'
  confidence_score:    number
  acceptance_criteria: string[]
  assigned_experts?:   ExpertAssignment[]
  compliance?:         ComplianceSuggestion
}

export interface Expert {
  expert_id:           string
  name:                string
  email:               string
  department:          string
  skills:              string[]
  specializations:     string[]
  current_workload:    number
  max_workload:        number
  availability_status: 'available' | 'busy' | 'unavailable'
}

export interface ExpertAssignment {
  expert_id:       string
  name:            string
  department:      string
  combined_score:  number
  similarity_score: number
  domain_score:    number
}

export interface ComplianceSuggestion {
  compliance_text:  string
  citations:        Citation[]
  confidence_score: number
  domain:           string
}

export interface SystemStats {
  total_documents:    number
  total_requirements: number
  total_experts:      number
  pending_reviews:    number
  avg_confidence:     number
  documents_today:    number
  api_calls_today:    number
  cache_hit_rate:     number
}

export interface Workspace {
  id:          string
  name:        string
  description: string
  documents:   number
  requirements: number
  created_at:  string
  status:      'active' | 'archived'
}
