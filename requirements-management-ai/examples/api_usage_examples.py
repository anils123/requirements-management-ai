# examples/api_usage_examples.py
"""
Example usage of the Requirements Management AI System API
"""

import boto3
import json
import time
from typing import Dict, Any

class RequirementsManagementClient:
    """Client for interacting with the Requirements Management AI System."""
    
    def __init__(self, api_endpoint: str, agent_id: str, region: str = 'us-east-1'):
        self.api_endpoint = api_endpoint
        self.agent_id = agent_id
        self.bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
    
    def upload_document(self, file_path: str, bucket_name: str) -> str:
        """Upload a document to S3 for processing."""
        
        file_name = file_path.split('/')[-1]
        s3_key = f"documents/{int(time.time())}_{file_name}"
        
        self.s3_client.upload_file(file_path, bucket_name, s3_key)
        
        return f"s3://{bucket_name}/{s3_key}"
    
    def process_document(self, document_path: str) -> Dict[str, Any]:
        """Process a document to extract requirements."""
        
        prompt = f"""
        Please process the document at {document_path} and extract all requirements.
        
        I need you to:
        1. Extract and structure all functional and non-functional requirements
        2. Assign appropriate domain experts to each requirement
        3. Generate compliance suggestions based on the requirements
        
        Please provide a comprehensive analysis with citations.
        """
        
        response = self.bedrock_agent_runtime.invoke_agent(
            agentId=self.agent_id,
            agentAliasId='TSTALIASID',
            sessionId=f"session_{int(time.time())}",
            inputText=prompt
        )
        
        # Process streaming response
        result = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    result += chunk['bytes'].decode('utf-8')
        
        return {"response": result, "session_id": response.get('sessionId')}
    
    def query_requirements(self, query: str, filters: Dict = None) -> Dict[str, Any]:
        """Query the requirements knowledge base."""
        
        filter_text = ""
        if filters:
            filter_text = f"Apply these filters: {json.dumps(filters)}"
        
        prompt = f"""
        Search for requirements related to: {query}
        
        {filter_text}
        
        Please provide:
        1. Relevant requirements with their details
        2. Assigned experts for each requirement
        3. Compliance status and suggestions
        4. Source citations with confidence scores
        
        Use hybrid search to find the most relevant results.
        """
        
        response = self.bedrock_agent_runtime.invoke_agent(
            agentId=self.agent_id,
            agentAliasId='TSTALIASID',
            sessionId=f"query_session_{int(time.time())}",
            inputText=prompt
        )
        
        # Process streaming response
        result = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    result += chunk['bytes'].decode('utf-8')
        
        return {"response": result}
    
    def assign_experts(self, requirement_ids: list) -> Dict[str, Any]:
        """Assign experts to specific requirements."""
        
        prompt = f"""
        Please assign domain experts to the following requirements: {requirement_ids}
        
        Consider:
        1. Expert specializations and current workload
        2. Requirement complexity and domain
        3. Optimal workload distribution
        
        Provide detailed reasoning for each assignment.
        """
        
        response = self.bedrock_agent_runtime.invoke_agent(
            agentId=self.agent_id,
            agentAliasId='TSTALIASID',
            sessionId=f"expert_session_{int(time.time())}",
            inputText=prompt
        )
        
        # Process streaming response
        result = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    result += chunk['bytes'].decode('utf-8')
        
        return {"response": result}

def main():
    """Example usage of the Requirements Management AI System."""
    
    # Configuration (replace with your actual values)
    API_ENDPOINT = "https://your-api-gateway-endpoint.amazonaws.com/prod"
    AGENT_ID = "your-bedrock-agent-id"
    BUCKET_NAME = "your-document-bucket"
    
    # Initialize client
    client = RequirementsManagementClient(API_ENDPOINT, AGENT_ID)
    
    print("🚀 Requirements Management AI System - Example Usage")
    print("=" * 60)
    
    # Example 1: Upload and process a document
    print("\n📄 Example 1: Document Processing")
    print("-" * 40)
    
    # Upload sample document (replace with actual file path)
    document_path = "examples/sample_requirements.pdf"
    try:
        s3_path = client.upload_document(document_path, BUCKET_NAME)
        print(f"✅ Document uploaded to: {s3_path}")
        
        # Process the document
        result = client.process_document(s3_path)
        print(f"✅ Document processed successfully")
        print(f"📋 Processing Result:\n{result['response'][:500]}...")
        
    except Exception as e:
        print(f"❌ Error processing document: {e}")
    
    # Example 2: Query requirements
    print("\n🔍 Example 2: Requirements Search")
    print("-" * 40)
    
    try:
        query_result = client.query_requirements(
            "security authentication requirements",
            filters={"domain": "security", "priority": "high"}
        )
        print(f"✅ Query executed successfully")
        print(f"🔍 Search Results:\n{query_result['response'][:500]}...")
        
    except Exception as e:
        print(f"❌ Error querying requirements: {e}")
    
    # Example 3: Expert assignment
    print("\n👥 Example 3: Expert Assignment")
    print("-" * 40)
    
    try:
        assignment_result = client.assign_experts(["REQ-001", "REQ-002", "REQ-003"])
        print(f"✅ Expert assignment completed")
        print(f"👥 Assignment Results:\n{assignment_result['response'][:500]}...")
        
    except Exception as e:
        print(f"❌ Error assigning experts: {e}")
    
    print("\n🎉 Example usage completed!")
    print("\nFor more examples, check the documentation at:")
    print("https://github.com/your-org/requirements-management-ai/docs/")

if __name__ == "__main__":
    main()
