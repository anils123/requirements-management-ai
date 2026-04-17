# scripts/create_bedrock_agent.py
import boto3
import json
from typing import Dict, Any

def create_requirements_management_agent() -> str:
    """Create and configure the Requirements Management Bedrock Agent."""
    
    bedrock_agent_client = boto3.client('bedrock-agent')
    
    # Agent configuration
    agent_config = {
        'agentName': 'RequirementsManagementAgent',
        'description': 'AI agent for automated requirements management and expert assignment',
        'foundationModel': 'anthropic.claude-3-5-sonnet-20241022-v2:0',
        'instruction': """
        You are an expert Requirements Management Assistant specializing in:
        
        1. DOCUMENT PROCESSING: Extract and structure requirements from bid documents and PDFs
        2. EXPERT ASSIGNMENT: Match requirements to appropriate domain experts based on skills and workload
        3. COMPLIANCE ANALYSIS: Generate compliance suggestions using historical data and regulations
        4. HYBRID SEARCH: Use advanced RAG techniques including vector similarity and full-text search
        
        Key Capabilities:
        - Process documents up to 200+ pages
        - Extract functional and non-functional requirements
        - Assign technical domains and responsible experts
        - Generate compliance comments and suggestions
        - Use corrective RAG for self-healing retrieval
        - Implement query decomposition for complex questions
        - Provide grounded citations with relevance scores
        
        Always provide detailed explanations for your recommendations and cite sources.
        """,
        'idleSessionTTLInSeconds': 1800,
        'agentResourceRoleArn': 'arn:aws:iam::ACCOUNT:role/BedrockAgentRole',
        'customerEncryptionKeyArn': None,
        'tags': {
            'Environment': 'Production',
            'Application': 'RequirementsManagement',
            'Owner': 'AITeam'
        }
    }
    
    # Create agent
    response = bedrock_agent_client.create_agent(**agent_config)
    agent_id = response['agent']['agentId']
    
    print(f"Created agent with ID: {agent_id}")
    
    # Create action groups
    create_action_groups(bedrock_agent_client, agent_id)
    
    # Associate knowledge bases
    associate_knowledge_bases(bedrock_agent_client, agent_id)
    
    # Prepare agent
    bedrock_agent_client.prepare_agent(agentId=agent_id)
    
    print(f"Agent {agent_id} prepared successfully")
    
    return agent_id

def create_action_groups(client, agent_id: str):
    """Create action groups for the agent."""
    
    action_groups = [
        {
            'actionGroupName': 'DocumentProcessor',
            'description': 'Process and extract content from documents',
            'actionGroupExecutor': {
                'lambda': 'arn:aws:lambda:REGION:ACCOUNT:function:DocumentProcessor'
            },
            'apiSchema': {
                'payload': json.dumps({
                    "openapi": "3.0.0",
                    "info": {
                        "title": "Document Processing API",
                        "version": "1.0.0"
                    },
                    "paths": {
                        "/process-document": {
                            "post": {
                                "summary": "Process a document to extract text and metadata",
                                "operationId": "process_document",
                                "requestBody": {
                                    "required": True,
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "type": "object",
                                                "properties": {
                                                    "document_path": {
                                                        "type": "string",
                                                        "description": "S3 path to the document"
                                                    },
                                                    "document_type": {
                                                        "type": "string",
                                                        "enum": ["pdf", "docx", "txt"],
                                                        "description": "Type of document"
                                                    }
                                                },
                                                "required": ["document_path"]
                                            }
                                        }
                                    }
                                },
                                "responses": {
                                    "200": {
                                        "description": "Document processed successfully",
                                        "content": {
                                            "application/json": {
                                                "schema": {
                                                    "type": "object",
                                                    "properties": {
                                                        "status": {"type": "string"},
                                                        "chunks_created": {"type": "integer"},
                                                        "entities_found": {"type": "integer"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                })
            }
        },
        {
            'actionGroupName': 'RequirementsExtractor',
            'description': 'Extract and structure requirements from processed documents',
            'actionGroupExecutor': {
                'lambda': 'arn:aws:lambda:REGION:ACCOUNT:function:RequirementsExtractor'
            },
            'apiSchema': {
                'payload': json.dumps({
                    "openapi": "3.0.0",
                    "info": {
                        "title": "Requirements Extraction API",
                        "version": "1.0.0"
                    },
                    "paths": {
                        "/extract-requirements": {
                            "post": {
                                "summary": "Extract structured requirements from document",
                                "operationId": "extract_requirements",
                                "requestBody": {
                                    "required": True,
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "type": "object",
                                                "properties": {
                                                    "document_id": {
                                                        "type": "string",
                                                        "description": "Document identifier"
                                                    },
                                                    "extraction_criteria": {
                                                        "type": "object",
                                                        "properties": {
                                                            "types": {
                                                                "type": "array",
                                                                "items": {"type": "string"}
                                                            },
                                                            "priorities": {
                                                                "type": "array", 
                                                                "items": {"type": "string"}
                                                            }
                                                        }
                                                    }
                                                },
                                                "required": ["document_id"]
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                })
            }
        }
    ]
    
    for action_group in action_groups:
        response = client.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            **action_group
        )
        print(f"Created action group: {action_group['actionGroupName']}")

def associate_knowledge_bases(client, agent_id: str):
    """Associate knowledge bases with the agent."""
    
    knowledge_bases = [
        'REQUIREMENTS_KB_ID',  # Replace with actual KB IDs
        'EXPERTS_KB_ID',
        'REGULATORY_KB_ID'
    ]
    
    for kb_id in knowledge_bases:
        client.associate_agent_knowledge_base(
            agentId=agent_id,
            agentVersion='DRAFT',
            knowledgeBaseId=kb_id,
            description=f'Knowledge base {kb_id} for requirements management'
        )
        print(f"Associated knowledge base: {kb_id}")

if __name__ == "__main__":
    agent_id = create_requirements_management_agent()
    print(f"Requirements Management Agent created: {agent_id}")
