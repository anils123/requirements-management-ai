import json
import boto3
from typing import List
from ..utils.config import CONFIG

_bedrock = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])


def decompose_query(query: str) -> List[str]:
    """Break a complex multi-hop query into 2-4 focused sub-queries."""
    prompt = (
        "You are a query decomposition expert. Break the following complex question "
        "into 2-4 simpler, self-contained sub-queries. Each sub-query should be "
        "answerable independently and together they should cover the full question.\n\n"
        f"Question: {query}\n\n"
        "Return ONLY a JSON array of strings: [\"sub1\", \"sub2\", ...]"
    )
    try:
        resp = _bedrock.invoke_model(
            modelId=CONFIG["fast_llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.1,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        text = json.loads(resp["body"].read())["content"][0]["text"]
        # Extract JSON array even if wrapped in markdown
        start, end = text.find("["), text.rfind("]") + 1
        return json.loads(text[start:end]) if start != -1 else [query]
    except Exception:
        return [query]


def is_complex_query(query: str) -> bool:
    """Heuristic: multi-part questions with conjunctions or multiple '?' are complex."""
    tokens = query.split()
    conjunctions = {"and", "also", "additionally", "furthermore", "as well as"}
    return (
        len(tokens) > 12
        or query.count("?") > 1
        or any(c in query.lower() for c in conjunctions)
    )
