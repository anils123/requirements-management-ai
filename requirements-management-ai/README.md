# Requirements Management Agentic AI System

An advanced AI-powered system for automated requirements extraction, expert assignment, and compliance checking using Amazon Bedrock, Aurora PostgreSQL with pgvector, and advanced RAG techniques.

## 🚀 Features

- **Automated Document Processing**: Extract requirements from 200+ page PDFs using Amazon Textract
- **Intelligent Requirements Extraction**: Structure requirements using Claude 3.5 Sonnet
- **Expert Assignment**: Match requirements to domain experts using vector similarity
- **Advanced RAG**: Hybrid search with vector similarity + BM25 full-text search
- **Corrective RAG (CRAG)**: Self-healing retrieval with automatic query rewriting
- **Self-Reflective RAG**: Hallucination detection and regeneration
- **Query Decomposition**: Break complex queries into sub-queries
- **Semantic Caching**: Redis-backed cache with embedding similarity
- **Re-ranking**: LLM-based and Cohere API re-ranking
- **Grounded Citations**: Source-linked answers with relevance scores

## 🏗️ Architecture

