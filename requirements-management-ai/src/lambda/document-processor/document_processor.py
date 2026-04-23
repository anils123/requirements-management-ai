"""
Document Processor Lambda — Graph-Enhanced
Extracts text → chunks → embeddings → pgvector
AND stores Document/Entity nodes + relationships in graph DB.
"""
import json, os, time, hashlib, sys
import boto3
from typing import Any

sys.path.insert(0, "/var/task")

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
BUCKET    = os.environ.get("BUCKET_NAME", "")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")

textract   = boto3.client("textract",        region_name=REGION)
bedrock    = boto3.client("bedrock-runtime", region_name=REGION)
comprehend = boto3.client("comprehend",      region_name=REGION)
s3         = boto3.client("s3",              region_name=REGION)
rds        = boto3.client("rds-data",        region_name=REGION)


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

def _get_graph():
    import graph_db
    return graph_db


# ── Text extraction ───────────────────────────────────────────────────────────
def _extract_text(document_path):
    if not BUCKET: return ""
    if document_path.lower().endswith((".txt",".md",".csv")):
        return s3.get_object(Bucket=BUCKET, Key=document_path)["Body"].read().decode("utf-8","ignore")
    # pypdf for PDFs
    try:
        import io
        from pypdf import PdfReader
        raw    = s3.get_object(Bucket=BUCKET, Key=document_path)["Body"].read()
        reader = PdfReader(io.BytesIO(raw))
        pages  = [p.extract_text() for p in reader.pages if p.extract_text()]
        text   = "\n".join(pages)
        if len(text) > 50:
            print(f"pypdf: {len(text)} chars, {len(reader.pages)} pages")
            return text
    except Exception as e:
        print(f"pypdf error: {e}")
    # Textract fallback
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
        print(f"Textract error: {e}")
        return ""


def _chunk(text, size=400, overlap=50):
    words = text.split()
    step  = size - overlap
    return [{"text":" ".join(words[i:i+size]),"chunk_id":i//step}
            for i in range(0,len(words),step) if words[i:i+size]]

def _embed(text):
    r = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                             body=json.dumps({"inputText":text[:8000]}))
    return json.loads(r["body"].read())["embedding"]

def _store_chunks_pgvector(chunks, document_path):
    if not DB_ARN: return 0
    sql = """INSERT INTO document_chunks
               (document_path,chunk_id,text_content,embedding,metadata,created_at)
             VALUES(:p,:c,:t,:e::vector,:m::jsonb,NOW())
             ON CONFLICT(document_path,chunk_id) DO UPDATE SET
               text_content=EXCLUDED.text_content,
               embedding=EXCLUDED.embedding,
               metadata=EXCLUDED.metadata"""
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

def _extract_entities(text):
    entities = []
    for i in range(0, min(len(text),49000), 4900):
        try:
            r = comprehend.detect_entities(Text=text[i:i+4900], LanguageCode="en")
            entities.extend(r.get("Entities",[]))
        except Exception as e:
            print(f"Comprehend error: {e}")
    seen, unique = set(), []
    for e in entities:
        k = f"{e['Text'].lower()}|{e['Type']}"
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return unique[:100]


def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    params        = _parse_event(event)
    document_path = params.get("document_path","")
    if not document_path:
        return _wrap(event, {"status":"error","message":"document_path required"})

    doc_name = document_path.split("/")[-1]
    g        = _get_graph()

    try:
        # 1. Extract text
        text   = _extract_text(document_path)
        chunks = _chunk(text)
        print(f"Text: {len(text)} chars, {len(chunks)} chunks")

        # 2. Store chunks in pgvector (for semantic search)
        stored = _store_chunks_pgvector(chunks, document_path)

        # 3. Store Document node in graph
        g.store_document(document_path, doc_name, {
            "chunk_count": stored,
            "text_length": len(text),
            "pages": max(1, len(text)//3000),
        })

        # 4. Extract entities → store as Entity nodes + MENTIONS edges
        entities = _extract_entities(text)
        for ent in entities:
            eid = f"ENT:{ent['Text'].lower()}"
            g.upsert_node("Entity", eid, {
                "text": ent["Text"], "type": ent["Type"],
                "score": float(ent.get("Score",1.0)),
            })
            g.upsert_edge("Document", document_path, "MENTIONS", "Entity", eid,
                          {"score": float(ent.get("Score",1.0))},
                          weight=float(ent.get("Score",1.0)))

        # 5. Extract entity relations via Nova
        entity_names = list({e["Text"] for e in entities[:20]})
        if entity_names and len(text) > 100:
            try:
                prompt = (f"Extract relationships between these entities.\n"
                          f"Entities: {entity_names}\nText: {text[:2000]}\n"
                          f"Return JSON array: [{{\"subject\":\"A\",\"predicate\":\"requires\",\"object\":\"B\"}}]")
                r   = bedrock.invoke_model(
                    modelId="amazon.nova-micro-v1:0",
                    body=json.dumps({"messages":[{"role":"user","content":[{"text":prompt}]}],
                                     "inferenceConfig":{"maxTokens":500,"temperature":0.1}}))
                out = json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]
                s,e = out.find("["), out.rfind("]")+1
                if s != -1:
                    for rel in json.loads(out[s:e]):
                        subj = rel.get("subject","")
                        obj  = rel.get("object","")
                        pred = rel.get("predicate","relates_to")
                        if subj and obj:
                            g.upsert_node("Entity", f"ENT:{subj.lower()}", {"text":subj,"type":"OTHER"})
                            g.upsert_node("Entity", f"ENT:{obj.lower()}",  {"text":obj, "type":"OTHER"})
                            g.upsert_edge("Entity", f"ENT:{subj.lower()}", pred.upper(),
                                          "Entity", f"ENT:{obj.lower()}", {"source":document_path})
            except Exception as e:
                print(f"Relation extraction error: {e}")

        stats = g.graph_stats()
        body  = {
            "status":         "success",
            "document_path":  document_path,
            "chunks_created": stored,
            "text_length":    len(text),
            "pages_approx":   max(1, len(text)//3000),
            "entities_found": len(entities),
            "graph_nodes":    stats.get("total_nodes", 0),
            "graph_edges":    stats.get("total_edges", 0),
        }
        print(f"Done: {json.dumps(body)}")
        return _wrap(event, body)

    except Exception as e:
        print(f"Handler error: {e}")
        return _wrap(event, {"status":"error","message":str(e)})
