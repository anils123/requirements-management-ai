# Requirements Management AI — Architecture & Data Flow

## System Overview

The Requirements Management AI is an agentic system that automatically extracts, structures, and manages requirements from bid documents (PDFs). It combines a direct RAG (Retrieval-Augmented Generation) pipeline with a Neo4j knowledge graph and AWS Bedrock AgentCore for intelligent orchestration.

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PRESENTATION LAYER                                  │
│                                                                               │
│   React + TypeScript + Tailwind CSS  (localhost:3000)                        │
│   ┌──────────┐ ┌───────────┐ ┌──────────────┐ ┌────────┐ ┌───────────────┐ │
│   │ AI Chat  │ │ Documents │ │ Requirements │ │Experts │ │ Knowledge     │ │
│   │ (RAG)    │ │ (Upload)  │ │ (Extract)    │ │(Graph) │ │ Graph (Neo4j) │ │
│   └──────────┘ └───────────┘ └──────────────┘ └────────┘ └───────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │ HTTP/SSE
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API LAYER (FastAPI)                                 │
│                                                                               │
│   backend/main.py  (localhost:8000)                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  /api/chat    /api/documents    /api/requirements    /api/search    │   │
│   │  /api/experts /api/compliance   /api/graph           /api/stats     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                          │
│   backend/ai_assistant.py  ←───────┘                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Intent Classifier → Route → pgvector Search → Nova Pro → Answer   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENTIC ORCHESTRATION LAYER                           │
│                                                                               │
│   AWS Bedrock AgentCore  (Agent ID: RKKSDKKZ08)                             │
│   Foundation Model: Amazon Nova Micro                                        │
│                                                                               │
│   Action Groups (Lambda Functions):                                          │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│   │ DocumentProcessor│  │RequirementsExtract│  │  ExpertMatcher   │         │
│   │ (PDF→chunks→KG)  │  │ (chunks→Nova→reqs)│  │ (graph traversal)│         │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘         │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│   │ComplianceChecker │  │  DocumentSearch  │  │   GraphAgent     │         │
│   │ (past reqs+Nova) │  │ (pgvector search)│  │ (Neo4j Cypher)   │         │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                          │
│                                                                               │
│  ┌─────────────────────────┐    ┌──────────────────────────────────────┐    │
│  │   Amazon S3             │    │   Aurora PostgreSQL (pgvector)        │    │
│  │   bids/*.pdf            │    │   ┌──────────────────────────────┐   │    │
│  │   bids/*.txt            │    │   │ document_chunks (embeddings) │   │    │
│  └─────────────────────────┘    │   │ requirements                 │   │    │
│                                  │   │ domain_experts               │   │    │
│  ┌─────────────────────────┐    │   │ compliance_suggestions        │   │    │
│  │   Neo4j AuraDB          │    │   │ kg_nodes / kg_edges           │   │    │
│  │   (:Document)           │    │   └──────────────────────────────┘   │    │
│  │   (:Requirement)        │    └──────────────────────────────────────┘    │
│  │   (:Expert)             │                                                  │
│  │   (:Domain)             │    ┌──────────────────────────────────────┐    │
│  │   (:Entity)             │    │   AWS Secrets Manager                │    │
│  └─────────────────────────┘    │   DB credentials, API keys           │    │
│                                  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI/ML SERVICES LAYER                                  │
│                                                                               │
│  ┌──────────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ Amazon Nova Pro      │  │ Titan Embed V2   │  │ Amazon Textract      │  │
│  │ (answer generation)  │  │ (1024-dim embed) │  │ (PDF text extract)   │  │
│  └──────────────────────┘  └──────────────────┘  └──────────────────────┘  │
│  ┌──────────────────────┐  ┌──────────────────┐                             │
│  │ Amazon Nova Micro    │  │ Amazon Comprehend│                             │
│  │ (req extraction)     │  │ (NER entities)   │                             │
│  └──────────────────────┘  └──────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow 1 — Document Upload & Processing

```
User uploads PDF
      │
      ▼
[Frontend: DocumentUpload.tsx]
  POST /api/documents/upload (multipart)
      │
      ▼
[Backend: main.py]
  S3.put_object → s3://bucket/bids/filename.pdf
      │
      ▼
  POST /api/documents {document_path, document_type}
      │
      ▼
[Lambda: DocumentProcessor]
  1. pypdf.PdfReader → extract text (all pages)
     └─ Fallback: Amazon Textract async job
  2. chunk_text(size=400, overlap=50) → N chunks
  3. For each chunk:
     └─ Titan Embed V2 → 1024-dim vector
     └─ Aurora INSERT document_chunks (path, chunk_id, text, embedding)
  4. Amazon Comprehend → extract entities (PERSON, ORG, QUANTITY, etc.)
  5. Amazon Nova Micro → extract entity relations
  6. Neo4j MERGE (:Document {id, name, path})
  7. Neo4j MERGE (:Entity) nodes + [:MENTIONS] edges
  8. Aurora INSERT document_registry (path, chunks, status=completed)
      │
      ▼
[Frontend: DocumentsPage]
  Shows document with chunk count + "Extract Reqs" button
```

---

## Data Flow 2 — Requirements Extraction

```
User clicks "Extract Reqs" on a document
      │
      ▼
[Frontend: DocumentsPage.handleExtract]
  POST /api/requirements {document_id}
      │
      ▼
[Lambda: RequirementsExtractor]
  1. SELECT chunks FROM document_chunks WHERE path LIKE %document_id%
  2. Neo4j MATCH (:Document)-[:MENTIONS]->(:Entity) → KG context
  3. For each batch of 5 chunks:
     └─ Amazon Nova Micro prompt:
        "Extract requirements from text + KG context"
        → JSON: [{id, type, priority, description, acceptance_criteria}]
  4. Deduplicate by description
  5. Assign document-scoped IDs: REQ-{DOCNAME}-{0000}
  6. Aurora DELETE existing reqs for document (fresh extraction)
  7. Aurora INSERT requirements (req_id, doc_id, type, priority, domain, ...)
  8. Titan Embed V2 → embed each requirement description
  9. Neo4j MERGE (:Requirement) + [:EXTRACTED_FROM] + [:CONTAINS] edges
  10. Neo4j SIMILAR_TO edges for requirements with similarity > 0.75
      │
      ▼
[Frontend: RequirementsPage]
  Shows all requirements with document filter tabs
  Approve / Reject / Assign Experts / Check Compliance actions
```

---

## Data Flow 3 — AI Chat (Direct RAG Pipeline)

```
User types question in AI Chat
      │
      ▼
[Frontend: ChatPage.send()]
  POST /api/chat {session_id, input_text, doc_filter, top_k}
      │
      ▼
[Backend: ai_assistant.py]

  Step 1: Intent Classification
  ┌─────────────────────────────────────────────────────┐
  │ _classify_intent(query) → (intent, doc_filter)      │
  │                                                       │
  │ "list documents"    → intent=list_docs               │
  │ "list requirements" → intent=list_reqs               │
  │ "who is expert"     → intent=expert_query            │
  │ "compliance"        → intent=compliance_query        │
  │ anything else       → intent=search                  │
  │                                                       │
  │ _detect_doc_filter(query):                           │
  │ "charging" → bids/CH_Charging System.pdf             │
  │ "efi/fuel" → bids/EF_EFI System.pdf                 │
  │ "emission"  → bids/EC_Emission Control Systems.pdf   │
  └─────────────────────────────────────────────────────┘
      │
      ▼
  Step 2: Retrieval (based on intent)
  ┌─────────────────────────────────────────────────────┐
  │ list_docs:    SELECT DISTINCT document_path          │
  │ list_reqs:    SELECT * FROM requirements + search    │
  │ expert_query: SELECT * FROM domain_experts + search  │
  │ compliance:   search + SELECT compliance domain reqs │
  │ search:       pgvector semantic search               │
  │                                                       │
  │ _semantic_search(query, doc_filter, top_k=8):        │
  │   Titan Embed V2 → 1024-dim query vector             │
  │   SQL: SELECT ... (1-(embedding<=>emb)) AS similarity│
  │        FROM document_chunks ORDER BY similarity DESC │
  │   Deduplicate by (document_path, chunk_id)           │
  └─────────────────────────────────────────────────────┘
      │
      ▼
  Step 3: Answer Generation
  ┌─────────────────────────────────────────────────────┐
  │ Amazon Nova Pro:                                      │
  │   System: "You are Requirements Management AI..."    │
  │   Context: top-6 chunks with document + score        │
  │   Question: user query                               │
  │   → Grounded answer with citations                   │
  └─────────────────────────────────────────────────────┘
      │
      ▼
  Step 4: Stream Response (SSE)
  ┌─────────────────────────────────────────────────────┐
  │ yield "data: {text: chunk}\n\n"  (word by word)     │
  │ yield "data: {citations: [...]}\n\n"                 │
  │ yield "data: {rag_info: {...}}\n\n"                  │
  │ yield "data: [DONE]\n\n"                             │
  └─────────────────────────────────────────────────────┘
      │
      ▼
[Frontend: ChatPage SSE reader]
  Accumulates text chunks → renders markdown
  Shows RAG indicators (strategy, intent)
  Shows citations with document + relevance score
```

---

## Data Flow 4 — Expert Assignment (Graph Traversal)

```
User clicks "Assign Experts" on a requirement
      │
      ▼
[Frontend: RequirementsPage.handleAssign]
  POST /api/experts {requirements: [...]}
      │
      ▼
[Lambda: ExpertMatcher]

  Strategy 1 — Domain Graph Traversal:
    Neo4j: MATCH (e:Expert)-[:SPECIALIZES_IN]->(d:Domain {name: domain})
    → experts who specialize in requirement domain

  Strategy 2 — Semantic Similarity:
    Titan Embed V2 → embed requirement description
    Neo4j: semantic_search_nodes(emb, label="Expert", top_k=10)
    → experts with similar skill embeddings

  Strategy 3 — Past Assignment History:
    Neo4j: MATCH (e:Expert)-[:ASSIGNED_TO]->(r:Requirement)
           WHERE r similar to current requirement
    → experts who handled similar past requirements

  Merge scores: domain(0.4) + semantic(0.5) + history(0.3)
  → Top 2 experts with combined score

  Neo4j: MERGE (e:Expert)-[:ASSIGNED_TO {score}]->(r:Requirement)
      │
      ▼
[Frontend] Shows assigned experts with scores
```

---

## Data Flow 5 — Knowledge Graph Operations

```
User queries Knowledge Graph page
      │
      ▼
[Frontend: GraphPage]
  POST /api/graph {action: "graph_stats" | "semantic_search" | "traverse" | ...}
      │
      ▼
[Backend: main.py → GraphAgent Lambda]

  Actions available:
  ┌────────────────────────────────────────────────────────┐
  │ semantic_search  → Titan Embed → Neo4j vector search   │
  │ traverse         → Neo4j MATCH (n)-[r]->(m)            │
  │ neighbourhood    → 2-hop graph context                  │
  │ find_experts     → MATCH Expert-SPECIALIZES_IN->Domain  │
  │ past_requirements→ MATCH Requirement WHERE domain=X     │
  │ store_requirement→ MERGE nodes + relationships          │
  │ assign_expert    → MERGE ASSIGNED_TO edge               │
  │ graph_stats      → COUNT nodes/edges by label/type      │
  │ cypher_query     → Raw Cypher execution                 │
  │ shortest_path    → shortestPath((a)-[*..4]-(b))        │
  └────────────────────────────────────────────────────────┘
      │
      ▼
[Neo4j AuraDB] executes Cypher → returns results
      │
      ▼
[Frontend: GraphPage] displays nodes, edges, stats
```

---

## Agentic Process Description

### What Makes This "Agentic"

The system uses **Bedrock AgentCore** as an orchestrator that:

1. **Reasons** about which tool to call based on the user's intent
2. **Plans** multi-step workflows (process → extract → assign → comply)
3. **Acts** by invoking Lambda action groups
4. **Observes** results and decides next steps
5. **Iterates** until the task is complete

### Agent Orchestration Flow

```
User Query → Bedrock AgentCore (Nova Micro)
                    │
                    ▼
         ┌─ Reasoning Step ─┐
         │ "What tools do   │
         │  I need?"        │
         └──────────────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
         ▼                     ▼
  DocumentSearch          GraphAgent
  (semantic search)       (Neo4j query)
         │                     │
         └──────────┬──────────┘
                    │
         ┌─ Synthesis Step ─┐
         │ Combine results  │
         │ Generate answer  │
         └──────────────────┘
                    │
                    ▼
              Final Response
         (with citations + RAG info)
```

### Direct RAG vs Agentic Mode

| Mode | When Used | Latency | Reliability |
|------|-----------|---------|-------------|
| **Direct RAG** (`/api/chat`) | All chat queries | ~2-4s | High |
| **Bedrock Agent** (`/api/agent/invoke`) | Complex multi-step tasks | ~10-30s | Medium |

The system defaults to **Direct RAG** for chat (faster, more reliable) and uses **Bedrock AgentCore** for complex orchestration tasks like full document processing pipelines.

---

## Neo4j Knowledge Graph Schema

```
Nodes:
  (:Document  {id, name, path, chunk_count, text_length})
  (:Requirement {id, description, type, priority, domain, confidence, status})
  (:Expert    {id, name, department, skills[], specializations[], workload})
  (:Domain    {name})
  (:Entity    {id, text, type, score})
  (:Project   {id, name})

Relationships:
  (:Document)-[:CONTAINS {confidence}]->(:Requirement)
  (:Requirement)-[:EXTRACTED_FROM {confidence}]->(:Document)
  (:Expert)-[:SPECIALIZES_IN {level}]->(:Domain)
  (:Expert)-[:ASSIGNED_TO {score, reason}]->(:Requirement)
  (:Requirement)-[:SIMILAR_TO {similarity}]->(:Requirement)
  (:Requirement)-[:PART_OF]->(:Project)
  (:Document)-[:MENTIONS {score}]->(:Entity)
  (:Entity)-[:RELATES_TO {predicate}]->(:Entity)
```

---

## Infrastructure (AWS CDK)

```
VPC (2 AZs)
├── Public Subnet    → NAT Gateway
├── Private Subnet   → Lambda functions
└── Isolated Subnet  → Aurora PostgreSQL

Aurora PostgreSQL (Serverless v2, 0.5-16 ACU)
├── database: requirements_db
├── Tables: document_chunks, requirements, domain_experts,
│           compliance_suggestions, kg_nodes, kg_edges,
│           graph_nodes, graph_edges, document_registry
└── Extensions: pgvector (1024-dim embeddings)

S3 Bucket
└── bids/  ← uploaded documents

API Gateway (REST)
└── /v1/*  → Lambda functions

Lambda Functions (Python 3.11, 1024MB, 15min timeout)
├── DocumentProcessor
├── RequirementsExtractor
├── ExpertMatcher
├── ComplianceChecker
├── DocumentSearch
└── GraphAgent

Lambda Layer: RequirementsManagementDeps
└── boto3, numpy, pypdf, neo4j, aws-lambda-powertools

ElastiCache Redis (t3.medium, 2 nodes)
└── Semantic cache for repeated queries

OpenSearch Serverless
└── requirements-search (VECTORSEARCH type)
```
