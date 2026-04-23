# User Guide — Requirements Management AI

## Overview

The Requirements Management AI is an intelligent system that:
- **Parses** bid documents (PDFs) automatically
- **Extracts** structured requirements using AI
- **Searches** across all documents using natural language
- **Assigns** domain experts to requirements
- **Checks** compliance against regulations
- **Visualizes** relationships in a knowledge graph

---

## Getting Started

1. Open **http://localhost:3000** in your browser
2. The app opens on the **AI Chat** page
3. Use the left sidebar to navigate between sections

---

## Navigation

| Icon | Section | Purpose |
|------|---------|---------|
| 💬 | **AI Chat** | Ask questions about any uploaded document |
| 📄 | **Documents** | Upload and manage bid PDFs |
| 📋 | **Requirements** | View and manage extracted requirements |
| 👤 | **Experts** | View domain expert profiles |
| 🔗 | **Knowledge Graph** | Explore entity relationships |
| 🗂️ | **Workspaces** | Manage project workspaces |
| 📊 | **Admin** | System statistics and health |

---

## AI Chat — Knowledge Base Search

The AI Chat is a **semantic search engine** over all uploaded documents.

### How to Use

1. Type any question in the input box
2. Press **Enter** or click the **Send** button
3. The AI searches all documents and returns a grounded answer with citations

### Document Filter

Click the **Filter** button (top right) to restrict search to a specific document:
- All Documents (default)
- CH Charging System
- EF EFI System
- EC Emission Control Systems
- CO Cooling System
- Rail Train

### Prompt Suggestions

Click any suggestion card on the welcome screen:
- "What documents are available?"
- "List all requirements from the EFI system"
- "What are the voltage requirements in the charging system?"
- "Show cooling system specifications"
- "What emission control requirements exist?"
- "Find all high priority security requirements"
- "Who are the domain experts for performance?"
- "What compliance standards apply to the system?"

### Understanding Responses

Each response includes:
- **Answer** — grounded in document content with citations
- **RAG Indicators** — shows search strategy used (Hybrid, Semantic, Structured)
- **Citations** — source document, chunk ID, and relevance score (%)
- **Intent** — detected query type (search, list_reqs, expert_query, etc.)

### Example Queries

```
# General search
"What are the fuel injection requirements?"
"Show me all safety requirements"
"What specifications exist for the alternator?"

# Document-specific
"What does the charging system PDF say about voltage?"
"List all requirements from the EFI document"

# Requirements queries
"Show high priority requirements"
"What functional requirements exist for security?"

# Expert queries
"Who should review the performance requirements?"
"Which experts specialize in compliance?"

# Compliance queries
"What ISO standards apply to the emission system?"
"Are there GDPR requirements in the documents?"
```

---

## Documents — Upload & Process

### Uploading a Document

1. Go to **Documents** tab
2. Drag and drop a PDF/TXT file onto the upload zone, or click to browse
3. The system automatically:
   - Uploads to S3
   - Extracts text (pypdf → Textract fallback)
   - Generates embeddings (Titan Embed V2)
   - Stores chunks in pgvector database
   - Extracts entities for Knowledge Graph
4. Status shows: **Uploading** → **Processing** → **Ready**

### Extracting Requirements

1. Once a document shows **Ready** status
2. Click **Extract Reqs →** button
3. The system:
   - Fetches document chunks from database
   - Uses Knowledge Graph context for enrichment
   - Calls Amazon Nova Micro to extract requirements
   - Stores requirements in Aurora with document-scoped IDs
   - Creates Neo4j graph relationships
4. Automatically navigates to **Requirements** tab

### Document List

All uploaded documents are shown with:
- Document name
- Number of indexed chunks
- Upload timestamp
- S3 key path

Click **Refresh** to reload from the database.

---

## Requirements — View & Manage

### Filtering Requirements

Use the filter tabs at the top:
- **All** — all requirements across all documents
- **High Priority** — high priority requirements only
- **Pending Review** — extracted but not yet reviewed
- **Approved** — approved requirements

**Document filter tabs** appear when multiple documents have requirements:
- Click a document name to show only its requirements
- Shows count per document

**Search box** — filter by requirement ID or description text.

### Requirement Details

Click any requirement to expand it and see:
- **Acceptance Criteria** — conditions for the requirement to be met
- **Assigned Experts** — experts matched to this requirement
- **Compliance Suggestion** — AI-generated compliance guidance

### Actions

| Button | Action |
|--------|--------|
| **Assign Experts** | Find and assign domain experts using graph traversal |
| **Check Compliance** | Generate compliance suggestions using past requirements |
| **Approve** | Mark requirement as approved (green) |
| **Reject** | Mark requirement as rejected (red) |

### Requirement IDs

Requirements use document-scoped IDs to avoid conflicts:
- Format: `REQ-{DOCUMENT_PREFIX}-{SEQUENCE}`
- Example: `REQ-CH_CHARGING--0003`, `REQ-EF_EFI-SYSTE-0012`

---

## Experts — Domain Expert Profiles

### Expert Cards

Each expert card shows:
- **Name** and **Department**
- **Availability status** (available / busy / unavailable)
- **Workload bar** — current vs maximum workload
- **Specializations** — domain areas (security, performance, etc.)
- **Skills** — specific technical skills

### Expert Assignment

Experts are automatically matched to requirements using three strategies:
1. **Domain traversal** — Neo4j graph: Expert → SPECIALIZES_IN → Domain
2. **Semantic similarity** — embedding similarity between requirement and expert skills
3. **Past assignments** — experts who handled similar past requirements

Combined score = domain(40%) + semantic(50%) + history(30%)

---

## Knowledge Graph — Relationship Explorer

### Graph Statistics

The top panel shows:
- **Node types** with counts (Document, Requirement, Expert, Domain, Entity)
- **Relationship types** with counts (CONTAINS, EXTRACTED_FROM, SPECIALIZES_IN, etc.)

### Running Graph Queries

Select an **Action** from the dropdown:

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `semantic_search` | Find nodes by meaning | Query text, Label (optional) |
| `find_experts` | Find experts for a domain | Domain name |
| `past_requirements` | Find similar past requirements | Domain or Query |
| `traverse` | Follow relationships from a node | Label, Node Key, Direction |
| `neighbourhood` | Get 2-hop context | Label, Node Key |
| `list_documents` | List all documents | None |
| `graph_stats` | Show statistics | None |

### Example Graph Queries

**Find security experts:**
- Action: `find_experts`
- Domain: `security`

**Find similar requirements:**
- Action: `semantic_search`
- Label: `Requirement`
- Query: `voltage requirements alternator`

**Traverse document relationships:**
- Action: `traverse`
- Label: `Document`
- Key: `bids/CH_Charging System.pdf`
- Direction: `out`

---

## Admin — System Statistics

The Admin dashboard shows:
- **Total Documents** — documents in knowledge base
- **Requirements** — total extracted requirements
- **Domain Experts** — registered experts
- **Pending Reviews** — requirements awaiting approval
- **Weekly Activity** — documents and requirements by day
- **Requirements by Domain** — pie chart breakdown
- **RAG Pipeline Health** — status of each component
- **Average Confidence** — extraction confidence score

---

## Workspaces

Workspaces organize documents and requirements by project:
- **Bid 2024-Q4** — Q4 infrastructure bid
- **Project Alpha** — Cloud migration project

Click a workspace to set it as active. The active workspace is shown in the sidebar.

---

## Tips & Best Practices

### For Best Search Results
- Use specific technical terms from the documents
- Mention the document name for document-specific queries
- Use the document filter for focused searches
- Ask follow-up questions to drill deeper

### For Document Processing
- Upload PDFs with selectable text (not scanned images) for best results
- Scanned PDFs use Amazon Textract (slower but works)
- Large PDFs (200+ pages) may take 2-5 minutes to process
- Re-process a document if requirements seem incomplete

### For Requirements Management
- Review extracted requirements for accuracy before approving
- Use "Check Compliance" to get regulatory guidance
- Assign experts before sending requirements for review
- Use the search to find duplicate or conflicting requirements

### For the Knowledge Graph
- Run `graph_stats` first to understand what data exists
- Use `semantic_search` with `label=Requirement` to find similar requirements
- Use `traverse` with `direction=both` to see all connections
- The graph grows richer as more documents are processed

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send chat message |
| `Shift+Enter` | New line in chat input |
| `Ctrl+K` | Focus chat input (when on Chat page) |

---

## Supported File Formats

| Format | Processing | Notes |
|--------|-----------|-------|
| `.pdf` | pypdf + Textract | Best results with text-based PDFs |
| `.txt` | Direct S3 read | Fast, no OCR needed |
| `.md` | Direct S3 read | Markdown files |
| `.csv` | Direct S3 read | Comma-separated data |
| `.doc/.docx` | Limited | Basic text extraction |

---

## Troubleshooting

### Chat shows "Search error"
- Check backend is running: `http://localhost:8000/api/health`
- Restart backend: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### Document upload fails
- Check file size (max 100MB)
- Verify S3 bucket exists in AWS Console
- Check backend logs for error details

### "No requirements found" after extraction
- Ensure document was processed first (chunks > 0)
- Try re-processing: click the document in Documents tab
- Check if document has readable text (not a scanned image)

### Requirements page is empty
- Click **Refresh** button
- Extract requirements from a document first
- Check Aurora database has data: `python scripts/debug_db.py`

### Knowledge Graph shows 0 nodes
- Run `python scripts/deploy_neo4j.py` to migrate data
- Check Neo4j credentials in environment variables
- Verify Neo4j AuraDB instance is running

### Experts page is empty
- Load expert profiles: `python scripts/load_sample_data.py`
- Check Aurora `domain_experts` table has data
