# docs/architecture.md

# Requirements Management AI System Architecture

## Overview

The Requirements Management AI System is built on a modern, cloud-native architecture leveraging Amazon Web Services (AWS) and advanced AI/ML capabilities.

## High-Level Architecture

```mermaid
graph TB
    A[Document Upload] --> B[Amazon S3]
    B --> C[Document Processor Lambda]
    C --> D[Amazon Textract]
    C --> E[Amazon Comprehend]
    C --> F[Aurora PostgreSQL + pgvector]
    
    G[Requirements Extraction] --> H[Requirements Extractor Lambda]
    H --> I[Bedrock Claude 3.5 Sonnet]
    H --> J[OpenSearch Serverless]
    
    K[Expert Assignment] --> L[Expert Matcher Lambda]
    L --> M[Vector Similarity Search]
    L --> F
    
    N[Compliance Checking] --> O[Compliance Checker Lambda]
    O --> P[Regulatory Knowledge Base]
    
    Q[Bedrock Agent] --> C
    Q --> H
    Q --> L
    Q --> O
    
    R[Hybrid Search Engine] --> F
    R --> J
    R --> S[Redis Cache]
    
    T[API Gateway] --> Q
    U[Web Interface] --> T
