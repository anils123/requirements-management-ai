"""
Bedrock AgentCore Configuration
================================
Defines the Requirements Management Agent with:
- 4 action groups (document, extraction, expert, compliance)
- 3 knowledge bases (requirements, experts, regulatory)
- Guardrails for safe responses
- Memory configuration for multi-turn sessions
"""
import json

AGENT_INSTRUCTION = """
You are an expert Requirements Management AI Assistant for bid and project management.

Your capabilities:
1. DOCUMENT PROCESSING: Extract and structure requirements from bid PDFs (up to 200+ pages)
2. REQUIREMENTS EXTRACTION: Identify functional and non-functional requirements with metadata
3. EXPERT ASSIGNMENT: Match requirements to domain experts based on skills, domain, and workload
4. COMPLIANCE ANALYSIS: Generate compliance suggestions using past requirements and regulations

Advanced RAG capabilities you leverage:
- Hybrid search (vector + BM25 with Reciprocal Rank Fusion)
- Corrective RAG with automatic query rewriting when retrieval quality is low
- Self-reflective RAG with hallucination detection and regeneration
- HyDE (Hypothetical Document Embeddings) for improved semantic retrieval
- Query decomposition for complex multi-part questions
- Knowledge graph traversal for entity-relationship context
- Semantic caching for fast repeated queries
- Cohere + LLM re-ranking with grounded citations

Always:
- Cite your sources with relevance scores when providing compliance suggestions
- Explain your expert assignment reasoning
- Flag low-confidence extractions (< 0.7) for human review
- Structure requirements with: ID, type, category, priority, description, acceptance criteria
"""

BEDROCK_CONFIG = {
    "agent": {
        "agentName":                "RequirementsManagementAgent",
        "description":              "Agentic AI for automated requirements management from bid PDFs",
        "foundationModel":          "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "instruction":              AGENT_INSTRUCTION,
        "idleSessionTTLInSeconds":  1800,
        "agentResourceRoleArn":     "arn:aws:iam::${ACCOUNT_ID}:role/BedrockAgentRole",
        "tags": {
            "Application": "RequirementsManagement",
            "Environment": "Production",
        },
    },
    "memory": {
        "enabled":          True,
        "storageDays":      30,
        "memoryType":       "SESSION_SUMMARY",
    },
    "guardrails": {
        "contentFilter": {
            "filtersConfig": [
                {"type": "HATE",     "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
            ]
        },
        "sensitiveInformationPolicy": {
            "piiEntitiesConfig": [
                {"type": "EMAIL",   "action": "ANONYMIZE"},
                {"type": "PHONE",   "action": "ANONYMIZE"},
                {"type": "NAME",    "action": "ANONYMIZE"},
            ]
        },
    },
    "action_groups": [
        {
            "actionGroupName": "DocumentProcessor",
            "description":     "Process bid PDFs and extract text, entities, and embeddings",
            "actionGroupExecutor": {"lambda": "${DOCUMENT_PROCESSOR_LAMBDA_ARN}"},
            "apiSchema": {
                "payload": json.dumps({
                    "openapi": "3.0.0",
                    "info": {"title": "Document Processing API", "version": "1.0.0"},
                    "paths": {
                        "/process-document": {
                            "post": {
                                "operationId": "process_document",
                                "summary": "Process a bid PDF document",
                                "requestBody": {
                                    "required": True,
                                    "content": {"application/json": {"schema": {
                                        "type": "object",
                                        "required": ["document_path"],
                                        "properties": {
                                            "document_path": {"type": "string", "description": "S3 key of the PDF"},
                                            "document_type": {"type": "string", "enum": ["pdf", "docx"], "default": "pdf"},
                                        },
                                    }}},
                                },
                                "responses": {"200": {"description": "Processing result"}},
                            }
                        }
                    },
                })
            },
        },
        {
            "actionGroupName": "RequirementsExtractor",
            "description":     "Extract structured requirements from processed documents",
            "actionGroupExecutor": {"lambda": "${REQUIREMENTS_EXTRACTOR_LAMBDA_ARN}"},
            "apiSchema": {
                "payload": json.dumps({
                    "openapi": "3.0.0",
                    "info": {"title": "Requirements Extraction API", "version": "1.0.0"},
                    "paths": {
                        "/extract-requirements": {
                            "post": {
                                "operationId": "extract_requirements",
                                "summary": "Extract requirements from a processed document",
                                "requestBody": {
                                    "required": True,
                                    "content": {"application/json": {"schema": {
                                        "type": "object",
                                        "required": ["document_id"],
                                        "properties": {
                                            "document_id": {"type": "string"},
                                            "extraction_criteria": {
                                                "type": "object",
                                                "properties": {
                                                    "types":      {"type": "array", "items": {"type": "string"}},
                                                    "priorities": {"type": "array", "items": {"type": "string"}},
                                                    "categories": {"type": "array", "items": {"type": "string"}},
                                                },
                                            },
                                        },
                                    }}},
                                },
                                "responses": {"200": {"description": "Extracted requirements"}},
                            }
                        }
                    },
                })
            },
        },
        {
            "actionGroupName": "ExpertMatcher",
            "description":     "Assign domain experts to requirements",
            "actionGroupExecutor": {"lambda": "${EXPERT_MATCHER_LAMBDA_ARN}"},
            "apiSchema": {
                "payload": json.dumps({
                    "openapi": "3.0.0",
                    "info": {"title": "Expert Matching API", "version": "1.0.0"},
                    "paths": {
                        "/assign-experts": {
                            "post": {
                                "operationId": "assign_experts",
                                "summary": "Assign experts to a list of requirements",
                                "requestBody": {
                                    "required": True,
                                    "content": {"application/json": {"schema": {
                                        "type": "object",
                                        "required": ["requirements"],
                                        "properties": {
                                            "requirements": {"type": "array", "items": {"type": "object"}},
                                            "assignment_criteria": {"type": "object"},
                                        },
                                    }}},
                                },
                                "responses": {"200": {"description": "Expert assignments"}},
                            }
                        }
                    },
                })
            },
        },
        {
            "actionGroupName": "ComplianceChecker",
            "description":     "Generate compliance suggestions with grounded citations",
            "actionGroupExecutor": {"lambda": "${COMPLIANCE_CHECKER_LAMBDA_ARN}"},
            "apiSchema": {
                "payload": json.dumps({
                    "openapi": "3.0.0",
                    "info": {"title": "Compliance Checker API", "version": "1.0.0"},
                    "paths": {
                        "/check-compliance": {
                            "post": {
                                "operationId": "check_compliance",
                                "summary": "Generate compliance suggestions for a requirement",
                                "requestBody": {
                                    "required": True,
                                    "content": {"application/json": {"schema": {
                                        "type": "object",
                                        "required": ["requirement_id", "requirement_text"],
                                        "properties": {
                                            "requirement_id":   {"type": "string"},
                                            "requirement_text": {"type": "string"},
                                            "domain":           {"type": "string"},
                                        },
                                    }}},
                                },
                                "responses": {"200": {"description": "Compliance suggestions with citations"}},
                            }
                        }
                    },
                })
            },
        },
    ],
    "knowledge_bases": [
        {
            "knowledgeBaseId":  "${REQUIREMENTS_KB_ID}",
            "description":      "Past requirements and project data for compliance reference",
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": 10}
            },
        },
        {
            "knowledgeBaseId":  "${EXPERTS_KB_ID}",
            "description":      "Domain expert profiles and skill descriptions",
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": 5}
            },
        },
        {
            "knowledgeBaseId":  "${REGULATORY_KB_ID}",
            "description":      "Regulatory standards and compliance documents",
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": 8}
            },
        },
    ],
}
