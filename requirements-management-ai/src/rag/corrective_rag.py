import json
import boto3
import numpy as np
from typing import List, Dict, Any, Tuple
from ..utils.config import CONFIG

_bedrock = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])
_RELEVANCE_THRESHOLD = CONFIG["relevance_threshold"]


# ── Corrective RAG ────────────────────────────────────────────────────────────

def evaluate_relevance(query: str, results: List[Dict]) -> List[float]:
    """Score each result 0-1 for relevance to the query using the LLM."""
    if not results:
        return []
    snippets = "\n\n".join(
        f"[{i}] {r['content'][:300]}" for i, r in enumerate(results[:6])
    )
    prompt = (
        f"Rate each passage's relevance to the query on a scale 0.0-1.0.\n"
        f"Query: {query}\n\nPassages:\n{snippets}\n\n"
        f"Return ONLY a JSON array of floats, one per passage: [0.9, 0.4, ...]"
    )
    try:
        resp = _bedrock.invoke_model(
            modelId=CONFIG["fast_llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.0,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        text = json.loads(resp["body"].read())["content"][0]["text"]
        start, end = text.find("["), text.rfind("]") + 1
        return json.loads(text[start:end])
    except Exception:
        return [0.5] * len(results)


def rewrite_query(query: str) -> List[str]:
    """Generate 3 alternative query rewrites for self-healing retrieval."""
    prompt = (
        f"Rewrite the following query in 3 different ways to improve document retrieval. "
        f"Use synonyms, expand acronyms, and vary specificity.\n\n"
        f"Original: {query}\n\n"
        f"Return ONLY a JSON array: [\"rewrite1\", \"rewrite2\", \"rewrite3\"]"
    )
    try:
        resp = _bedrock.invoke_model(
            modelId=CONFIG["fast_llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 250,
                "temperature": 0.3,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        text = json.loads(resp["body"].read())["content"][0]["text"]
        start, end = text.find("["), text.rfind("]") + 1
        return json.loads(text[start:end])
    except Exception:
        return [query]


def needs_correction(results: List[Dict], query: str) -> bool:
    if not results:
        return True
    scores = evaluate_relevance(query, results[:3])
    return bool(scores) and float(np.mean(scores)) < _RELEVANCE_THRESHOLD


# ── Self-Reflective RAG ───────────────────────────────────────────────────────

def detect_hallucination(answer: str, context_chunks: List[Dict]) -> Tuple[bool, float]:
    """
    Check whether the answer is grounded in the retrieved context.
    Returns (is_hallucination, confidence_score).
    """
    context = "\n\n".join(c["content"][:400] for c in context_chunks[:5])
    prompt = (
        f"Does the following answer contain claims NOT supported by the context? "
        f"Reply with JSON: {{\"hallucination\": true/false, \"confidence\": 0.0-1.0}}\n\n"
        f"Context:\n{context}\n\nAnswer:\n{answer}"
    )
    try:
        resp = _bedrock.invoke_model(
            modelId=CONFIG["fast_llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 80,
                "temperature": 0.0,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        text = json.loads(resp["body"].read())["content"][0]["text"]
        start, end = text.find("{"), text.rfind("}") + 1
        data = json.loads(text[start:end])
        return data.get("hallucination", False), data.get("confidence", 0.5)
    except Exception:
        return False, 0.5


def self_reflect_and_regenerate(query: str, answer: str,
                                 context_chunks: List[Dict],
                                 max_attempts: int = 2) -> str:
    """
    If hallucination is detected, regenerate the answer with stricter grounding.
    Returns the final (grounded) answer.
    """
    for _ in range(max_attempts):
        is_hallucination, _ = detect_hallucination(answer, context_chunks)
        if not is_hallucination:
            break
        context = "\n\n".join(
            f"[Source {i+1}] {c['content'][:500]}" for i, c in enumerate(context_chunks[:5])
        )
        prompt = (
            f"Answer the question using ONLY the provided sources. "
            f"Do not add information not present in the sources.\n\n"
            f"Sources:\n{context}\n\nQuestion: {query}"
        )
        resp = _bedrock.invoke_model(
            modelId=CONFIG["llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.1,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        answer = json.loads(resp["body"].read())["content"][0]["text"]
    return answer
