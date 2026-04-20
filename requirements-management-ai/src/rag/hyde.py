import json
import boto3
from typing import List
from ..utils.config import CONFIG
from ..utils.embeddings import embed_text

_bedrock = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])


def generate_hypothetical_document(query: str) -> str:
    """Ask the LLM to write a hypothetical answer passage for the query."""
    prompt = (
        f"Write a concise technical passage (3-5 sentences) that would directly answer "
        f"the following question about requirements management:\n\n{query}"
    )
    resp = _bedrock.invoke_model(
        modelId=CONFIG["fast_llm_model"],
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.3,
            "anthropic_version": "bedrock-2023-05-31",
        }),
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


def hyde_embedding(query: str) -> List[float]:
    """Return embedding of a hypothetical document for the query (HyDE)."""
    hyp_doc = generate_hypothetical_document(query)
    return embed_text(hyp_doc)
