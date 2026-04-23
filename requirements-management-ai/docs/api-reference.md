# API Reference

Base URL: `http://localhost:8000`

---

## AI Chat

### POST /api/chat
Direct RAG search engine — semantic search + Nova Pro generation.

**Request:**
```json
{
  "session_id": "unique-session-id",
  "input_text": "What are the voltage requirements?",
  "doc_filter": "bids/CH_Charging System.pdf",
  "top_k": 8
}
```

**Response (SSE stream):**
```
data: {"text": "Based on the document..."}
data: {"text": " the voltage requirements are..."}
data: {"citations": [{"source": "CH_Charging System.pdf", "chunk_id": 3, "relevance_score": 0.87, "text_snippet": "..."}]}
data: {"rag_info": {"strategy": "semantic", "intent": "search", "doc_filter": "bids/CH_Charging System.pdf"}}
data: [DONE]
```

---

## Documents

### GET /api/documents
List all uploaded documents.

**Response:**
```json
{
  "documents": [
    {
      "id": "bids/CH_Charging System.pdf",
      "name": "CH_Charging System.pdf",
      "s3_key": "bids/CH_Charging System.pdf",
      "status": "ready",
      "chunks": 10,
      "uploaded_at": "2026-04-20 14:27:32",
      "size_bytes": 0
    }
  ],
  "total": 8
}
```

### POST /api/documents
Trigger document processing (text extraction + embeddings + KG).

**Request:**
```json
{
  "document_path": "bids/my-document.pdf",
  "document_type": "pdf"
}
```

**Response:**
```json
{
  "status": "success",
  "document_path": "bids/my-document.pdf",
  "chunks_created": 15,
  "text_length": 45230,
  "pages_approx": 15,
  "entities_found": 42,
  "graph_nodes": 180,
  "graph_edges": 95
}
```

### POST /api/documents/upload
Upload a file to S3.

**Request:** `multipart/form-data` with `file` field

**Response:**
```json
{
  "status": "uploaded",
  "s3_key": "bids/my-document.pdf",
  "size_bytes": 1048576
}
```

---

## Requirements

### GET /api/requirements
Fetch all requirements from Aurora.

**Response:**
```json
{
  "requirements": [
    {
      "requirement_id": "REQ-CH_CHARGING--0003",
      "document_id": "CH_Charging System",
      "type": "functional",
      "category": "general",
      "priority": "high",
      "description": "The charging system shall operate at a maximum voltage of 3...",
      "domain": "performance",
      "status": "extracted",
      "confidence_score": 0.9,
      "acceptance_criteria": ["criterion1", "criterion2"]
    }
  ],
  "total": 140
}
```

### POST /api/requirements
Extract requirements from a processed document.

**Request:**
```json
{
  "document_id": "CH_Charging System",
  "extraction_criteria": {
    "types": ["functional", "non-functional"],
    "priorities": ["high", "medium", "low"]
  }
}
```

**Response:**
```json
{
  "status": "success",
  "document_id": "CH_Charging System",
  "requirements_extracted": 57,
  "graph_nodes_created": 57,
  "requirements": [...]
}
```

---

## Search

### POST /api/search
Semantic search across all PDFs.

**Request:**
```json
{
  "query": "voltage requirements alternator",
  "document_filter": "bids/CH_Charging System.pdf",
  "top_k": 8
}
```

**Response:**
```json
{
  "answer": "According to CH_Charging System.pdf...",
  "citations": [...],
  "intent": "search",
  "sources": [...],
  "rag_info": {
    "strategy": "semantic",
    "intent": "search",
    "doc_filter": "bids/CH_Charging System.pdf"
  }
}
```

---

## Experts

### GET /api/experts
List all domain experts.

**Response:**
```json
{
  "experts": [
    {
      "expert_id": "EXP-001",
      "name": "Security Expert",
      "department": "Cybersecurity",
      "skills": ["OAuth2", "PKI", "SIEM"],
      "specializations": ["security", "compliance"],
      "current_workload": 2,
      "max_workload": 10,
      "availability_status": "available"
    }
  ]
}
```

### POST /api/experts
Assign experts to requirements using graph traversal.

**Request:**
```json
{
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "description": "OAuth2 authentication",
      "domain": "security"
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "assignments": [
    {
      "requirement_id": "REQ-001",
      "assigned_experts": [
        {
          "expert_id": "EXP-001",
          "name": "Security Expert",
          "combined_score": 0.87
        }
      ]
    }
  ]
}
```

---

## Compliance

### POST /api/compliance
Generate compliance suggestions using past requirements.

**Request:**
```json
{
  "requirement_id": "REQ-001",
  "requirement_text": "The system shall implement OAuth2 authentication",
  "domain": "security"
}
```

**Response:**
```json
{
  "status": "success",
  "requirement_id": "REQ-001",
  "compliance_text": "For OAuth2 authentication, consider ISO 27001...",
  "citations": [...],
  "confidence_score": 0.82,
  "domain": "security",
  "graph_context_used": 3
}
```

---

## Graph (Neo4j)

### POST /api/graph
Execute Neo4j graph operations.

**Actions:**

#### semantic_search
```json
{"action": "semantic_search", "query": "voltage requirements", "label": "Requirement", "top_k": 8}
```

#### traverse
```json
{"action": "traverse", "label": "Document", "key": "bids/CH_Charging System.pdf", "direction": "out", "limit": 20}
```

#### find_experts
```json
{"action": "find_experts", "domain": "security", "limit": 5}
```

#### past_requirements
```json
{"action": "past_requirements", "domain": "performance", "limit": 10}
```

#### graph_stats
```json
{"action": "graph_stats"}
```
Response:
```json
{
  "nodes": {"Document": 8, "Requirement": 140, "Expert": 6, "Domain": 22},
  "edges": {"CONTAINS": 140, "SPECIALIZES_IN": 24, "ASSIGNED_TO": 12},
  "total_nodes": 176,
  "total_edges": 176
}
```

#### cypher_query
```json
{
  "action": "cypher_query",
  "cypher": "MATCH (r:Requirement {domain: 'security'}) RETURN r.id, r.description LIMIT 10"
}
```

#### shortest_path
```json
{
  "action": "shortest_path",
  "from_label": "Expert", "from_id": "EXP-001",
  "to_label": "Document", "to_id": "bids/CH_Charging System.pdf",
  "max_depth": 4
}
```

---

## Knowledge Graph (Aurora)

### GET /api/knowledge-graph
Get KG nodes and edges from Aurora.

**Query params:** `document_id` (optional), `limit` (default 100)

**Response:**
```json
{
  "nodes": [
    {"entity_id": "abc123", "entity_text": "Phillips", "entity_type": "ORGANIZATION", "score": 1.0}
  ],
  "edges": [],
  "node_count": 42,
  "edge_count": 0
}
```

---

## Statistics

### GET /api/stats
System statistics.

**Response:**
```json
{
  "total_documents": 8,
  "total_requirements": 140,
  "total_experts": 6,
  "pending_reviews": 95,
  "avg_confidence": 0.87,
  "documents_today": 2,
  "api_calls_today": 284,
  "cache_hit_rate": 0.62
}
```

---

## Health

### GET /api/health
Health check.

**Response:**
```json
{
  "status": "ok",
  "agent_id": "RKKSDKKZ08",
  "alias_id": "DSSWEULJAJ",
  "bucket": "requirementsmanagementstack-documentbucketae41e5a9-v7g01d4l2urm",
  "region": "us-east-1"
}
```
