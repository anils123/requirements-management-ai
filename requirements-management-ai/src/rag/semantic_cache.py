import json
import hashlib
import redis
import numpy as np
from typing import Any, List, Optional
from ..utils.config import CONFIG
from ..utils.embeddings import embed_text, cosine_similarity

_redis = redis.Redis(
    host=CONFIG["redis_endpoint"],
    port=CONFIG["redis_port"],
    decode_responses=True,
    socket_connect_timeout=2,
)

_EMBEDDING_KEY = "cache:embeddings"   # Redis hash: query_hash -> embedding JSON
_RESULT_KEY    = "cache:results"      # Redis hash: query_hash -> result JSON
_TTL           = CONFIG["cache_ttl_seconds"]
_SIM_THRESHOLD = CONFIG["cache_similarity_threshold"]


class SemanticCache:
    def get(self, query: str) -> Optional[Any]:
        try:
            query_emb = embed_text(query)
            all_hashes = _redis.hkeys(_EMBEDDING_KEY)
            best_score, best_hash = 0.0, None
            for h in all_hashes:
                stored_emb = json.loads(_redis.hget(_EMBEDDING_KEY, h))
                score = cosine_similarity(query_emb, stored_emb)
                if score > best_score:
                    best_score, best_hash = score, h
            if best_score >= _SIM_THRESHOLD and best_hash:
                raw = _redis.hget(_RESULT_KEY, best_hash)
                return json.loads(raw) if raw else None
        except Exception:
            pass
        return None

    def set(self, query: str, value: Any) -> None:
        try:
            query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
            query_emb  = embed_text(query)
            _redis.hset(_EMBEDDING_KEY, query_hash, json.dumps(query_emb))
            _redis.hset(_RESULT_KEY,    query_hash, json.dumps(value, default=str))
            _redis.expire(_EMBEDDING_KEY, _TTL)
            _redis.expire(_RESULT_KEY,    _TTL)
        except Exception:
            pass

    def invalidate(self, query: str) -> None:
        try:
            query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
            _redis.hdel(_EMBEDDING_KEY, query_hash)
            _redis.hdel(_RESULT_KEY,    query_hash)
        except Exception:
            pass
