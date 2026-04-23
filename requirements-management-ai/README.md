# Requirements Management AI

AI-powered requirements management system for bid documents using AWS Bedrock AgentCore, Neo4j Knowledge Graph, and direct RAG pipeline.

## Architecture

```
User → React Frontend (localhost:3000)
         ↓
     FastAPI Backend (localhost:8000)
         ↓
     ai_assistant.py (Direct RAG)
         ↓
     Aurora pgvector ← semantic search
     Aurora SQL      ← structured queries
         ↓
     Amazon Nova Pro → grounded answer
```

### AWS Services
- **Amazon S3** — document storage (`bids/` prefix)
- **Aurora PostgreSQL** — pgvector embeddings + structured data
- **Amazon Bedrock** — Nova Pro (generation), Titan Embed V2 (embeddings)
- **AWS Lambda** — 6 functions (DocumentProcessor, RequirementsExtractor, ExpertMatcher, ComplianceChecker, GraphAgent, DocumentSearch)
- **Amazon Textract** — PDF text extraction
- **Amazon Comprehend** — entity extraction
- **Neo4j** — knowledge graph (nodes: Document, Requirement, Expert, Domain, Entity)

### Graph Schema (Neo4j)
```
(:Document)-[:CONTAINS]->(:Requirement)
(:Requirement)-[:EXTRACTED_FROM]->(:Document)
(:Expert)-[:SPECIALIZES_IN]->(:Domain)
(:Expert)-[:ASSIGNED_TO {score}]->(:Requirement)
(:Requirement)-[:SIMILAR_TO {similarity}]->(:Requirement)
(:Document)-[:MENTIONS]->(:Entity)
```

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI server (all API routes)
│   └── ai_assistant.py      # Direct RAG search engine
├── frontend/
│   └── src/
│       ├── pages/           # Chat, Documents, Requirements, Experts, Graph, Admin
│       ├── components/      # Sidebar, DocumentUpload, CitationList, RAGIndicator
│       └── api/client.ts    # API client
├── src/
│   ├── graph/graph_db.py    # Neo4j graph database layer
│   └── lambda/
│       ├── document-processor/    # PDF → text → chunks → pgvector + KG
│       ├── requirements-extractor/ # chunks → Nova → requirements → Aurora + Neo4j
│       ├── expert-matcher/        # graph traversal → expert assignment
│       ├── compliance-checker/    # past reqs → compliance suggestions
│       ├── graph-agent/           # Neo4j operations for Bedrock AgentCore
│       └── document-search/       # semantic search across all PDFs
├── cdk/                     # AWS CDK infrastructure (VPC, Aurora, Lambda, API GW)
├── scripts/
│   ├── init_database.py     # Aurora schema initialization
│   ├── load_sample_data.py  # Load expert profiles
│   ├── post_deploy_setup.py # Full post-deploy setup
│   ├── redeploy_lambdas.py  # Redeploy all Lambda functions
│   ├── deploy_neo4j.py      # Migrate to Neo4j graph DB
│   ├── debug_db.py          # Database diagnostics
│   └── create_bedrock_agent.py # Create/update Bedrock agent
├── layers/dependencies/     # Lambda layer packages
├── examples/expert_profiles.json
└── config/                  # Environment configs
```

## Quick Start

### Prerequisites
- AWS CLI configured (`aws configure`)
- Node.js 20+ and Python 3.11+
- Neo4j AuraDB free instance (https://console.neo4j.io)

### 1. Deploy Infrastructure
```bash
cd cdk
npm install
npx cdk deploy RequirementsManagementStack --require-approval never
```

### 2. Post-Deploy Setup
```bash
python scripts/post_deploy_setup.py
```

### 3. Start Development Servers
```bash
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

Open: http://localhost:3000

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Direct RAG search (main AI assistant) |
| GET/POST | `/api/documents` | List / process documents |
| POST | `/api/documents/upload` | Upload PDF to S3 |
| GET/POST | `/api/requirements` | List / extract requirements |
| GET/POST | `/api/experts` | List experts / assign to requirements |
| POST | `/api/compliance` | Generate compliance suggestions |
| POST | `/api/search` | Semantic search across all PDFs |
| POST | `/api/graph` | Neo4j graph operations |
| GET | `/api/knowledge-graph` | KG nodes and edges |
| GET | `/api/stats` | System statistics |
| GET | `/api/health` | Health check |

## Environment Variables

```bash
# AWS (set via aws configure or IAM role)
AWS_REGION=us-east-1

# Neo4j (required for graph features)
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>
```

## Redeploy Lambdas

```bash
python scripts/redeploy_lambdas.py
```
