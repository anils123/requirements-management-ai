# src/lambda/document-processor/document_processor.py
import json
import boto3
import os
from typing import Dict, List, Any
import logging
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = BedrockAgentResolver()

# AWS clients
textract_client = boto3.client('textract')
comprehend_client = boto3.client('comprehend')
bedrock_client = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')
rds_client = boto3.client('rds-data')

@app.tool(name="process_document")
@tracer.capture_method
def process_document(document_path: str, document_type: str = "pdf") -> Dict[str, Any]:
    """
    Process a document to extract text, entities, and metadata.
    
    Args:
        document_path: S3 path to the document
        document_type: Type of document (pdf, docx, txt)
    
    Returns:
        Dictionary containing extracted content and metadata
    """
    try:
        logger.info(f"Processing document: {document_path}")
        
        # Extract text using Textract
        text_content = extract_text_with_textract(document_path)
        
        # Extract entities using Comprehend
        entities = extract_entities_with_comprehend(text_content)
        
        # Chunk the document
        chunks = chunk_document(text_content)
        
        # Generate embeddings
        embeddings = generate_embeddings(chunks)
        
        # Store in vector database
        store_in_vector_db(chunks, embeddings, document_path, entities)
        
        metrics.add_metric(name="DocumentProcessed", unit=MetricUnit.Count, value=1)
        
        return {
            "status": "success",
            "document_path": document_path,
            "chunks_created": len(chunks),
            "entities_found": len(entities),
            "processing_metadata": {
                "text_length": len(text_content),
                "entity_types": list(set([e['Type'] for e in entities]))
            }
        }
        
    except Exception as e:
        logger.error(f"Error processing document {document_path}: {str(e)}")
        metrics.add_metric(name="DocumentProcessingError", unit=MetricUnit.Count, value=1)
        raise

def extract_text_with_textract(document_path: str) -> str:
    """Extract text from document using Amazon Textract."""
    bucket_name = os.environ['BUCKET_NAME']
    
    response = textract_client.start_document_text_detection(
        DocumentLocation={
            'S3Object': {
                'Bucket': bucket_name,
                'Name': document_path
            }
        }
    )
    
    job_id = response['JobId']
    
    # Wait for job completion
    while True:
        response = textract_client.get_document_text_detection(JobId=job_id)
        status = response['JobStatus']
        
        if status in ['SUCCEEDED', 'FAILED']:
            break
    
    if status == 'FAILED':
        raise Exception("Textract job failed")
    
    # Extract text from blocks
    text_content = ""
    for block in response['Blocks']:
        if block['BlockType'] == 'LINE':
            text_content += block['Text'] + '\n'
    
    return text_content

def extract_entities_with_comprehend(text: str) -> List[Dict]:
    """Extract entities using Amazon Comprehend."""
    # Split text into chunks for Comprehend (max 5000 bytes)
    max_bytes = 5000
    text_bytes = text.encode('utf-8')
    
    entities = []
    for i in range(0, len(text_bytes), max_bytes):
        chunk = text_bytes[i:i+max_bytes].decode('utf-8', errors='ignore')
        
        response = comprehend_client.detect_entities(
            Text=chunk,
            LanguageCode='en'
        )
        
        entities.extend(response['Entities'])
    
    return entities

def chunk_document(text: str, chunk_size: int = 512, overlap: int = 50) -> List[Dict]:
    """Chunk document into smaller pieces with overlap."""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunk_text = ' '.join(chunk_words)
        
        chunks.append({
            'text': chunk_text,
            'chunk_id': i // (chunk_size - overlap),
            'start_word': i,
            'end_word': min(i + chunk_size, len(words))
        })
    
    return chunks

def generate_embeddings(chunks: List[Dict]) -> List[List[float]]:
    """Generate embeddings for text chunks using Bedrock."""
    embeddings = []
    
    for chunk in chunks:
        response = bedrock_client.invoke_model(
            modelId='amazon.titan-embed-text-v2:0',
            body=json.dumps({
                'inputText': chunk['text']
            })
        )
        
        embedding = json.loads(response['body'].read())['embedding']
        embeddings.append(embedding)
    
    return embeddings

def store_in_vector_db(chunks: List[Dict], embeddings: List[List[float]], 
                      document_path: str, entities: List[Dict]):
    """Store chunks and embeddings in Aurora PostgreSQL with pgvector."""
    
    # Prepare SQL statements
    insert_sql = """
    INSERT INTO document_chunks (
        document_path, chunk_id, text_content, embedding, 
        entities, metadata, created_at
    ) VALUES (
        :document_path, :chunk_id, :text_content, :embedding::vector,
        :entities, :metadata, NOW()
    )
    """
    
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        parameters = [
            {'name': 'document_path', 'value': {'stringValue': document_path}},
            {'name': 'chunk_id', 'value': {'longValue': chunk['chunk_id']}},
            {'name': 'text_content', 'value': {'stringValue': chunk['text']}},
            {'name': 'embedding', 'value': {'stringValue': str(embedding)}},
            {'name': 'entities', 'value': {'stringValue': json.dumps(entities)}},
            {'name': 'metadata', 'value': {'stringValue': json.dumps({
                'start_word': chunk['start_word'],
                'end_word': chunk['end_word'],
                'chunk_length': len(chunk['text'])
            })}}
        ]
        
        rds_client.execute_statement(
            resourceArn=os.environ['DB_CLUSTER_ARN'],
            secretArn=os.environ['DB_SECRET_ARN'],
            database='requirements_db',
            sql=insert_sql,
            parameters=parameters
        )

@lambda_handler
@tracer.capture_lambda_handler
@logger.inject_lambda_context
@metrics.log_metrics
def handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda handler for document processing."""
    return app.resolve(event, context)
