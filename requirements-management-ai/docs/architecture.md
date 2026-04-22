# Requirements Management AI System Architecture

## Canonical Diagram (draw.io)

The canonical editable architecture diagram is:

- `docs/architecture.drawio`

It covers all required layers and data flows:

1. UI layer (user + React frontend)
2. Backend/API layer (FastAPI, API Gateway, Bedrock agent runtime/action groups)
3. AWS services layer (Lambda, Bedrock models, Textract, Comprehend, KBs, OpenSearch, Redis)
4. Data stores layer (S3, Aurora PostgreSQL + pgvector, requirements/compliance tables)
5. RAG pipeline (cache, routing, HyDE, decomposition, hybrid retrieval, CRAG, reranking, grounded answer)
6. Knowledge graph layer (entity/relation extraction, KG storage/traversal, optional Neptune endpoint)

## Data Flow Summary

- Document ingestion: `UI -> FastAPI/API -> S3 -> DocumentProcessor -> Textract/Comprehend/Bedrock -> Aurora + KG tables -> Bedrock KB/OpenSearch`.
- Requirement extraction: `RequirementsExtractor -> Aurora chunks + KG context -> Bedrock Nova -> requirements table`.
- Expert matching: `ExpertMatcher -> Titan embeddings + experts table -> assignment scoring`.
- Compliance: `ComplianceChecker -> Bedrock Nova -> compliance_suggestions table`.
- Agent response: `Bedrock Agent Runtime -> Hybrid retrieval pipeline -> grounded answer + citations -> frontend SSE stream`.
