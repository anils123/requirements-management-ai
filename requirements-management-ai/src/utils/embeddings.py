import json
import boto3
from typing import List, Union
from .config import CONFIG

_bedrock = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])

def embed_text(text: str) -> List[float]:
    resp = _bedrock.invoke_model(
        modelId=CONFIG["embedding_model"],
        body=json.dumps({"inputText": text[:8000]}),
    )
    return json.loads(resp["body"].read())["embedding"]

def embed_batch(texts: List[str]) -> List[List[float]]:
    return [embed_text(t) for t in texts]

def cosine_similarity(a: List[float], b: List[float]) -> float:
    import numpy as np
    va, vb = np.array(a), np.array(b)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom else 0.0
