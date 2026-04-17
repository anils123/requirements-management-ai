# src/rag/hybrid_search.py
import json
import boto3
import numpy as np
from typing import Dict, List, Any, Tuple
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth
import redis

class HybridSearchEngine:
    """Advanced hybrid search engine with multiple RAG techniques."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bedrock_client = boto3.client('bedrock-runtime')
        self.opensearch_client = self._init_opensearch()
        self.redis_client = self._init_redis()
        self.rds_client = boto3.client('rds-data')
        
    def _init_opensearch(self) -> OpenSearch:
        """Initialize OpenSearch client."""
        host = self.config['opensearch_endpoint']
        region = self.config['aws_region']
        service = 'aoss'
        credentials = boto3.Session().get_credentials()
        awsauth = AWSRequestsAuth(credentials, region, service)
        
        return OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )
    
    def _init_redis(self) -> redis.Redis:
        """Initialize Redis client for semantic caching."""
        return redis.Redis(
            host=self.config['redis_endpoint'],
            port=6379,
            decode_responses=True
        )
    
    def hybrid_search(self, query: str, filters: Dict = None, 
                     top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector similarity and full-text search.
        """
        # Check semantic cache first
        cached_result = self._check_semantic_cache(query)
        if cached_result:
            return cached_result
        
        # Classify query to determine search strategy
        search_strategy = self._classify_query(query)
        
        # Perform search based on strategy
        if search_strategy == 'vector_only':
            results = self._vector_search(query, filters, top_k)
        elif search_strategy == 'text_only':
            results = self._text_search(query, filters, top_k)
        elif search_strategy == 'decomposed':
            results = self._decomposed_search(query, filters, top_k)
        else:  # hybrid
            results = self._hybrid_search_core(query, filters, top_k)
        
        # Apply corrective RAG if needed
        if self._needs_correction(results, query):
            results = self._corrective_rag(query, results, filters, top_k)
        
        # Re-rank results
        results = self._rerank_results(query, results)
        
        # Cache results
        self._cache_results(query, results)
        
        return results
    
    def _hybrid_search_core(self, query: str, filters: Dict, 
                           top_k: int) -> List[Dict[str, Any]]:
        """Core hybrid search implementation."""
        
        # Generate query embedding
        query_embedding = self._generate_embedding(query)
        
        # Vector search
        vector_results = self._vector_search_raw(query_embedding, filters, top_k)
        
        # Full-text search
        text_results = self._text_search_raw(query, filters, top_k)
        
        # Apply Reciprocal Rank Fusion (RRF)
        fused_results = self._reciprocal_rank_fusion(
            vector_results, text_results, k=60
        )
        
        return fused_results[:top_k]
    
    def _vector_search_raw(self, embedding: List[float], filters: Dict, 
                          top_k: int) -> List[Dict[str, Any]]:
        """Perform vector similarity search."""
        
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "vector_field": {
                                    "vector": embedding,
                                    "k": top_k
                                }
                            }
                        }
                    ]
                }
            },
            "_source": ["text", "metadata", "document_id", "chunk_id"]
        }
        
        # Add filters
        if filters:
            search_body["query"]["bool"]["filter"] = self._build_filters(filters)
        
        response = self.opensearch_client.search(
            index="requirements-index",
            body=search_body
        )
        
        results = []
        for i, hit in enumerate(response['hits']['hits']):
            results.append({
                'content': hit['_source']['text'],
                'metadata': hit['_source']['metadata'],
                'score': hit['_score'],
                'rank': i + 1,
                'search_type': 'vector'
            })
        
        return results
    
    def _text_search_raw(self, query: str, filters: Dict, 
                        top_k: int) -> List[Dict[str, Any]]:
        """Perform full-text search using BM25."""
        
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["text^2", "metadata.title", "metadata.category"],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        }
                    ]
                }
            },
            "_source": ["text", "metadata", "document_id", "chunk_id"]
        }
        
        # Add filters
        if filters:
            search_body["query"]["bool"]["filter"] = self._build_filters(filters)
        
        response = self.opensearch_client.search(
            index="requirements-index",
            body=search_body
        )
        
        results = []
        for i, hit in enumerate(response['hits']['hits']):
            results.append({
                'content': hit['_source']['text'],
                'metadata': hit['_source']['metadata'],
                'score': hit['_score'],
                'rank': i + 1,
                'search_type': 'text'
            })
        
        return results
    
    def _reciprocal_rank_fusion(self, list1: List[Dict], list2: List[Dict], 
                               k: int = 60) -> List[Dict[str, Any]]:
        """Apply Reciprocal Rank Fusion to combine search results."""
        
        # Create document ID to result mapping
        doc_scores = {}
        
        # Process first list (vector results)
        for rank, result in enumerate(list1, 1):
            doc_id = self._get_doc_id(result)
            rrf_score = 1 / (k + rank)
            doc_scores[doc_id] = {
                'result': result,
                'rrf_score': rrf_score,
                'vector_rank': rank,
                'text_rank': None
            }
        
        # Process second list (text results)
        for rank, result in enumerate(list2, 1):
            doc_id = self._get_doc_id(result)
            rrf_score = 1 / (k + rank)
            
            if doc_id in doc_scores:
                doc_scores[doc_id]['rrf_score'] += rrf_score
                doc_scores[doc_id]['text_rank'] = rank
            else:
                doc_scores[doc_id] = {
                    'result': result,
                    'rrf_score': rrf_score,
                    'vector_rank': None,
                    'text_rank': rank
                }
        
        # Sort by RRF score
        sorted_results = sorted(
            doc_scores.values(),
            key=lambda x: x['rrf_score'],
            reverse=True
        )
        
        # Return results with RRF metadata
        fused_results = []
        for item in sorted_results:
            result = item['result'].copy()
            result['rrf_score'] = item['rrf_score']
            result['vector_rank'] = item['vector_rank']
            result['text_rank'] = item['text_rank']
            result['search_type'] = 'hybrid'
            fused_results.append(result)
        
        return fused_results
    
    def _corrective_rag(self, query: str, results: List[Dict], 
                       filters: Dict, top_k: int) -> List[Dict[str, Any]]:
        """Apply Corrective RAG for self-healing retrieval."""
        
        # Evaluate relevance of current results
        relevance_scores = self._evaluate_relevance(query, results)
        
        # If relevance is low, try alternative strategies
        avg_relevance = np.mean(relevance_scores) if relevance_scores else 0
        
        if avg_relevance < 0.6:  # Threshold for correction
            # Try query rewriting
            rewritten_queries = self._rewrite_query(query)
            
            corrected_results = []
            for rewritten_query in rewritten_queries:
                new_results = self._hybrid_search_core(
                    rewritten_query, filters, top_k // 2
                )
                corrected_results.extend(new_results)
            
            # Combine original and corrected results
            all_results = results + corrected_results
            
            # Remove duplicates and re-rank
            unique_results = self._remove_duplicates(all_results)
            return self._rerank_results(query, unique_results)[:top_k]
        
        return results
    
    def _evaluate_relevance(self, query: str, results: List[Dict]) -> List[float]:
        """Evaluate relevance of search results using LLM."""
        
        if not results:
            return []
        
        # Prepare evaluation prompt
        results_text = "\n\n".join([
            f"Result {i+1}: {result['content'][:200]}..."
            for i, result in enumerate(results[:5])  # Evaluate top 5
        ])
        
        prompt = f"""
        Evaluate the relevance of these search results to the query.
        
        Query: {query}
        
        Results:
        {results_text}
        
        Rate each result's relevance on a scale of 0.0 to 1.0.
        Return only a JSON array of scores: [0.8, 0.6, 0.9, 0.3, 0.7]
        """
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-haiku-20240307-v1:0',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 100,
                    'temperature': 0.1
                })
            )
            
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            scores = json.loads(content)
            
            return scores
            
        except Exception as e:
            print(f"Error evaluating relevance: {e}")
            return [0.5] * len(results)  # Default neutral scores
    
    def _rewrite_query(self, query: str) -> List[str]:
        """Rewrite query for better retrieval."""
        
        prompt = f"""
        Rewrite this query in 3 different ways to improve search results:
        
        Original query: {query}
        
        Generate variations that:
        1. Use synonyms and alternative terms
        2. Expand with related concepts
        3. Simplify to core concepts
        
        Return as JSON array: ["rewrite1", "rewrite2", "rewrite3"]
        """
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-haiku-20240307-v1:0',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 200,
                    'temperature': 0.3
                })
            )
            
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            rewrites = json.loads(content)
            
            return rewrites
            
        except Exception as e:
            print(f"Error rewriting query: {e}")
            return [query]  # Return original if rewriting fails
    
    def _decomposed_search(self, query: str, filters: Dict, 
                          top_k: int) -> List[Dict[str, Any]]:
        """Decompose complex queries into sub-queries."""
        
        # Decompose query
        sub_queries = self._decompose_query(query)
        
        all_results = []
        for sub_query in sub_queries:
            sub_results = self._hybrid_search_core(
                sub_query, filters, top_k // len(sub_queries)
            )
            all_results.extend(sub_results)
        
        # Remove duplicates and re-rank
        unique_results = self._remove_duplicates(all_results)
        return self._rerank_results(query, unique_results)[:top_k]
    
    def _decompose_query(self, query: str) -> List[str]:
        """Decompose complex query into simpler sub-queries."""
        
        prompt = f"""
        Break down this complex query into 2-3 simpler sub-queries:
        
        Complex query: {query}
        
        Each sub-query should focus on a specific aspect of the original question.
        Return as JSON array: ["sub_query1", "sub_query2", "sub_query3"]
        """
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-haiku-20240307-v1:0',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 150,
                    'temperature': 0.2
                })
            )
            
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            sub_queries = json.loads(content)
            
            return sub_queries
            
        except Exception as e:
            print(f"Error decomposing query: {e}")
            return [query]
    
    def _rerank_results(self, query: str, results: List[Dict]) -> List[Dict[str, Any]]:
        """Re-rank results using LLM-based scoring."""
        
        if len(results) <= 1:
            return results
        
        # Prepare results for re-ranking
        results_for_ranking = []
        for i, result in enumerate(results[:20]):  # Re-rank top 20
            results_for_ranking.append({
                'id': i,
                'content': result['content'][:300],  # Truncate for efficiency
                'original_result': result
            })
        
        # LLM-based re-ranking
        reranked_ids = self._llm_rerank(query, results_for_ranking)
        
        # Reorder results
        reranked_results = []
        for rank_id in reranked_ids:
            if rank_id < len(results_for_ranking):
                original_result = results_for_ranking[rank_id]['original_result']
                original_result['rerank_score'] = len(reranked_ids) - reranked_ids.index(rank_id)
                reranked_results.append(original_result)
        
        # Add remaining results
        remaining_results = results[len(results_for_ranking):]
        reranked_results.extend(remaining_results)
        
        return reranked_results
    
    def _llm_rerank(self, query: str, results: List[Dict]) -> List[int]:
        """Use LLM to re-rank search results."""
        
        results_text = "\n\n".join([
            f"ID: {result['id']}\nContent: {result['content']}"
            for result in results
        ])
        
        prompt = f"""
        Re-rank these search results by relevance to the query.
        
        Query: {query}
        
        Results:
        {results_text}
        
        Return the IDs in order of relevance (most relevant first).
        Return as JSON array of integers: [2, 0, 5, 1, 3, 4]
        """
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 200,
                    'temperature': 0.1
                })
            )
            
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            ranked_ids = json.loads(content)
            
            return ranked_ids
            
        except Exception as e:
            print(f"Error in LLM re-ranking: {e}")
            return list(range(len(results)))  # Return original order
    
    def _check_semantic_cache(self, query: str) -> List[Dict[str, Any]]:
        """Check Redis semantic cache for similar queries."""
        
        try:
            # Generate query embedding for similarity search
            query_embedding = self._generate_embedding(query)
            
            # Search for similar cached queries (simplified implementation)
            # In production, use Redis with vector similarity search
            cache_key = f"query_cache:{hash(query) % 10000}"
            cached_result = self.redis_client.get(cache_key)
            
            if cached_result:
                return json.loads(cached_result)
            
        except Exception as e:
            print(f"Cache lookup error: {e}")
        
        return None
    
    def _cache_results(self, query: str, results: List[Dict]):
        """Cache search results in Redis."""
        
        try:
            cache_key = f"query_cache:{hash(query) % 10000}"
            cache_value = json.dumps(results, default=str)
            
            # Cache for 1 hour
            self.redis_client.setex(cache_key, 3600, cache_value)
            
        except Exception as e:
            print(f"Cache storage error: {e}")
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        
        response = self.bedrock_client.invoke_model(
            modelId='amazon.titan-embed-text-v2:0',
            body=json.dumps({'inputText': text})
        )
        
        result = json.loads(response['body'].read())
        return result['embedding']
    
    def _classify_query(self, query: str) -> str:
        """Classify query to determine optimal search strategy."""
        
        # Simple classification based on query characteristics
        query_lower = query.lower()
        
        # Check for factual keywords
        factual_keywords = ['what', 'who', 'when', 'where', 'define', 'explain']
        if any(keyword in query_lower for keyword in factual_keywords):
            return 'vector_only'
        
        # Check for specific terms/IDs
        if any(char.isdigit() for char in query) and len(query.split()) <= 3:
            return 'text_only'
        
        # Check for complex multi-part questions
        if '?' in query and len(query.split()) > 10:
            return 'decomposed'
        
        return 'hybrid'
    
    def _needs_correction(self, results: List[Dict], query: str) -> bool:
        """Determine if corrective RAG is needed."""
        
        if not results:
            return True
        
        # Check if top results have low scores
        top_scores = [r.get('score', 0) for r in results[:3]]
        avg_top_score = np.mean(top_scores) if top_scores else 0
        
        return avg_top_score < 0.5  # Threshold for correction
    
    def _build_filters(self, filters: Dict) -> List[Dict]:
        """Build OpenSearch filters from filter dictionary."""
        
        filter_clauses = []
        
        for field, value in filters.items():
            if isinstance(value, list):
                filter_clauses.append({
                    "terms": {f"metadata.{field}": value}
                })
            else:
                filter_clauses.append({
                    "term": {f"metadata.{field}": value}
                })
        
        return filter_clauses
    
    def _get_doc_id(self, result: Dict) -> str:
        """Get unique document ID for deduplication."""
        
        metadata = result.get('metadata', {})
        return f"{metadata.get('document_id', 'unknown')}_{metadata.get('chunk_id', 0)}"
    
    def _remove_duplicates(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate results based on content similarity."""
        
        unique_results = []
        seen_ids = set()
        
        for result in results:
            doc_id = self._get_doc_id(result)
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_results.append(result)
        
        return unique_results
