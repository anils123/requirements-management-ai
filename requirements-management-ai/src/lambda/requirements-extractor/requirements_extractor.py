"""
Requirements Extractor Lambda — Graph-Enhanced
Extracts requirements from document chunks AND stores them in the graph DB
with EXTRACTED_FROM, SIMILAR_TO, and PART_OF relationships.
"""
import json, os, sys
import boto3
from typing import Any

sys.path.insert(0, "/var/task")

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
rds     = boto3.client("rds-data",        region_name=REGION)

DOMAIN_KEYWORDS = {
    "security":       ["security","auth","encrypt","access","permission","oauth","ssl","tls"],
    "performance":    ["performance","latency","throughput","response time","scalab","speed"],
    "integration":    ["api","integration","interface","protocol","rest","graphql","webhook"],
    "data":           ["data","database","storage","backup","retention","migration"],
    "compliance":     ["compliance","regulation","gdpr","iso","audit","standard","policy"],
    "infrastructure": ["infrastructure","cloud","deploy","availability","disaster","recovery"],
    "ui_ux":          ["interface","user experience","usability","accessibility","ui","ux"],
}


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

def _classify_domain(text):
    t = text.lower()
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(k in t for k in kws): return domain
    return "general"

def _rds_json(sql, params=None):
    kw = dict(resourceArn=DB_ARN, secretArn=DB_SECRET,
              database="requirements_db", sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords","[]"))

def _embed(text):
    r = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                             body=json.dumps({"inputText":text[:8000]}))
    return json.loads(r["body"].read())["embedding"]

def _get_graph():
    import graph_db
    return graph_db


def _fetch_chunks(document_id):
    if not DB_ARN: return []
    try:
        r = _rds_json(
            "SELECT chunk_id,text_content FROM document_chunks "
            "WHERE document_path LIKE :doc ORDER BY chunk_id LIMIT 50",
            [{"name":"doc","value":{"stringValue":f"%{document_id}%"}}])
        return [{"chunk_id":row["chunk_id"],"text":row["text_content"]} for row in r]
    except Exception as e:
        print(f"Fetch chunks error: {e}"); return []


def _get_kg_context(document_id, g):
    """Get Knowledge Graph context for this document."""
    try:
        # Get entities mentioned in this document
        doc_neighbours = g.traverse_out("Document", f"bids/{document_id}.pdf",
                                         rel="MENTIONS", limit=20)
        if not doc_neighbours:
            doc_neighbours = g.traverse_out("Document", document_id,
                                             rel="MENTIONS", limit=20)
        if not doc_neighbours:
            return ""
        entity_names = [n.get("properties",{}).get("text","") for n in doc_neighbours[:15]]
        lines = ["=== Knowledge Graph Context ===", "Key Entities:"]
        lines.extend(f"  - {e}" for e in entity_names if e)
        return "\n".join(lines)
    except Exception as e:
        print(f"KG context error: {e}"); return ""


def _extract_from_text(text, kg_context=""):
    prompt = f"""Extract ALL requirements from the text below.
{kg_context}

Text:
{text[:4000]}

Return ONLY valid JSON:
{{"requirements":[{{"id":"REQ-001","type":"functional","category":"security","priority":"high","description":"The system shall...","acceptance_criteria":["criterion1"],"confidence_score":0.9}}]}}"""
    try:
        r   = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            body=json.dumps({"messages":[{"role":"user","content":[{"text":prompt}]}],
                             "inferenceConfig":{"maxTokens":2000,"temperature":0.1}}))
        out = json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]
        s,e = out.find("{"), out.rfind("}")+1
        if s == -1: return []
        return json.loads(out[s:e]).get("requirements",[])
    except Exception as ex:
        print(f"Extraction error: {ex}"); return []


def _store_in_aurora(reqs, doc_id):
    """Store requirements in Aurora for fast SQL queries."""
    if not DB_ARN or not reqs: return
    # Delete existing for this document first
    try:
        rds.execute_statement(resourceArn=DB_ARN, secretArn=DB_SECRET,
            database="requirements_db",
            sql="DELETE FROM requirements WHERE document_id=:did",
            parameters=[{"name":"did","value":{"stringValue":doc_id}}])
    except Exception as e:
        print(f"Clear error: {e}")

    sql = """INSERT INTO requirements
               (requirement_id,document_id,type,category,priority,
                description,acceptance_criteria,domain,confidence_score,status)
             VALUES(:rid,:did,:type,:cat,:pri,:desc,:crit::jsonb,:dom,:conf,'extracted')
             ON CONFLICT(requirement_id) DO UPDATE SET
               description=EXCLUDED.description,domain=EXCLUDED.domain,
               confidence_score=EXCLUDED.confidence_score,updated_at=NOW()"""
    for r in reqs:
        try:
            rds.execute_statement(resourceArn=DB_ARN, secretArn=DB_SECRET,
                database="requirements_db", sql=sql, parameters=[
                {"name":"rid",  "value":{"stringValue":r.get("requirement_id","")}},
                {"name":"did",  "value":{"stringValue":doc_id}},
                {"name":"type", "value":{"stringValue":r.get("type","functional")}},
                {"name":"cat",  "value":{"stringValue":r.get("category","general")}},
                {"name":"pri",  "value":{"stringValue":r.get("priority","medium")}},
                {"name":"desc", "value":{"stringValue":r.get("description","")}},
                {"name":"crit", "value":{"stringValue":json.dumps(r.get("acceptance_criteria",[]))}},
                {"name":"dom",  "value":{"stringValue":r.get("domain","general")}},
                {"name":"conf", "value":{"doubleValue":float(r.get("confidence_score",0.8))}},
            ])
        except Exception as e:
            print(f"Aurora store error: {e}")


def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    params      = _parse_event(event)
    document_id = params.get("document_id","")
    if not document_id:
        return _wrap(event, {"status":"error","message":"document_id required"})

    g = _get_graph()

    try:
        # 1. Fetch chunks from pgvector
        chunks = _fetch_chunks(document_id)
        print(f"Found {len(chunks)} chunks for '{document_id}'")

        # 2. Get KG context for enriched extraction
        kg_context = _get_kg_context(document_id, g)

        # 3. Extract requirements
        all_reqs = []
        if chunks:
            for i in range(0, len(chunks), 5):
                batch = "\n\n".join(c["text"] for c in chunks[i:i+5])
                all_reqs.extend(_extract_from_text(batch, kg_context))
        else:
            all_reqs = _extract_from_text(
                f"Document: {document_id}\nExtract requirements.", kg_context)

        # 4. Deduplicate + assign IDs
        seen, unique = set(), []
        for r in all_reqs:
            desc = r.get("description","").lower().strip()
            if not desc or desc in seen: continue
            seen.add(desc)
            doc_prefix = document_id[:12].upper().replace(" ","-").replace("/","-")
            r["requirement_id"] = f"REQ-{doc_prefix}-{len(unique):04d}"
            r["document_id"]    = document_id
            r["domain"]         = _classify_domain(desc)
            r["status"]         = "extracted"
            unique.append(r)

        # 5. Store in Aurora (for SQL queries)
        _store_in_aurora(unique, document_id)

        # 6. Store in Graph DB (for relationship queries)
        graph_stored = 0
        for r in unique:
            emb = _embed(r["description"])
            g.store_requirement(
                r["requirement_id"], document_id,
                r["description"], r.get("type","functional"),
                r.get("priority","medium"), r["domain"],
                float(r.get("confidence_score",0.8)), emb)
            graph_stored += 1

        print(f"Stored {len(unique)} reqs in Aurora + {graph_stored} in graph")

        return _wrap(event, {
            "status":                 "success",
            "document_id":            document_id,
            "requirements_extracted": len(unique),
            "graph_nodes_created":    graph_stored,
            "requirements":           unique,
        })

    except Exception as e:
        print(f"Error: {e}")
        return _wrap(event, {"status":"error","message":str(e)})
