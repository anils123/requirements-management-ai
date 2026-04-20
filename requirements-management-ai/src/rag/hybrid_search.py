"""
Hybrid Search Engine
====================
Combines:
  - Vector similarity (pgvector / OpenSearch kNN)
  - BM25 full-text (OpenSearch)
  - Reciprocal Rank Fusion (RRF)
  - Adaptive routing (vector / text / hybrid / decomposed)
  - HyDE (Hypothetical Document Embeddings)
  - Corrective RAG (CRAG) with query rewriting
  - Self-Reflective RAG (hallucination detection)
  - Query Decomposition
  - Knowledge Graph enrichment
  - Semantic Cache (Redis)
  - Re-ranking (Cohere + LLM fallback)
  - Grounded citations with relevance scores
"""
import json
import numpy as np
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from typing import Any, Dict, List, Optional

from ..utils.config import CONFIG
from ..utils.embeddings import embed_text
from .semantic_cache import SemanticCache
from .hyde import hyde_embedding
from .query_decomposition import decompose_query, is_complex_query
from .corrective_rag import (
    needs_correction, rewrite_query,
    self_reflect_and_regenerate, detect_hallucination,
)
from .reranking import rerank
from .knowledge_graph import enrich_results_with_graph


class HybridSearchEngine:
    def __init__(self):
        self.cache  = SemanticCache()
        self.os     = self._init_opensearch()
        self.index  = "requirements-index"

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_opensearch(self) -> OpenSearch:
        region = CONFIG["aws_region"]
        creds  = boto3.Session().get_credentials().resolve()
        auth   = AWS4Auth(creds.access_key, creds.secret_key, region, "aoss",
                          session_token=creds.token)
        return OpenSearch(
            hosts=[{"host": CONFIG["opensearch_endpoint"], "port": 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def search(self, query: str, filters: Dict = None,
               top_k: int = None, use_hyde: bool = False) -> List[Dict]:
        """
        Main entry point. Returns re-ranked results with grounded citations.
        """
        top_k = top_k or CONFIG["top_k"]

        # 1. Semantic cache
        cached = self.cache.get(query)
        if cached:
            return cached

        # 2. Adaptive routing
        strategy = self._classify_query(query)

        # 3. Retrieve
        if strategy == "decomposed" or is_complex_query(query):
            results = self._decomposed_search(query, filters, top_k)
        elif strategy == "vector_only":
            emb = hyde_embedding(query) if use_hyde else embed_text(query)
            results = self._vector_search(emb, filters, top_k)
        elif strategy == "text_only":
            results = self._text_search(query, filters, top_k)
        else:
            results = self._hybrid_core(query, filters, top_k, use_hyde)

        # 4. Corrective RAG
        if needs_correction(results, query):
            results = self._corrective_retrieve(query, results, filters, top_k)

        # 5. Knowledge Graph enrichment
        results = enrich_results_with_graph(results)

        # 6. Re-rank + attach citations
        results = rerank(query, results)

        # 7. Cache & return
        self.cache.set(query, results)
        return results[:top_k]

    def generate_grounded_answer(self, query: str,
                                  results: List[Dict]) -> Dict[str, Any]:
        """
        Generate an answer grounded in retrieved chunks with citations.
        Applies Self-Reflective RAG to detect and fix hallucinations.
        """
        context = "\n\n".join(
            f"[Source {i+1} | score={r.get('relevance_score', 0):.2f}] {r['content'][:600]}"
            for i, r in enumerate(results[:6])
        )
        bedrock = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])
        prompt  = (
            f"Answer the question using ONLY the provided sources. "
            f"Cite each claim as [Source N].\n\n"
            f"Sources:\n{context}\n\nQuestion: {query}"
        )
        resp   = bedrock.invoke_model(
            modelId=CONFIG["llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.1,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        answer = json.loads(resp["body"].read())["content"][0]["text"]

        # Self-Reflective RAG
        answer = self_reflect_and_regenerate(query, answer, results)

        citations = [
            r["citation"] for r in results if "citation" in r
        ]
        return {"answer": answer, "citations": citations, "sources_used": len(results)}

    # ── Core retrieval ────────────────────────────────────────────────────────

    def _hybrid_core(self, query: str, filters: Dict,
                     top_k: int, use_hyde: bool = False) -> List[Dict]:
        emb          = hyde_embedding(query) if use_hyde else embed_text(query)
        vec_results  = self._vector_search(emb, filters, top_k)
        text_results = self._text_search(query, filters, top_k)
        return self._rrf(vec_results, text_results)[:top_k]

    def _vector_search(self, embedding: List[float],
                       filters: Dict, top_k: int) -> List[Dict]:
        body = {
            "size": top_k,
            "query": {"bool": {"must": [{"knn": {"vector_field": {
                "vector": embedding, "k": top_k
            }}}]}},
            "_source": ["text", "metadata", "document_id", "chunk_id"],
        }
        if filters:
            body["query"]["bool"]["filter"] = self._build_filters(filters)
        hits = self.os.search(index=self.index, body=body)["hits"]["hits"]
        return [self._hit_to_result(h, i, "vector") for i, h in enumerate(hits)]

    def _text_search(self, query: str, filters: Dict, top_k: int) -> List[Dict]:
        body = {
            "size": top_k,
            "query": {"bool": {"must": [{"multi_match": {
                "query": query,
                "fields": ["text^2", "metadata.title", "metadata.category"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }}]}},
            "_source": ["text", "metadata", "document_id", "chunk_id"],
        }
        if filters:
            body["query"]["bool"]["filter"] = self._build_filters(filters)
        hits = self.os.search(index=self.index, body=body)["hits"]["hits"]
        return [self._hit_to_result(h, i, "text") for i, h in enumerate(hits)]

    def _decomposed_search(self, query: str, filters: Dict,
                           top_k: int) -> List[Dict]:
        sub_queries = decompose_query(query)
        all_results: List[Dict] = []
        per_query   = max(top_k // len(sub_queries), 3)
        for sq in sub_queries:
            all_results.extend(self._hybrid_core(sq, filters, per_query))
        return self._deduplicate(all_results)[:top_k]

    def _corrective_retrieve(self, query: str, results: List[Dict],
                              filters: Dict, top_k: int) -> List[Dict]:
        rewrites = rewrite_query(query)
        extra: List[Dict] = []
        for rq in rewrites:
            extra.extend(self._hybrid_core(rq, filters, top_k // 2))
        merged = self._deduplicate(results + extra)
        return merged[:top_k]

    # ── RRF ───────────────────────────────────────────────────────────────────

    def _rrf(self, list1: List[Dict], list2: List[Dict],
             k: int = None) -> List[Dict]:
        k = k or CONFIG["rrf_k"]
        scores: Dict[str, Dict] = {}
        for rank, r in enumerate(list1, 1):
            did = self._doc_id(r)
            scores.setdefault(did, {"result": r, "rrf": 0.0})
            scores[did]["rrf"] += 1 / (k + rank)
        for rank, r in enumerate(list2, 1):
            did = self._doc_id(r)
            scores.setdefault(did, {"result": r, "rrf": 0.0})
            scores[did]["rrf"] += 1 / (k + rank)
        sorted_items = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)
        out = []
        for item in sorted_items:
            r = item["result"].copy()
            r["rrf_score"]   = round(item["rrf"], 6)
            r["search_type"] = "hybrid"
            out.append(r)
        return out

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _classify_query(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["what is", "define", "explain", "who is"]):
            return "vector_only"
        if len(query.split()) <= 4 and any(c.isdigit() for c in query):
            return "text_only"
        if is_complex_query(query):
            return "decomposed"
        return "hybrid"

    def _build_filters(self, filters: Dict) -> List[Dict]:
        clauses = []
        for field, value in filters.items():
            key = f"metadata.{field}"
            clauses.append(
                {"terms": {key: value}} if isinstance(value, list)
                else {"term": {key: value}}
            )
        return clauses

    def _hit_to_result(self, hit: Dict, rank: int, search_type: str) -> Dict:
        src = hit["_source"]
        return {
            "content":     src.get("text", ""),
            "metadata":    src.get("metadata", {}),
            "score":       hit.get("_score", 0.0),
            "rank":        rank + 1,
            "search_type": search_type,
        }

    def _doc_id(self, result: Dict) -> str:
        m = result.get("metadata", {})
        return f"{m.get('document_id','?')}_{m.get('chunk_id', 0)}"

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:
        seen, out = set(), []
        for r in results:
            did = self._doc_id(r)
            if did not in seen:
                seen.add(did)
                out.append(r)
        return out
