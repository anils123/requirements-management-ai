# scripts/init_database.py
import boto3
import json
import os

def initialize_database():
    """Initialize database schema for requirements management."""
    
    rds_client = boto3.client('rds-data')
    
    # Database connection details
    cluster_arn = os.environ.get('DB_CLUSTER_ARN')
    secret_arn = os.environ.get('DB_SECRET_ARN')
    database_name = 'requirements_db'
    
    # SQL schema
    schema_sql = """
    -- Enable pgvector extension
    CREATE EXTENSION IF NOT EXISTS vector;
    
    -- Document chunks table
    CREATE TABLE IF NOT EXISTS document_chunks (
        id SERIAL PRIMARY KEY,
        document_path VARCHAR(500) NOT NULL,
        chunk_id INTEGER NOT NULL,
        text_content TEXT NOT NULL,
        embedding vector(1536),
        entities JSONB,
        metadata JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    -- Requirements table
    CREATE TABLE IF NOT EXISTS requirements (
        id SERIAL PRIMARY KEY,
        requirement_id VARCHAR(50) UNIQUE NOT NULL,
        document_id VARCHAR(100) NOT NULL,
        type VARCHAR(50) NOT NULL,
        category VARCHAR(100),
        priority VARCHAR(20),
        description TEXT NOT NULL,
        acceptance_criteria JSONB,
        domain VARCHAR(100),
        complexity VARCHAR(20),
        status VARCHAR(50) DEFAULT 'extracted',
        confidence_score FLOAT,
        source_chunk_ids INTEGER[],
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    -- Domain experts table
    CREATE TABLE IF NOT EXISTS domain_experts (
        id SERIAL PRIMARY KEY,
        expert_id VARCHAR(50) UNIQUE NOT NULL,
        name VARCHAR(200) NOT NULL,
        email VARCHAR(200) NOT NULL,
        department VARCHAR(100),
        skills JSONB NOT NULL,
        specializations JSONB NOT NULL,
        skill_embeddings vector(1536),
        current_workload INTEGER DEFAULT 0,
        max_workload INTEGER DEFAULT 10,
        availability_status VARCHAR(50) DEFAULT 'available',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    -- Expert assignments table
    CREATE TABLE IF NOT EXISTS expert_assignments (
        id SERIAL PRIMARY KEY,
        requirement_id VARCHAR(50) NOT NULL,
        expert_id VARCHAR(50) NOT NULL,
        assignment_type VARCHAR(50) DEFAULT 'primary',
        confidence_score FLOAT,
        assignment_reason TEXT,
        status VARCHAR(50) DEFAULT 'assigned',
        assigned_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY (requirement_id) REFERENCES requirements(requirement_id),
        FOREIGN KEY (expert_id) REFERENCES domain_experts(expert_id)
    );
    
    -- Compliance suggestions table
    CREATE TABLE IF NOT EXISTS compliance_suggestions (
        id SERIAL PRIMARY KEY,
        requirement_id VARCHAR(50) NOT NULL,
        regulation_type VARCHAR(100),
        suggestion_text TEXT NOT NULL,
        confidence_score FLOAT,
        source_documents JSONB,
        status VARCHAR(50) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY (requirement_id) REFERENCES requirements(requirement_id)
    );
    
    -- Create indexes
    CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_document_chunks_path ON document_chunks(document_path);
    CREATE INDEX IF NOT EXISTS idx_requirements_domain ON requirements(domain);
    CREATE INDEX IF NOT EXISTS idx_requirements_status ON requirements(status);
    CREATE INDEX IF NOT EXISTS idx_experts_specializations ON domain_experts USING GIN(specializations);
    CREATE INDEX IF NOT EXISTS idx_experts_availability ON domain_experts(availability_status);
    CREATE INDEX IF NOT EXISTS idx_expert_assignments_requirement ON expert_assignments(requirement_id);
    CREATE INDEX IF NOT EXISTS idx_expert_assignments_expert ON expert_assignments(expert_id);
    """
    
    # Execute schema creation
    try:
        response = rds_client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database_name,
            sql=schema_sql
        )
        
        print("Database schema initialized successfully")
        print(f"Execution ID: {response.get('id', 'N/A')}")
        
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        raise

if __name__ == "__main__":
    initialize_database()
