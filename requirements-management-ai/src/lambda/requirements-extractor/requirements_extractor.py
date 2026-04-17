# src/lambda/requirements-extractor/requirements_extractor.py
import json
import boto3
import os
from typing import Dict, List, Any
import re
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = BedrockAgentResolver()

bedrock_client = boto3.client('bedrock-runtime')
opensearch_client = boto3.client('opensearchserverless')

@app.tool(name="extract_requirements")
@tracer.capture_method
def extract_requirements(document_id: str, extraction_criteria: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured requirements from processed document chunks.
    
    Args:
        document_id: Identifier for the processed document
        extraction_criteria: Criteria for requirement extraction
    
    Returns:
        Dictionary containing extracted requirements
    """
    try:
        logger.info(f"Extracting requirements from document: {document_id}")
        
        # Retrieve document chunks
        chunks = retrieve_document_chunks(document_id)
        
        # Extract requirements using LLM
        requirements = []
        for chunk in chunks:
            chunk_requirements = extract_requirements_from_chunk(
                chunk['text'], extraction_criteria
            )
            requirements.extend(chunk_requirements)
        
        # Deduplicate and structure requirements
        structured_requirements = structure_requirements(requirements)
        
        # Store requirements in search index
        store_requirements_in_search(document_id, structured_requirements)
        
        return {
            "status": "success",
            "document_id": document_id,
            "requirements_extracted": len(structured_requirements),
            "requirements": structured_requirements
        }
        
    except Exception as e:
        logger.error(f"Error extracting requirements: {str(e)}")
        raise

def retrieve_document_chunks(document_id: str) -> List[Dict]:
    """Retrieve document chunks from vector database."""
    # Implementation would query Aurora PostgreSQL
    # This is a simplified version
    return [
        {"text": "Sample requirement text", "chunk_id": 1},
        {"text": "Another requirement", "chunk_id": 2}
    ]

def extract_requirements_from_chunk(text: str, criteria: Dict[str, Any]) -> List[Dict]:
    """Extract requirements from a text chunk using Bedrock LLM."""
    
    prompt = f"""
    Extract functional and non-functional requirements from the following text.
    
    Extraction Criteria:
    - Requirement types: {criteria.get('types', ['functional', 'non-functional'])}
    - Priority levels: {criteria.get('priorities', ['high', 'medium', 'low'])}
    - Categories: {criteria.get('categories', ['performance', 'security', 'usability'])}
    
    Text to analyze:
    {text}
    
    Return requirements in JSON format with the following structure:
    {{
        "requirements": [
            {{
                "id": "REQ-001",
                "type": "functional|non-functional",
                "category": "category_name",
                "priority": "high|medium|low",
                "description": "requirement description",
                "acceptance_criteria": ["criteria1", "criteria2"],
                "source_text": "original text snippet",
                "confidence_score": 0.95
            }}
        ]
    }}
    """
    
    response = bedrock_client.invoke_model(
        modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
        body=json.dumps({
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 2000,
            'temperature': 0.1
        })
    )
    
    result = json.loads(response['body'].read())
    content = result['content'][0]['text']
    
    try:
        requirements_data = json.loads(content)
        return requirements_data.get('requirements', [])
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON")
        return []

def structure_requirements(requirements: List[Dict]) -> List[Dict]:
    """Structure and deduplicate requirements."""
    structured = []
    seen_descriptions = set()
    
    for req in requirements:
        description = req.get('description', '').strip().lower()
        
        # Skip duplicates
        if description in seen_descriptions:
            continue
        
        seen_descriptions.add(description)
        
        # Add structured metadata
        structured_req = {
            **req,
            'extracted_at': '2024-01-01T00:00:00Z',  # Current timestamp
            'status': 'extracted',
            'domain': classify_domain(req.get('description', '')),
            'complexity': assess_complexity(req.get('description', ''))
        }
        
        structured.append(structured_req)
    
    return structured

def classify_domain(description: str) -> str:
    """Classify requirement domain based on description."""
    domain_keywords = {
        'security': ['security', 'authentication', 'authorization', 'encryption'],
        'performance': ['performance', 'speed', 'latency', 'throughput'],
        'ui_ux': ['interface', 'user', 'display', 'navigation'],
        'integration': ['api', 'integration', 'interface', 'connection'],
        'data': ['data', 'database', 'storage', 'backup']
    }
    
    description_lower = description.lower()
    
    for domain, keywords in domain_keywords.items():
        if any(keyword in description_lower for keyword in keywords):
            return domain
    
    return 'general'

def assess_complexity(description: str) -> str:
    """Assess requirement complexity based on description."""
    complexity_indicators = {
        'high': ['complex', 'advanced', 'sophisticated', 'multiple', 'integration'],
        'medium': ['moderate', 'standard', 'typical', 'normal'],
        'low': ['simple', 'basic', 'straightforward', 'minimal']
    }
    
    description_lower = description.lower()
    
    for level, indicators in complexity_indicators.items():
        if any(indicator in description_lower for indicator in indicators):
            return level
    
    return 'medium'

def store_requirements_in_search(document_id: str, requirements: List[Dict]):
    """Store requirements in OpenSearch for hybrid search."""
    # Implementation would index requirements in OpenSearch
    logger.info(f"Storing {len(requirements)} requirements for document {document_id}")

@lambda_handler
@tracer.capture_lambda_handler
@logger.inject_lambda_context
@metrics.log_metrics
def handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda handler for requirements extraction."""
    return app.resolve(event, context)
