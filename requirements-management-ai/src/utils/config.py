import os
import json
import boto3

def get_config() -> dict:
    env = os.environ.get("ENVIRONMENT", "development")
    base = {
        "environment": env,
        "aws_region": os.environ.get("AWS_REGION", "us-east-1"),
        "opensearch_endpoint": os.environ.get("OPENSEARCH_ENDPOINT", ""),
        "redis_endpoint": os.environ.get("REDIS_ENDPOINT", "localhost"),
        "redis_port": int(os.environ.get("REDIS_PORT", "6379")),
        "db_cluster_arn": os.environ.get("DB_CLUSTER_ARN", ""),
        "db_secret_arn": os.environ.get("DB_SECRET_ARN", ""),
        "db_name": os.environ.get("DB_NAME", "requirements_db"),
        "bucket_name": os.environ.get("BUCKET_NAME", ""),
        "embedding_model": os.environ.get("EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"),
        "llm_model": os.environ.get("LLM_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
        "fast_llm_model": os.environ.get("FAST_LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"),
        "cohere_api_key_secret": os.environ.get("COHERE_API_KEY_SECRET", ""),
        "knowledge_graph_endpoint": os.environ.get("NEPTUNE_ENDPOINT", ""),
        "cache_ttl_seconds": int(os.environ.get("CACHE_TTL", "3600")),
        "cache_similarity_threshold": float(os.environ.get("CACHE_SIM_THRESHOLD", "0.92")),
        "rrf_k": int(os.environ.get("RRF_K", "60")),
        "top_k": int(os.environ.get("TOP_K", "10")),
        "relevance_threshold": float(os.environ.get("RELEVANCE_THRESHOLD", "0.6")),
    }
    return base

CONFIG = get_config()
