"""
Document Search Lambda — semantic search across all uploaded PDFs.
Fix: ORDER BY similarity DESC (not embedding<=>... ASC) for RDS Data API.
"""
import json, os
import boto3
from typing import Any

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
rds     = boto3.client("rds-data",        region_name=REGION)


def _parse_event(event):
    if "requestBody" in event:
        props = event.get("requestBody",{}).get("content",{}) \
                     .get("application/json",{}).get("properties",[])
        return {p["name"]: p["value"] for p in props}
    if "body" in event and event["body"]:
        try: return json.loads(event["body"])
        except: pass
    return event

def _wrap(event, body):
    if "actionGroup" not in event: return body
    return {"messageVersion":"1.0","response":{
        "actionGroup":event.get("actionGroup",""),
        "apiPath":event.get("apiPath",""),
        "httpMethod":event.get("httpMethod","POST"),
        "httpStatusCode":200,
        "responseBody":{"application/json":{"body":json.dumps(body)}},
    }}

def _rds_json(sql, params=None):
    kw = dict(resourceArn=DB_ARN, secretArn=DB_SECRET,
              database="requirements_db", sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords", "[]"))

def _embed(text):
    r = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                             body=json.dumps({"inputText": text[:8000]}))
    return json.loads(r["body"].read())["embedding"]


def _list_documents():
    try:
        rows = _rds_json(
            "SELECT document_path, COUNT(*) as chunks "
            "FROM document_chunks GROUP BY document_path "
            "ORDER BY MAX(created_at) DESC")
        return [{"document_name": r["document_path"].split("/")[-1],
                 "document_path": r["document_path"],
                 "chunks": r["chunks"]} for r in rows]
    except Exception as e:
        print(f"List docs error: {e}"); return []


def _list_requirements(doc_filter=""):
    try:
        if doc_filter:
            rows = _rds_json(
                "SELECT requirement_id,document_id,type,priority,description,domain,status "
                "FROM requirements WHERE document_id LIKE :d ORDER BY requirement_id",
                [{"name":"d","value":{"stringValue":f"%{doc_filter}%"}}])
        else:
            rows = _rds_json(
                "SELECT requirement_id,document_id,type,priority,description,domain,status "
                "FROM requirements ORDER BY document_id,requirement_id LIMIT 200")
        return rows
    except Exception as e:
        print(f"List reqs error: {e}"); return []


def _semantic_search(query, top_k=8, doc_filter=""):
    """
    Semantic search using pgvector cosine similarity.
    Uses ORDER BY similarity DESC — ORDER BY embedding<=>... ASC returns 0 rows
    with RDS Data API formatRecordsAs=JSON due to operator handling.
    """
    try:
        print(f"Embedding: {query[:50]}")
        emb     = _embed(query)
        emb_lit = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
        where   = f"WHERE document_path LIKE '%{doc_filter}%'" if doc_filter else ""

        sql = (
            f"SELECT document_path, chunk_id, text_content, "
            f"(1-(embedding<=>'{emb_lit}'::vector)) AS similarity "
            f"FROM document_chunks {where} "
            f"ORDER BY similarity DESC "
            f"LIMIT {top_k}"
        )
        print(f"SQL length: {len(sql)}")
        rows = _rds_json(sql)
        print(f"Found {len(rows)} results")
        # Deduplicate by (document_path, chunk_id) — keep highest similarity
        seen, deduped = set(), []
        for r in rows:
            key = f"{r['document_path']}_{r['chunk_id']}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return [{"document":      r["document_path"].split("/")[-1],
                 "document_path": r["document_path"],
                 "chunk_id":      r["chunk_id"],
                 "text":          r["text_content"],
                 "similarity":    round(float(r.get("similarity", 0)), 4)}
                for r in deduped]
    except Exception as e:
        print(f"Search error: {e}"); return []


def _answer(query, chunks):
    if not chunks:
        return "No relevant content found across the uploaded documents."
    context = "\n\n".join(
        f"[{c['document']} | score={c['similarity']}]\n{c['text']}"
        for c in chunks[:6])
    prompt = (
        f"Answer the question using ONLY the document excerpts below. "
        f"Cite the document name for each fact. Be specific and detailed.\n\n"
        f"Excerpts:\n{context}\n\nQuestion: {query}")
    try:
        r = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            body=json.dumps({"messages":[{"role":"user","content":[{"text":prompt}]}],
                             "inferenceConfig":{"maxTokens":1500,"temperature":0.1}}))
        return json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]
    except Exception as e:
        print(f"Answer error: {e}")
        return "\n".join(f"[{c['document']}] {c['text'][:200]}" for c in chunks[:3])


def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    p          = _parse_event(event)
    action     = p.get("action", "search")
    query      = p.get("query", "").strip()
    doc_filter = p.get("document_filter", "").strip()
    top_k      = int(p.get("top_k", 8))

    print(f"action={action} query={query[:50]} filter={doc_filter}")

    if action == "list_documents" or (not query and not doc_filter):
        docs = _list_documents()
        return _wrap(event, {
            "status": "success", "action": "list_documents",
            "documents": docs, "total": len(docs),
            "summary": f"{len(docs)} documents: " + ", ".join(d["document_name"] for d in docs),
        })

    if action == "list_requirements":
        reqs = _list_requirements(doc_filter)
        return _wrap(event, {
            "status": "success", "action": "list_requirements",
            "requirements": reqs, "total": len(reqs),
        })

    chunks = _semantic_search(query, top_k, doc_filter)
    answer = _answer(query, chunks)
    return _wrap(event, {
        "status": "success", "action": "search", "query": query,
        "answer": answer,
        "sources": [{"document": c["document"], "chunk_id": c["chunk_id"],
                     "similarity": c["similarity"], "excerpt": c["text"][:300]}
                    for c in chunks],
        "total_sources": len(chunks),
    })
