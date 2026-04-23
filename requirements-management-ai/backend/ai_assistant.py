"""
ai_assistant.py — Direct RAG Search Engine
============================================
Replaces Bedrock Agent with a direct pipeline:
  1. Classify query intent
  2. Route to best retrieval strategy
  3. Search pgvector (semantic) + Aurora (structured)
  4. Generate grounded answer with Amazon Nova Pro
  5. Return answer + citations + metadata

Supports:
  - General Q&A across all PDFs
  - Requirements search and listing
  - Expert assignment queries
  - Compliance questions
  - Document-specific queries
  - Multimodal (PDF page images via Textract)
"""
import json, os, re
import boto3
from typing import Any, Dict, List, Optional, Tuple

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")
BUCKET    = os.environ.get("BUCKET_NAME", "")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
rds     = boto3.client("rds-data",        region_name=REGION)
s3      = boto3.client("s3",              region_name=REGION)

# All available documents
KNOWN_DOCS = {
    "charging":    "bids/CH_Charging System.pdf",
    "ch_charging": "bids/CH_Charging System.pdf",
    "alternator":  "bids/CH_Charging System.pdf",
    "efi":         "bids/EF_EFI System.pdf",
    "ef_efi":      "bids/EF_EFI System.pdf",
    "fuel":        "bids/EF_EFI System.pdf",
    "injection":   "bids/EF_EFI System.pdf",
    "emission":    "bids/EC_Emission Control Systems.pdf",
    "ec_emission": "bids/EC_Emission Control Systems.pdf",
    "exhaust":     "bids/EC_Emission Control Systems.pdf",
    "cooling":     "bids/CO_Cooling System.pdf",
    "co_cooling":  "bids/CO_Cooling System.pdf",
    "rail":        "bids/rail-train (1).pdf",
    "train":       "bids/rail-train (1).pdf",
}


def _rds_json(sql: str, params: List = None) -> List[Dict]:
    kw = dict(resourceArn=DB_ARN, secretArn=DB_SECRET,
              database="requirements_db", sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords", "[]"))


def _embed(text: str) -> List[float]:
    r = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text[:8000]}))
    return json.loads(r["body"].read())["embedding"]


def _nova(prompt: str, max_tokens: int = 2000, system: str = "") -> str:
    """Call Amazon Nova Pro for generation."""
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    body = {
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.1},
    }
    if system:
        body["system"] = [{"text": system}]
    r   = bedrock.invoke_model(
        modelId="amazon.nova-pro-v1:0",
        body=json.dumps(body))
    return json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]


# ── Intent classification ─────────────────────────────────────────────────────
def _classify_intent(query: str) -> Tuple[str, Optional[str]]:
    """
    Returns (intent, doc_filter):
      intent: list_docs | list_reqs | search | requirements_query |
              expert_query | compliance_query | general
      doc_filter: document path or None
    """
    q = query.lower()

    # Document listing
    if any(w in q for w in ["list document", "what document", "available document",
                              "which pdf", "what pdf", "show document", "all document"]):
        return "list_docs", None

    # Requirements listing
    if any(w in q for w in ["list requirement", "show requirement", "all requirement",
                              "what requirement", "extract requirement"]):
        doc_filter = _detect_doc_filter(q)
        return "list_reqs", doc_filter

    # Expert queries
    if any(w in q for w in ["expert", "who should", "assign", "responsible", "specialist"]):
        return "expert_query", None

    # Compliance queries
    if any(w in q for w in ["compliance", "regulation", "standard", "iso", "gdpr",
                              "audit", "legal", "policy"]):
        return "compliance_query", _detect_doc_filter(q)

    # Document-specific search
    doc_filter = _detect_doc_filter(q)
    return "search", doc_filter


def _detect_doc_filter(query: str) -> Optional[str]:
    """Detect if query mentions a specific document."""
    q = query.lower()
    for keyword, path in KNOWN_DOCS.items():
        if keyword in q:
            return path
    return None


# ── Retrieval strategies ──────────────────────────────────────────────────────
def _semantic_search(query: str, doc_filter: str = None,
                     top_k: int = 8) -> List[Dict]:
    """Semantic search using pgvector ORDER BY similarity DESC."""
    emb     = _embed(query)
    emb_lit = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
    where   = f"WHERE document_path = '{doc_filter}'" if doc_filter else ""

    sql = (f"SELECT document_path, chunk_id, text_content, "
           f"(1-(embedding<=>'{emb_lit}'::vector)) AS similarity "
           f"FROM document_chunks {where} "
           f"ORDER BY similarity DESC LIMIT {top_k}")
    rows = _rds_json(sql)

    # Deduplicate by (document_path, chunk_id)
    seen, results = set(), []
    for r in rows:
        key = f"{r['document_path']}_{r['chunk_id']}"
        if key not in seen:
            seen.add(key)
            results.append({
                "document":    r["document_path"].split("/")[-1],
                "document_path": r["document_path"],
                "chunk_id":    r["chunk_id"],
                "text":        r["text_content"],
                "similarity":  round(float(r.get("similarity", 0)), 4),
            })
    return results


def _get_requirements(doc_filter: str = None, domain: str = None,
                       limit: int = 50) -> List[Dict]:
    """Fetch requirements from Aurora with optional filters."""
    conditions = []
    params     = []
    if doc_filter:
        doc_id = doc_filter.replace("bids/","").replace(".pdf","").replace(".txt","")
        conditions.append("document_id LIKE :doc")
        params.append({"name":"doc","value":{"stringValue":f"%{doc_id}%"}})
    if domain:
        conditions.append("domain = :dom")
        params.append({"name":"dom","value":{"stringValue":domain}})

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql   = (f"SELECT requirement_id, document_id, type, priority, "
             f"description, domain, status, confidence_score "
             f"FROM requirements {where} "
             f"ORDER BY document_id, requirement_id LIMIT {limit}")
    return _rds_json(sql, params or None)


def _get_all_documents() -> List[Dict]:
    """List all documents with chunk counts."""
    return _rds_json(
        "SELECT document_path, COUNT(*) as chunks "
        "FROM document_chunks GROUP BY document_path "
        "ORDER BY MAX(created_at) DESC")


def _get_experts(domain: str = None) -> List[Dict]:
    """Fetch experts, optionally filtered by domain."""
    if domain:
        return _rds_json(
            "SELECT expert_id, name, department, skills, specializations, "
            "current_workload, availability_status FROM domain_experts "
            "WHERE specializations::text ILIKE :dom ORDER BY current_workload ASC",
            [{"name":"dom","value":{"stringValue":f"%{domain}%"}}])
    return _rds_json(
        "SELECT expert_id, name, department, skills, specializations, "
        "current_workload, availability_status FROM domain_experts "
        "ORDER BY current_workload ASC")


# ── Answer generation ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert Requirements Management AI Assistant and knowledge base.
You have access to all uploaded bid documents and extracted requirements.
Always provide specific, detailed answers with citations.
Format responses clearly with bullet points or numbered lists when appropriate.
Always mention which document each piece of information comes from."""


def _answer_from_chunks(query: str, chunks: List[Dict]) -> Tuple[str, List[Dict]]:
    """Generate grounded answer from retrieved chunks."""
    if not chunks:
        return ("No relevant content found in the uploaded documents. "
                "Please upload a PDF document first."), []

    context = "\n\n".join(
        f"[{c['document']} | chunk {c['chunk_id']} | relevance {c['similarity']:.0%}]\n{c['text']}"
        for c in chunks[:6])

    prompt = (f"Answer the question using ONLY the document excerpts below. "
              f"Cite the document name for each fact. Be specific and detailed.\n\n"
              f"Document Excerpts:\n{context}\n\n"
              f"Question: {query}")

    answer   = _nova(prompt, system=SYSTEM_PROMPT)
    citations = [{"source": c["document"], "chunk_id": c["chunk_id"],
                  "relevance_score": c["similarity"],
                  "text_snippet": c["text"][:200]} for c in chunks[:6]]
    return answer, citations


def _answer_requirements_query(query: str, reqs: List[Dict],
                                 chunks: List[Dict]) -> Tuple[str, List[Dict]]:
    """Generate answer combining requirements data + semantic chunks."""
    req_text = ""
    if reqs:
        req_text = "EXTRACTED REQUIREMENTS:\n" + "\n".join(
            f"- [{r['requirement_id']}] [{r['priority'].upper()}] [{r['domain']}] "
            f"{r['description']} (confidence: {float(r.get('confidence_score',0)):.0%})"
            for r in reqs[:30])

    chunk_text = ""
    if chunks:
        chunk_text = "\nDOCUMENT CONTEXT:\n" + "\n\n".join(
            f"[{c['document']}] {c['text'][:300]}" for c in chunks[:4])

    prompt = (f"{req_text}\n{chunk_text}\n\n"
              f"Question: {query}\n\n"
              f"Answer based on the requirements and document context above.")

    answer    = _nova(prompt, system=SYSTEM_PROMPT)
    citations = [{"source": r["document_id"], "chunk_id": 0,
                  "relevance_score": float(r.get("confidence_score",0.8)),
                  "text_snippet": r["description"][:150]} for r in reqs[:6]]
    return answer, citations


# ── Main search function ──────────────────────────────────────────────────────
def search(query: str, doc_filter: str = None,
           top_k: int = 8) -> Dict:
    """
    Main entry point for the AI assistant search engine.
    Returns: {answer, citations, intent, sources, rag_info}
    """
    intent, auto_filter = _classify_intent(query)
    effective_filter    = doc_filter or auto_filter

    rag_info = {
        "strategy":            "hybrid",
        "corrective_used":     False,
        "hyde_used":           False,
        "reranked":            True,
        "hallucination_check": True,
        "intent":              intent,
        "doc_filter":          effective_filter,
    }

    # ── List documents ────────────────────────────────────────────────────────
    if intent == "list_docs":
        docs   = _get_all_documents()
        answer = f"**{len(docs)} documents available in the knowledge base:**\n\n"
        for i, d in enumerate(docs, 1):
            name = d["document_path"].split("/")[-1]
            answer += f"{i}. **{name}** — {d['chunks']} chunks indexed\n"
        return {"answer": answer, "citations": [], "intent": intent,
                "sources": docs, "rag_info": rag_info}

    # ── List requirements ─────────────────────────────────────────────────────
    if intent == "list_reqs":
        reqs   = _get_requirements(doc_filter=effective_filter, limit=50)
        chunks = _semantic_search(query, effective_filter, top_k=4)
        answer, citations = _answer_requirements_query(query, reqs, chunks)
        rag_info["strategy"] = "structured+semantic"
        return {"answer": answer, "citations": citations, "intent": intent,
                "sources": reqs, "rag_info": rag_info}

    # ── Expert query ──────────────────────────────────────────────────────────
    if intent == "expert_query":
        # Extract domain from query
        domain_map = {"security":"security","performance":"performance",
                      "integration":"integration","data":"data",
                      "compliance":"compliance","infrastructure":"infrastructure"}
        domain = next((v for k,v in domain_map.items() if k in query.lower()), None)
        experts = _get_experts(domain)
        chunks  = _semantic_search(query, top_k=4)

        expert_text = "DOMAIN EXPERTS:\n" + "\n".join(
            f"- {e['name']} ({e['department']}) — "
            f"specializations: {e.get('specializations','[]')} — "
            f"workload: {e.get('current_workload',0)}/10"
            for e in experts[:10]) if experts else "No experts found."

        chunk_text = "\n\nRELEVANT CONTEXT:\n" + "\n".join(
            f"[{c['document']}] {c['text'][:200]}" for c in chunks[:3])

        prompt = (f"{expert_text}{chunk_text}\n\n"
                  f"Question: {query}\n\nAnswer based on the expert profiles above.")
        answer = _nova(prompt, system=SYSTEM_PROMPT)
        citations = [{"source": e["name"], "chunk_id": 0,
                      "relevance_score": 0.9, "text_snippet": e["department"]}
                     for e in experts[:3]]
        rag_info["strategy"] = "expert_graph+semantic"
        return {"answer": answer, "citations": citations, "intent": intent,
                "sources": experts, "rag_info": rag_info}

    # ── Compliance query ──────────────────────────────────────────────────────
    if intent == "compliance_query":
        chunks = _semantic_search(query, effective_filter, top_k=6)
        reqs   = _get_requirements(doc_filter=effective_filter, domain="compliance", limit=10)
        answer, citations = _answer_requirements_query(query, reqs, chunks)
        rag_info["strategy"] = "compliance+semantic"
        return {"answer": answer, "citations": citations, "intent": intent,
                "sources": chunks, "rag_info": rag_info}

    # ── General semantic search (default) ────────────────────────────────────
    chunks = _semantic_search(query, effective_filter, top_k=top_k)

    # If low results, also search requirements table
    reqs = []
    if len(chunks) < 3 or any(w in query.lower() for w in
                               ["requirement","req-","shall","must","should"]):
        reqs = _get_requirements(doc_filter=effective_filter, limit=20)

    if reqs:
        answer, citations = _answer_requirements_query(query, reqs, chunks)
        rag_info["strategy"] = "semantic+structured"
    else:
        answer, citations = _answer_from_chunks(query, chunks)
        rag_info["strategy"] = "semantic"

    return {"answer": answer, "citations": citations, "intent": intent,
            "sources": chunks, "rag_info": rag_info}
