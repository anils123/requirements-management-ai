"""
Document Processor Lambda
- Extracts text (S3 direct / Textract)
- Chunks + embeds into Aurora pgvector
- Extracts entities + relations → Knowledge Graph (Aurora kg_nodes/kg_edges)
- Registers document in document_registry
- Syncs document to Bedrock Knowledge Base for agent retrieval
"""
import json, os, time, hashlib, re
import boto3
from typing import Any

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
BUCKET    = os.environ.get("BUCKET_NAME", "")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")
KB_ID     = os.environ.get("REQUIREMENTS_KB_ID", "")   # Bedrock KB ID

textract   = boto3.client("textract",        region_name=REGION)
bedrock    = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_ag = boto3.client("bedrock-agent",   region_name=REGION)
comprehend = boto3.client("comprehend",      region_name=REGION)
s3         = boto3.client("s3",              region_name=REGION)
rds        = boto3.client("rds-data",        region_name=REGION)


# ── Event helpers ─────────────────────────────────────────────────────────────
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
    if "actionGroup" not in event:
        return body
    return {"messageVersion":"1.0","response":{
        "actionGroup":event.get("actionGroup",""),
        "apiPath":event.get("apiPath",""),
        "httpMethod":event.get("httpMethod","POST"),
        "httpStatusCode":200,
        "responseBody":{"application/json":{"body":json.dumps(body)}},
    }}


# ── Text extraction ───────────────────────────────────────────────────────────
def _extract_text(document_path):
    if not BUCKET:
        return ""
    if document_path.lower().endswith((".txt",".md",".csv")):
        obj = s3.get_object(Bucket=BUCKET, Key=document_path)
        return obj["Body"].read().decode("utf-8", errors="ignore")
    # PDF via Textract
    try:
        job_id = textract.start_document_text_detection(
            DocumentLocation={"S3Object":{"Bucket":BUCKET,"Name":document_path}}
        )["JobId"]
        for _ in range(60):
            r = textract.get_document_text_detection(JobId=job_id)
            if r["JobStatus"] == "SUCCEEDED": break
            if r["JobStatus"] == "FAILED":    raise Exception("Textract failed")
            time.sleep(5)
        lines, nxt = [], None
        while True:
            kw = {"JobId": job_id}
            if nxt: kw["NextToken"] = nxt
            pg  = textract.get_document_text_detection(**kw)
            lines.extend(b["Text"] for b in pg.get("Blocks",[]) if b["BlockType"]=="LINE")
            nxt = pg.get("NextToken")
            if not nxt: break
        return "\n".join(lines)
    except Exception as e:
        print(f"Textract error: {e}, falling back to S3 raw read")
        raw   = s3.get_object(Bucket=BUCKET, Key=document_path)["Body"].read()
        text  = raw.decode("utf-8", errors="ignore")
        lines = [l.strip() for l in text.split("\n")
                 if len(l.strip()) > 10 and l.strip().isprintable()]
        return "\n".join(lines)


# ── Chunking + embedding ──────────────────────────────────────────────────────
def _chunk(text, size=400, overlap=50):
    words = text.split()
    step  = size - overlap
    return [{"text":" ".join(words[i:i+size]),"chunk_id":i//step}
            for i in range(0,len(words),step) if words[i:i+size]]

def _embed(text):
    r = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                             body=json.dumps({"inputText":text[:8000]}))
    return json.loads(r["body"].read())["embedding"]

def _store_chunks(chunks, document_path):
    if not DB_ARN: return 0
    sql = """INSERT INTO document_chunks
               (document_path,chunk_id,text_content,embedding,metadata,created_at)
             VALUES (:p,:c,:t,:e::vector,:m::jsonb,NOW())
             ON CONFLICT DO NOTHING"""
    stored = 0
    for ch in chunks:
        try:
            emb = _embed(ch["text"])
            rds.execute_statement(resourceArn=DB_ARN,secretArn=DB_SECRET,
                database="requirements_db",sql=sql,parameters=[
                {"name":"p","value":{"stringValue":document_path}},
                {"name":"c","value":{"longValue":ch["chunk_id"]}},
                {"name":"t","value":{"stringValue":ch["text"]}},
                {"name":"e","value":{"stringValue":str(emb)}},
                {"name":"m","value":{"stringValue":json.dumps({
                    "document_path":document_path,"chunk_id":ch["chunk_id"]})}},
            ])
            stored += 1
        except Exception as e:
            print(f"Chunk store error: {e}")
    return stored


# ── Knowledge Graph extraction ────────────────────────────────────────────────
def _extract_entities_comprehend(text):
    """Extract named entities using Amazon Comprehend."""
    entities = []
    for i in range(0, min(len(text), 49000), 4900):
        chunk = text[i:i+4900]
        try:
            r = comprehend.detect_entities(Text=chunk, LanguageCode="en")
            entities.extend(r.get("Entities", []))
        except Exception as e:
            print(f"Comprehend error: {e}")
    # Deduplicate by text+type
    seen, unique = set(), []
    for e in entities:
        key = f"{e['Text'].lower()}|{e['Type']}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique[:100]  # cap at 100 entities per doc

def _extract_relations_nova(text, entity_names):
    """Extract entity relations using Amazon Nova."""
    if not entity_names:
        return []
    prompt = (
        f"Extract relationships between these entities found in the text.\n"
        f"Entities: {entity_names[:20]}\n\n"
        f"Text (excerpt):\n{text[:3000]}\n\n"
        f"Return ONLY valid JSON:\n"
        f'[{{"subject":"EntityA","predicate":"requires","object":"EntityB"}}]'
    )
    try:
        r    = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            body=json.dumps({"messages":[{"role":"user","content":[{"text":prompt}]}],
                             "inferenceConfig":{"maxTokens":800,"temperature":0.1}}))
        out  = json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]
        s, e = out.find("["), out.rfind("]") + 1
        return json.loads(out[s:e]) if s != -1 else []
    except Exception as ex:
        print(f"Relation extraction error: {ex}")
        return []

def _store_kg(entities, relations, document_path):
    """Store entities as nodes and relations as edges in Aurora KG tables."""
    if not DB_ARN:
        return 0, 0

    node_sql = """INSERT INTO kg_nodes
                    (entity_id,entity_text,entity_type,document_path,score,metadata,created_at)
                  VALUES (:eid,:text,:type,:doc,:score,:meta::jsonb,NOW())
                  ON CONFLICT (entity_id) DO UPDATE SET
                    score=GREATEST(kg_nodes.score,EXCLUDED.score),
                    metadata=kg_nodes.metadata||EXCLUDED.metadata"""

    edge_sql = """INSERT INTO kg_edges
                    (edge_id,subject_id,object_id,predicate,document_path,confidence,created_at)
                  VALUES (:eid,:sub,:obj,:pred,:doc,:conf,NOW())
                  ON CONFLICT (edge_id) DO NOTHING"""

    nodes_stored = 0
    for ent in entities:
        eid = hashlib.md5(f"{ent['Text'].lower()}|{ent['Type']}".encode()).hexdigest()[:16]
        try:
            rds.execute_statement(resourceArn=DB_ARN,secretArn=DB_SECRET,
                database="requirements_db",sql=node_sql,parameters=[
                {"name":"eid",  "value":{"stringValue":eid}},
                {"name":"text", "value":{"stringValue":ent["Text"]}},
                {"name":"type", "value":{"stringValue":ent["Type"]}},
                {"name":"doc",  "value":{"stringValue":document_path}},
                {"name":"score","value":{"doubleValue":float(ent.get("Score",1.0))}},
                {"name":"meta", "value":{"stringValue":json.dumps({"source":document_path})}},
            ])
            nodes_stored += 1
        except Exception as e:
            print(f"KG node error: {e}")

    edges_stored = 0
    for rel in relations:
        subj = rel.get("subject","")
        obj  = rel.get("object","")
        pred = rel.get("predicate","relates_to")
        if not subj or not obj:
            continue
        sub_id = hashlib.md5(subj.lower().encode()).hexdigest()[:16]
        obj_id = hashlib.md5(obj.lower().encode()).hexdigest()[:16]
        eid    = hashlib.md5(f"{sub_id}|{pred}|{obj_id}".encode()).hexdigest()[:16]
        try:
            rds.execute_statement(resourceArn=DB_ARN,secretArn=DB_SECRET,
                database="requirements_db",sql=edge_sql,parameters=[
                {"name":"eid",  "value":{"stringValue":eid}},
                {"name":"sub",  "value":{"stringValue":sub_id}},
                {"name":"obj",  "value":{"stringValue":obj_id}},
                {"name":"pred", "value":{"stringValue":pred}},
                {"name":"doc",  "value":{"stringValue":document_path}},
                {"name":"conf", "value":{"doubleValue":1.0}},
            ])
            edges_stored += 1
        except Exception as e:
            print(f"KG edge error: {e}")

    return nodes_stored, edges_stored


# ── Document registry ─────────────────────────────────────────────────────────
def _register_document(document_path, doc_name, chunks, text, kb_ingestion_id=""):
    if not DB_ARN: return
    sql = """INSERT INTO document_registry
               (document_path,document_name,s3_bucket,chunk_count,text_length,
                kb_synced,kb_ingestion_id,processing_status,processed_at,metadata)
             VALUES (:path,:name,:bucket,:chunks,:tlen,
                     :synced,:kbid,'completed',NOW(),:meta::jsonb)
             ON CONFLICT (document_path) DO UPDATE SET
               chunk_count=EXCLUDED.chunk_count,
               text_length=EXCLUDED.text_length,
               kb_synced=EXCLUDED.kb_synced,
               kb_ingestion_id=EXCLUDED.kb_ingestion_id,
               processing_status='completed',
               processed_at=NOW()"""
    try:
        rds.execute_statement(resourceArn=DB_ARN,secretArn=DB_SECRET,
            database="requirements_db",sql=sql,parameters=[
            {"name":"path",   "value":{"stringValue":document_path}},
            {"name":"name",   "value":{"stringValue":doc_name}},
            {"name":"bucket", "value":{"stringValue":BUCKET}},
            {"name":"chunks", "value":{"longValue":len(chunks)}},
            {"name":"tlen",   "value":{"longValue":len(text)}},
            {"name":"synced", "value":{"booleanValue":bool(kb_ingestion_id)}},
            {"name":"kbid",   "value":{"stringValue":kb_ingestion_id or ""}},
            {"name":"meta",   "value":{"stringValue":json.dumps({"s3_key":document_path})}},
        ])
    except Exception as e:
        print(f"Registry error: {e}")


# ── Bedrock Knowledge Base sync ───────────────────────────────────────────────
def _sync_to_kb(document_path):
    """Start a Bedrock KB ingestion job to index the document."""
    if not KB_ID:
        print("REQUIREMENTS_KB_ID not set — skipping KB sync")
        return ""
    try:
        # List data sources for this KB
        ds_list = bedrock_ag.list_data_sources(knowledgeBaseId=KB_ID)
        ds_id   = ds_list["dataSourceSummaries"][0]["dataSourceId"] if ds_list["dataSourceSummaries"] else ""
        if not ds_id:
            print("No data source found for KB")
            return ""
        job = bedrock_ag.start_ingestion_job(
            knowledgeBaseId=KB_ID,
            dataSourceId=ds_id,
        )
        ingestion_id = job["ingestionJob"]["ingestionJobId"]
        print(f"KB ingestion started: {ingestion_id}")
        return ingestion_id
    except Exception as e:
        print(f"KB sync error: {e}")
        return ""


# ── Main handler ──────────────────────────────────────────────────────────────
def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    params        = _parse_event(event)
    document_path = params.get("document_path","")
    if not document_path:
        return _wrap(event, {"status":"error","message":"document_path required"})

    doc_name = document_path.split("/")[-1]

    try:
        # 1. Extract text
        print(f"Extracting text from: {document_path}")
        text   = _extract_text(document_path)
        chunks = _chunk(text)
        print(f"Text length: {len(text)}, Chunks: {len(chunks)}")

        # 2. Store chunks + embeddings in pgvector
        stored = _store_chunks(chunks, document_path)
        print(f"Stored {stored} chunks in pgvector")

        # 3. Extract entities + relations → Knowledge Graph
        print("Extracting entities for Knowledge Graph...")
        entities      = _extract_entities_comprehend(text)
        entity_names  = list({e["Text"] for e in entities})
        relations     = _extract_relations_nova(text, entity_names)
        nodes, edges  = _store_kg(entities, relations, document_path)
        print(f"KG: {nodes} nodes, {edges} edges stored")

        # 4. Sync to Bedrock Knowledge Base
        kb_ingestion_id = _sync_to_kb(document_path)

        # 5. Register document
        _register_document(document_path, doc_name, chunks, text, kb_ingestion_id)

        body = {
            "status":           "success",
            "document_path":    document_path,
            "chunks_created":   stored,
            "text_length":      len(text),
            "pages_approx":     max(1, len(text)//3000),
            "kg_nodes":         nodes,
            "kg_edges":         edges,
            "kb_synced":        bool(kb_ingestion_id),
            "kb_ingestion_id":  kb_ingestion_id,
            "entities_found":   len(entities),
        }
        print(f"Done: {json.dumps(body)}")
        return _wrap(event, body)

    except Exception as e:
        print(f"Handler error: {e}")
        return _wrap(event, {"status":"error","message":str(e)})
