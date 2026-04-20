import json
import os
import boto3
import cohere
from typing import List, Dict, Any
from ..utils.config import CONFIG
import boto3 as _boto3

_bedrock = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])


def _get_cohere_client():
    if not CONFIG.get("cohere_api_key_secret"):
        return None
    sm = _boto3.client("secretsmanager", region_name=CONFIG["aws_region"])
    key = sm.get_secret_value(SecretId=CONFIG["cohere_api_key_secret"])["SecretString"]
    return cohere.Client(key)


def cohere_rerank(query: str, results: List[Dict]) -> List[Dict]:
    """Re-rank using Cohere Rerank API; attach relevance_score as citation score."""
    client = _get_cohere_client()
    if not client or not results:
        return results
    docs = [r["content"][:512] for r in results]
    response = client.rerank(model="rerank-english-v3.0", query=query, documents=docs, top_n=len(docs))
    reranked = []
    for item in response.results:
        r = results[item.index].copy()
        r["relevance_score"] = round(item.relevance_score, 4)
        r["citation"] = {
            "source": r.get("metadata", {}).get("document_path", "unknown"),
            "chunk_id": r.get("metadata", {}).get("chunk_id", 0),
            "relevance_score": r["relevance_score"],
        }
        reranked.append(r)
    return reranked


def llm_rerank(query: str, results: List[Dict]) -> List[Dict]:
    """LLM-based re-ranking with relevance scores when Cohere is unavailable."""
    if len(results) <= 1:
        return results
    candidates = [{"id": i, "text": r["content"][:400]} for i, r in enumerate(results[:20])]
    prompt = (
        f"Re-rank these passages by relevance to the query. "
        f"Return a JSON array of objects: [{{\"id\": 0, \"score\": 0.95}}, ...]\n\n"
        f"Query: {query}\n\nPassages:\n" +
        "\n".join(f"ID {c['id']}: {c['text']}" for c in candidates)
    )
    try:
        resp = _bedrock.invoke_model(
            modelId=CONFIG["fast_llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.0,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        text = json.loads(resp["body"].read())["content"][0]["text"]
        start, end = text.find("["), text.rfind("]") + 1
        ranked = json.loads(text[start:end])
        ranked.sort(key=lambda x: x["score"], reverse=True)
        reranked = []
        for item in ranked:
            if item["id"] < len(results):
                r = results[item["id"]].copy()
                r["relevance_score"] = round(item["score"], 4)
                r["citation"] = {
                    "source": r.get("metadata", {}).get("document_path", "unknown"),
                    "chunk_id": r.get("metadata", {}).get("chunk_id", 0),
                    "relevance_score": r["relevance_score"],
                }
                reranked.append(r)
        return reranked or results
    except Exception:
        return results


def rerank(query: str, results: List[Dict]) -> List[Dict]:
    """Try Cohere first, fall back to LLM re-ranking."""
    try:
        reranked = cohere_rerank(query, results)
        if reranked:
            return reranked
    except Exception:
        pass
    return llm_rerank(query, results)
