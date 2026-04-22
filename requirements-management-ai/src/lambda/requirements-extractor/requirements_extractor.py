"""
Requirements Extractor Lambda
- Fetches document chunks from Aurora pgvector
- Traverses Knowledge Graph for entity-enriched context
- Extracts requirements using Amazon Nova
- Stores to Aurora requirements table
"""
import json, os, hashlib
import boto3
from typing import Any

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
rds     = boto3.client("rds-data",        region_name=REGION)

DOMAIN_KEYWORDS = {
    "security":       ["security","auth","encrypt","access","permission","oauth","ssl","tls","certificate"],
    "performance":    ["performance","latency","throughput","response time","scalab","speed","capacity"],
    "integration":    ["api","integration","interface","protocol","rest","graphql","webhook","connector"],
    "data":           ["data","database","storage","backup","retention","migration","archive"],
    "compliance":     ["compliance","regulation","gdpr","iso","audit","standard","policy","legal"],
    "infrastructure": ["infrastructure","cloud","deploy","availability","disaster","recovery","redundan"],
    "ui_ux":          ["interface","user experience","usability","accessibility","ui","ux","dashboard"],
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
        if any(k in t for k in kws):
            return domain
    return "general"

def _rds(sql, params=None):
    kw = dict(resourceArn=DB_ARN, secretArn=DB_SECRET,
              database="requirements_db", sql=sql)
    if params: kw["parameters"] = params
    return rds.execute_statement(**kw)


# ── Fetch document chunks ─────────────────────────────────────────────────────
def _fetch_chunks(document_id):
    if not DB_ARN: return []
    try:
        r = _rds("SELECT chunk_id,text_content FROM document_chunks "
                 "WHERE document_path LIKE :doc ORDER BY chunk_id LIMIT 50",
                 [{"name":"doc","value":{"stringValue":f"%{document_id}%"}}])
        return [{"chunk_id":row[0]["longValue"],"text":row[1]["stringValue"]}
                for row in r.get("records",[])]
    except Exception as e:
        print(f"Fetch chunks error: {e}")
        return []


# ── Knowledge Graph traversal ─────────────────────────────────────────────────
def _kg_traverse(document_id, max_hops=2):
    """
    Traverse the KG for entities in this document.
    Returns enriched context: entity names, types, and their connected entities.
    """
    if not DB_ARN: return [], []
    try:
        # Get all entities for this document
        r = _rds("SELECT entity_id,entity_text,entity_type FROM kg_nodes "
                 "WHERE document_path LIKE :doc ORDER BY score DESC LIMIT 50",
                 [{"name":"doc","value":{"stringValue":f"%{document_id}%"}}])
        nodes = [{"id":row[0]["stringValue"],
                  "text":row[1]["stringValue"],
                  "type":row[2]["stringValue"]}
                 for row in r.get("records",[])]

        if not nodes:
            return [], []

        # For each entity, find connected entities (1-hop traversal)
        node_ids = [n["id"] for n in nodes[:20]]
        ids_str  = ",".join(f"'{nid}'" for nid in node_ids)

        r2 = _rds(
            f"SELECT e.predicate, n1.entity_text, n2.entity_text, n1.entity_type, n2.entity_type "
            f"FROM kg_edges e "
            f"JOIN kg_nodes n1 ON e.subject_id = n1.entity_id "
            f"JOIN kg_nodes n2 ON e.object_id  = n2.entity_id "
            f"WHERE e.subject_id IN ({ids_str}) OR e.object_id IN ({ids_str}) "
            f"LIMIT 50"
        )
        relations = [
            {"predicate": row[0]["stringValue"],
             "subject":   row[1]["stringValue"],
             "object":    row[2]["stringValue"],
             "subj_type": row[3]["stringValue"],
             "obj_type":  row[4]["stringValue"]}
            for row in r2.get("records", [])
        ]
        return nodes, relations
    except Exception as e:
        print(f"KG traversal error: {e}")
        return [], []


def _build_kg_context(nodes, relations):
    """Format KG data as readable context for the LLM."""
    if not nodes and not relations:
        return ""
    lines = ["=== Knowledge Graph Context ==="]
    if nodes:
        lines.append("Key Entities:")
        for n in nodes[:15]:
            lines.append(f"  - {n['text']} ({n['type']})")
    if relations:
        lines.append("Relationships:")
        for r in relations[:15]:
            lines.append(f"  - {r['subject']} --[{r['predicate']}]--> {r['object']}")
    return "\n".join(lines)


# ── Requirement extraction ────────────────────────────────────────────────────
def _extract_from_text(text, kg_context=""):
    prompt = f"""You are a requirements engineering expert. Extract ALL requirements from the text below.

{kg_context}

Text:
{text[:4000]}

Return ONLY valid JSON:
{{"requirements":[{{"id":"REQ-001","type":"functional","category":"security","priority":"high","description":"The system shall...","acceptance_criteria":["criterion1","criterion2"],"confidence_score":0.9,"entities":["EntityA","EntityB"]}}]}}

Rules:
- type: "functional" or "non-functional"
- priority: "high", "medium", or "low"
- Include entities from the Knowledge Graph context when relevant
- confidence_score: 0.0-1.0"""

    try:
        r    = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            body=json.dumps({"messages":[{"role":"user","content":[{"text":prompt}]}],
                             "inferenceConfig":{"maxTokens":2000,"temperature":0.1}}))
        out  = json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]
        s, e = out.find("{"), out.rfind("}") + 1
        if s == -1: return []
        return json.loads(out[s:e]).get("requirements", [])
    except Exception as ex:
        print(f"Extraction error: {ex}")
        return []


def _store_requirements(reqs, doc_id):
    if not DB_ARN or not reqs: return
    # DELETE existing requirements for this document first, then re-insert
    # This ensures fresh extraction always replaces stale data
    try:
        _rds("DELETE FROM requirements WHERE document_id = :did",
             [{"name":"did","value":{"stringValue":doc_id}}])
        print(f"Cleared existing requirements for {doc_id}")
    except Exception as e:
        print(f"Clear error (ok if first time): {e}")

    sql = """INSERT INTO requirements
               (requirement_id,document_id,type,category,priority,
                description,acceptance_criteria,domain,confidence_score,status)
             VALUES (:rid,:did,:type,:cat,:pri,:desc,:crit::jsonb,:dom,:conf,'extracted')
             ON CONFLICT (requirement_id) DO UPDATE SET
               description=EXCLUDED.description,
               document_id=EXCLUDED.document_id,
               type=EXCLUDED.type,
               priority=EXCLUDED.priority,
               domain=EXCLUDED.domain,
               confidence_score=EXCLUDED.confidence_score,
               status='extracted',
               updated_at=NOW()"""
    stored = 0
    for i, r in enumerate(reqs):
        try:
            # Use document-scoped ID: REQ-DOCNAME-0001 to avoid cross-document conflicts
            doc_prefix = doc_id[:12].upper().replace(' ','-').replace('/','-')
            req_id = f"REQ-{doc_prefix}-{i:04d}"
            _rds(sql, [
                {"name":"rid",  "value":{"stringValue": req_id}},
                {"name":"did",  "value":{"stringValue": doc_id}},
                {"name":"type", "value":{"stringValue": r.get("type","functional")}},
                {"name":"cat",  "value":{"stringValue": r.get("category","general")}},
                {"name":"pri",  "value":{"stringValue": r.get("priority","medium")}},
                {"name":"desc", "value":{"stringValue": r.get("description","")}},
                {"name":"crit", "value":{"stringValue": json.dumps(r.get("acceptance_criteria",[]))}},
                {"name":"dom",  "value":{"stringValue": _classify_domain(r.get("description",""))}},
                {"name":"conf", "value":{"doubleValue": float(r.get("confidence_score",0.8))}},
            ])
            r["requirement_id"] = req_id
            stored += 1
        except Exception as e:
            print(f"Store req error: {e}")
    print(f"Stored {stored}/{len(reqs)} requirements for {doc_id}")


# ── Handler ───────────────────────────────────────────────────────────────────
def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    params      = _parse_event(event)
    document_id = params.get("document_id","")
    if not document_id:
        return _wrap(event, {"status":"error","message":"document_id required"})

    try:
        # 1. Fetch chunks from pgvector
        chunks = _fetch_chunks(document_id)
        print(f"Found {len(chunks)} chunks for document_id='{document_id}'")

        # 2. Traverse Knowledge Graph for enriched context
        kg_nodes, kg_relations = _kg_traverse(document_id)
        kg_context = _build_kg_context(kg_nodes, kg_relations)
        print(f"KG context: {len(kg_nodes)} nodes, {len(kg_relations)} relations")

        # 3. Extract requirements from chunks + KG context
        all_reqs = []
        if chunks:
            for i in range(0, len(chunks), 5):
                batch = "\n\n".join(c["text"] for c in chunks[i:i+5])
                reqs  = _extract_from_text(batch, kg_context)
                all_reqs.extend(reqs)
        else:
            all_reqs = _extract_from_text(
                f"Document: {document_id}\nExtract sample requirements.", kg_context)

        # 4. Deduplicate + enrich
        seen, unique = set(), []
        for r in all_reqs:
            desc = r.get("description","").lower().strip()
            if not desc or desc in seen: continue
            seen.add(desc)
            r["requirement_id"] = r.get("id") or f"REQ-{document_id[:8].upper()}-{len(unique):04d}"
            r["document_id"]    = document_id
            r["domain"]         = _classify_domain(desc)
            r["status"]         = "extracted"
            r["kg_entities"]    = r.get("entities", [])
            unique.append(r)

        # 5. Store
        _store_requirements(unique, document_id)

        body = {
            "status":                 "success",
            "document_id":            document_id,
            "requirements_extracted": len(unique),
            "kg_nodes_used":          len(kg_nodes),
            "kg_relations_used":      len(kg_relations),
            "requirements":           unique,
        }
        print(f"Extracted {len(unique)} requirements (KG: {len(kg_nodes)} nodes)")
        return _wrap(event, body)

    except Exception as e:
        print(f"Error: {e}")
        return _wrap(event, {"status":"error","message":str(e)})
