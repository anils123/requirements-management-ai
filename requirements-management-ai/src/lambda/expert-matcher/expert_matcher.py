# src/lambda/expert-matcher/expert_matcher.py
import json
import boto3
import os
import numpy as np
from typing import Dict, List, Any, Tuple
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = BedrockAgentResolver()

bedrock_client = boto3.client('bedrock-runtime')
rds_client = boto3.client('rds-data')

@app.tool(name="assign_experts")
@tracer.capture_method
def assign_experts(requirements: List[Dict[str, Any]], 
                  assignment_criteria: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assign domain experts to requirements based on expertise matching.
    
    Args:
        requirements: List of extracted requirements
        assignment_criteria: Criteria for expert assignment
    
    Returns:
        Dictionary containing expert assignments
    """
    try:
        logger.info(f"Assigning experts to {len(requirements)} requirements")
        
        # Load expert profiles
        experts = load_expert_profiles()
        
        # Generate embeddings for requirements
        requirement_embeddings = generate_requirement_embeddings(requirements)
        
        # Match requirements to experts
        assignments = []
        for i, req in enumerate(requirements):
            best_matches = find_best_expert_matches(
                req, requirement_embeddings[i], experts, assignment_criteria
            )
            
            assignments.append({
                'requirement_id': req.get('id'),
                'assigned_experts': best_matches,
                'assignment_confidence': calculate_assignment_confidence(best_matches)
            })
        
        # Update workload balancing
        update_expert_workloads(assignments)
        
        return {
            "status": "success",
            "assignments": assignments,
            "total_requirements": len(requirements),
            "experts_involved": len(set([
                expert['expert_id'] 
                for assignment in assignments 
                for expert in assignment['assigned_experts']
            ]))
        }
        
    except Exception as e:
        logger.error(f"Error assigning experts: {str(e)}")
        raise

def load_expert_profiles() -> List[Dict[str, Any]]:
    """Load expert profiles from database."""
    sql = """
    SELECT 
        expert_id, name, email, department, 
        skills, specializations, current_workload,
        availability_status, skill_embeddings
    FROM domain_experts 
    WHERE availability_status = 'available'
    ORDER BY current_workload ASC
    """
    
    response = rds_client.execute_statement(
        resourceArn=os.environ['DB_CLUSTER_ARN'],
        secretArn=os.environ['DB_SECRET_ARN'],
        database='requirements_db',
        sql=sql
    )
    
    experts = []
    for record in response['records']:
        expert = {
            'expert_id': record[0]['stringValue'],
            'name': record[1]['stringValue'],
            'email': record[2]['stringValue'],
            'department': record[3]['stringValue'],
            'skills': json.loads(record[4]['stringValue']),
            'specializations': json.loads(record[5]['stringValue']),
            'current_workload': record[6]['longValue'],
            'availability_status': record[7]['stringValue'],
            'skill_embeddings': json.loads(record[8]['stringValue'])
        }
        experts.append(expert)
    
    return experts

def generate_requirement_embeddings(requirements: List[Dict]) -> List[List[float]]:
    """Generate embeddings for requirements."""
    embeddings = []
    
    for req in requirements:
        # Combine description and category for embedding
        text = f"{req.get('description', '')} {req.get('category', '')} {req.get('domain', '')}"
        
        response = bedrock_client.invoke_model(
            modelId='amazon.titan-embed-text-v2:0',
            body=json.dumps({'inputText': text})
        )
        
        embedding = json.loads(response['body'].read())['embedding']
        embeddings.append(embedding)
    
    return embeddings

def find_best_expert_matches(requirement: Dict, req_embedding: List[float], 
                           experts: List[Dict], criteria: Dict) -> List[Dict]:
    """Find best expert matches for a requirement."""
    
    matches = []
    max_experts = criteria.get('max_experts_per_requirement', 2)
    min_similarity = criteria.get('min_similarity_threshold', 0.7)
    
    for expert in experts:
        # Calculate similarity between requirement and expert skills
        similarity = calculate_cosine_similarity(
            req_embedding, expert['skill_embeddings']
        )
        
        # Check domain match
        domain_match = check_domain_match(requirement, expert)
        
        # Calculate workload factor
        workload_factor = calculate_workload_factor(expert['current_workload'])
        
        # Combined score
        combined_score = (
            similarity * 0.6 + 
            domain_match * 0.3 + 
            workload_factor * 0.1
        )
        
        if combined_score >= min_similarity:
            matches.append({
                'expert_id': expert['expert_id'],
                'name': expert['name'],
                'email': expert['email'],
                'department': expert['department'],
                'similarity_score': similarity,
                'domain_match_score': domain_match,
                'workload_factor': workload_factor,
                'combined_score': combined_score,
                'assignment_reason': generate_assignment_reason(
                    requirement, expert, similarity, domain_match
                )
            })
    
    # Sort by combined score and return top matches
    matches.sort(key=lambda x: x['combined_score'], reverse=True)
    return matches[:max_experts]

def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    vec1_np = np.array(vec1)
    vec2_np = np.array(vec2)
    
    dot_product = np.dot(vec1_np, vec2_np)
    norm1 = np.linalg.norm(vec1_np)
    norm2 = np.linalg.norm(vec2_np)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)

def check_domain_match(requirement: Dict, expert: Dict) -> float:
    """Check domain match between requirement and expert."""
    req_domain = requirement.get('domain', '').lower()
    req_category = requirement.get('category', '').lower()
    
    expert_specializations = [s.lower() for s in expert.get('specializations', [])]
    expert_skills = [s.lower() for s in expert.get('skills', [])]
    
    # Direct domain match
    if req_domain in expert_specializations:
        return 1.0
    
    # Category match
    if req_category in expert_specializations or req_category in expert_skills:
        return 0.8
    
    # Partial match
    for spec in expert_specializations:
        if req_domain in spec or spec in req_domain:
            return 0.6
    
    return 0.0

def calculate_workload_factor(current_workload: int) -> float:
    """Calculate workload factor (higher is better for assignment)."""
    # Normalize workload (assuming max workload is 10)
    max_workload = 10
    normalized_workload = min(current_workload / max_workload, 1.0)
    
    # Invert so lower workload gives higher factor
    return 1.0 - normalized_workload

def generate_assignment_reason(requirement: Dict, expert: Dict, 
                             similarity: float, domain_match: float) -> str:
    """Generate human-readable assignment reason."""
    reasons = []
    
    if domain_match >= 0.8:
        reasons.append(f"Strong domain expertise in {requirement.get('domain', 'N/A')}")
    
    if similarity >= 0.8:
        reasons.append("High skill similarity match")
    elif similarity >= 0.6:
        reasons.append("Good skill similarity match")
    
    if expert['current_workload'] <= 3:
        reasons.append("Low current workload")
    
    return "; ".join(reasons) if reasons else "General expertise match"

def calculate_assignment_confidence(matches: List[Dict]) -> float:
    """Calculate confidence score for assignment."""
    if not matches:
        return 0.0
    
    # Average of top match scores
    top_scores = [match['combined_score'] for match in matches[:2]]
    return sum(top_scores) / len(top_scores)

def update_expert_workloads(assignments: List[Dict]):
    """Update expert workload counts."""
    workload_updates = {}
    
    for assignment in assignments:
        for expert in assignment['assigned_experts']:
            expert_id = expert['expert_id']
            workload_updates[expert_id] = workload_updates.get(expert_id, 0) + 1
    
    # Update database
    for expert_id, additional_workload in workload_updates.items():
        sql = """
        UPDATE domain_experts 
        SET current_workload = current_workload + :additional_workload,
            last_updated = NOW()
        WHERE expert_id = :expert_id
        """
        
        rds_client.execute_statement(
            resourceArn=os.environ['DB_CLUSTER_ARN'],
            secretArn=os.environ['DB_SECRET_ARN'],
            database='requirements_db',
            sql=sql,
            parameters=[
                {'name': 'additional_workload', 'value': {'longValue': additional_workload}},
                {'name': 'expert_id', 'value': {'stringValue': expert_id}}
            ]
        )

@lambda_handler
@tracer.capture_lambda_handler
@logger.inject_lambda_context
@metrics.log_metrics
def handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda handler for expert assignment."""
    return app.resolve(event, context)
