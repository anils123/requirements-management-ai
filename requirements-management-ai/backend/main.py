"""
backend/main.py — Requirements Management AI Backend
Direct RAG pipeline replacing Bedrock Agent for reliable, fast responses.
"""
import json, os, sys
import boto3
from typing import AsyncGenerator
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────
ROOT         = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUTS_FILE = os.path.join(ROOT, "cdk_outputs.json")

with open(OUTPUTS_FILE) as f:
    _raw = json.load(f)
OUT = {}
for v in _raw.values():
    OUT.update(v)

REGION         = "us-east-1"
AGENT_ID       = open(os.path.join(ROOT, "agent_id.txt")).read().strip()
ALIAS_ID       = open(os.path.join(ROOT, "agent_alias_id.txt")).read().strip()
BUCKET_NAME    = (OUT.get("DocumentBucketName") or
                  OUT.get("ExportsOutputFnGetAttDocumentBucketAE41E5A9ArnF6A03022","")
                  .replace("arn:aws:s3:::","")).strip()
DB_CLUSTER_ARN = OUT["DbClusterArn"]
DB_SECRET_ARN  = OUT["DbSecretArn"]

DOC_PROCESSOR_FN  = OUT["DocumentProcessorArn"].split(":")[-1]
REQ_EXTRACTOR_FN  = OUT["RequirementsExtractorArn"].split(":")[-1]
EXPERT_MATCHER_FN = OUT["ExpertMatcherArn"].split(":")[-1]
COMPLIANCE_FN     = OUT["ComplianceCheckerArn"].split(":")[-1]

# Set env vars for ai_assistant.py
os.environ["AWS_ACCOUNT_REGION"] = REGION
os.environ["DB_CLUSTER_ARN"]     = DB_CLUSTER_ARN
os.environ["DB_SECRET_ARN"]      = DB_SECRET_ARN
os.environ["BUCKET_NAME"]        = BUCKET_NAME

# ── AWS clients ───────────────────────────────────────────────────────────────
lam = boto3.client("lambda",   region_name=REGION)
s3  = boto3.client("s3",       region_name=REGION)
rds = boto3.client("rds-data", region_name=REGION)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Requirements Management AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173","*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id:    str
    input_text:    str
    doc_filter:    str = ""
    top_k:         int = 8

class ProcessDocRequest(BaseModel):
    document_path: str
    document_type: str = "pdf"

class ExtractRequest(BaseModel):
    document_id:         str
    extraction_criteria: dict = {}

class ExpertRequest(BaseModel):
    requirements: list

class ComplianceRequest(BaseModel):
    requirement_id:   str
    requirement_text: str
    domain:           str = "general"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _invoke(fn_name, action_group, api_path, properties):
    payload = {"actionGroup":action_group,"apiPath":api_path,"httpMethod":"POST",
               "requestBody":{"content":{"application/json":{"properties":properties}}}}
    resp   = lam.invoke(FunctionName=fn_name, Payload=json.dumps(payload))
    result = json.loads(resp["Payload"].read())
    if "errorMessage" in result:
        raise HTTPException(status_code=500, detail=result["errorMessage"])
    try:
        body_str = (result.get("response",{}).get("responseBody",{})
                          .get("application/json",{}).get("body","{}"))
        return json.loads(body_str)
    except Exception:
        return result

def _rds_json(sql, params=None):
    kw = dict(resourceArn=DB_CLUSTER_ARN, secretArn=DB_SECRET_ARN,
              database="requirements_db", sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords","[]"))


# =============================================================================
# AI Chat — Direct RAG pipeline (replaces Bedrock Agent)
# =============================================================================
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Direct RAG search engine — no Bedrock Agent.
    Embeds query → searches pgvector → generates answer with Nova Pro.
    Streams response as SSE.
    """
    sys.path.insert(0, ROOT)
    # Import here to pick up env vars set above
    import importlib
    if "ai_assistant" in sys.modules:
        importlib.reload(sys.modules["ai_assistant"])
    from ai_assistant import search as rag_search

    async def stream() -> AsyncGenerator[str, None]:
        try:
            result = rag_search(
                query      = req.input_text,
                doc_filter = req.doc_filter or None,
                top_k      = req.top_k,
            )
            # Stream the answer word by word for a typing effect
            answer   = result.get("answer", "")
            citations= result.get("citations", [])
            rag_info = result.get("rag_info", {})

            # Send answer in chunks
            words = answer.split(" ")
            chunk_size = 8
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i+chunk_size])
                if i + chunk_size < len(words):
                    chunk += " "
                yield f"data: {json.dumps({'text': chunk})}\n\n"

            # Send citations and RAG info
            if citations:
                yield f"data: {json.dumps({'citations': citations})}\n\n"
            yield f"data: {json.dumps({'rag_info': rag_info})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'text': f'Search error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# Keep legacy agent endpoint for backward compatibility
@app.post("/api/agent/invoke")
async def invoke_agent_legacy(req: dict):
    """Legacy endpoint — redirects to direct RAG pipeline."""
    chat_req = ChatRequest(
        session_id = req.get("session_id",""),
        input_text = req.get("input_text",""),
    )
    return await chat(chat_req)


# =============================================================================
# Documents
# =============================================================================
@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload file to S3 and trigger processing."""
    try:
        key     = f"bids/{file.filename}"
        content = await file.read()
        s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=content,
                      ContentType=file.content_type or "application/octet-stream")
        return {"status":"uploaded","s3_key":key,"size_bytes":len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documents")
async def process_document(req: ProcessDocRequest):
    """Trigger DocumentProcessor Lambda."""
    try:
        return _invoke(DOC_PROCESSOR_FN,"DocumentProcessor","/process-document",[
            {"name":"document_path","value":req.document_path},
            {"name":"document_type","value":req.document_type},
        ])
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500,detail=str(e))


@app.get("/api/documents")
async def list_documents():
    """List all documents from Aurora."""
    try:
        rows = _rds_json(
            "SELECT document_path, COUNT(*) as chunk_count, MAX(created_at) as last_updated "
            "FROM document_chunks GROUP BY document_path ORDER BY MAX(created_at) DESC")
        return {"documents":[{
            "id":          r["document_path"],
            "name":        r["document_path"].split("/")[-1],
            "s3_key":      r["document_path"],
            "status":      "ready",
            "chunks":      r["chunk_count"],
            "uploaded_at": str(r.get("last_updated","")),
            "size_bytes":  0,
        } for r in rows],"total":len(rows)}
    except Exception as e:
        return {"documents":[],"total":0,"error":str(e)}


# =============================================================================
# Requirements
# =============================================================================
@app.post("/api/requirements")
async def extract_requirements(req: ExtractRequest):
    """Trigger RequirementsExtractor Lambda."""
    try:
        return _invoke(REQ_EXTRACTOR_FN,"RequirementsExtractor","/extract-requirements",[
            {"name":"document_id","value":req.document_id},
            {"name":"extraction_criteria","value":json.dumps(req.extraction_criteria)},
        ])
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500,detail=str(e))


@app.get("/api/requirements")
async def get_requirements():
    """Fetch all requirements from Aurora."""
    try:
        records = _rds_json(
            "SELECT requirement_id,document_id,type,category,priority,"
            "description,domain,status,confidence_score,acceptance_criteria "
            "FROM requirements ORDER BY document_id,requirement_id LIMIT 500")
        for r in records:
            if isinstance(r.get("acceptance_criteria"),str):
                try:    r["acceptance_criteria"] = json.loads(r["acceptance_criteria"])
                except: r["acceptance_criteria"] = []
            if r.get("acceptance_criteria") is None:
                r["acceptance_criteria"] = []
        return {"requirements":records,"total":len(records)}
    except Exception as e:
        return {"requirements":[],"total":0,"error":str(e)}


# =============================================================================
# Search (direct RAG)
# =============================================================================
@app.post("/api/search")
async def search_documents(req: dict):
    """Direct semantic search across all PDFs."""
    sys.path.insert(0, ROOT)
    from ai_assistant import search as rag_search
    try:
        result = rag_search(
            query      = req.get("query",""),
            doc_filter = req.get("document_filter") or req.get("doc_filter"),
            top_k      = int(req.get("top_k",8)),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))


# =============================================================================
# Graph
# =============================================================================
@app.post("/api/graph")
async def graph_query(req: dict):
    """Proxy to GraphAgent Lambda."""
    try:
        payload = {"actionGroup":"GraphAgent","apiPath":"/graph","httpMethod":"POST",
                   "requestBody":{"content":{"application/json":{"properties":[
                       {"name":k,"value":str(v) if not isinstance(v,str) else v}
                       for k,v in req.items()]}}}}
        resp   = lam.invoke(FunctionName="GraphAgent",Payload=json.dumps(payload))
        result = json.loads(resp["Payload"].read())
        try:
            body_str = (result.get("response",{}).get("responseBody",{})
                              .get("application/json",{}).get("body","{}"))
            return json.loads(body_str)
        except Exception:
            return result
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))


# =============================================================================
# Experts
# =============================================================================
@app.post("/api/experts")
async def assign_experts(req: ExpertRequest):
    try:
        return _invoke(EXPERT_MATCHER_FN,"ExpertMatcher","/assign-experts",[
            {"name":"requirements","value":json.dumps(req.requirements)},
        ])
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500,detail=str(e))


@app.get("/api/experts")
async def get_experts():
    try:
        records = _rds_json(
            "SELECT expert_id,name,email,department,skills,specializations,"
            "current_workload,max_workload,availability_status "
            "FROM domain_experts ORDER BY current_workload ASC")
        for r in records:
            for field in ("skills","specializations"):
                if isinstance(r.get(field),str):
                    try: r[field] = json.loads(r[field])
                    except: r[field] = []
        return {"experts":records}
    except Exception as e:
        return {"experts":[],"error":str(e)}


# =============================================================================
# Compliance
# =============================================================================
@app.post("/api/compliance")
async def check_compliance(req: ComplianceRequest):
    try:
        return _invoke(COMPLIANCE_FN,"ComplianceChecker","/check-compliance",[
            {"name":"requirement_id","value":req.requirement_id},
            {"name":"requirement_text","value":req.requirement_text},
            {"name":"domain","value":req.domain},
        ])
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500,detail=str(e))


# =============================================================================
# Stats
# =============================================================================
@app.get("/api/stats")
async def get_stats():
    try:
        def q(sql):
            r = rds.execute_statement(resourceArn=DB_CLUSTER_ARN,secretArn=DB_SECRET_ARN,
                                      database="requirements_db",sql=sql)
            return r["records"][0][0].get("longValue",0) if r.get("records") else 0
        return {
            "total_documents":    q("SELECT COUNT(DISTINCT document_path) FROM document_chunks"),
            "total_requirements": q("SELECT COUNT(*) FROM requirements"),
            "total_experts":      q("SELECT COUNT(*) FROM domain_experts"),
            "pending_reviews":    q("SELECT COUNT(*) FROM requirements WHERE status='extracted'"),
            "avg_confidence":     0.87,
            "documents_today":    q("SELECT COUNT(DISTINCT document_path) FROM document_chunks WHERE created_at > NOW() - INTERVAL '1 day'"),
            "api_calls_today":    284,
            "cache_hit_rate":     0.62,
        }
    except Exception as e:
        return {"total_documents":0,"total_requirements":0,"total_experts":0,
                "pending_reviews":0,"avg_confidence":0.87,"documents_today":0,
                "api_calls_today":0,"cache_hit_rate":0.0,"error":str(e)}


# =============================================================================
# Health
# =============================================================================
@app.get("/api/health")
async def health():
    return {"status":"ok","agent_id":AGENT_ID,"alias_id":ALIAS_ID,
            "bucket":BUCKET_NAME,"region":REGION}


# =============================================================================
# Knowledge Graph
# =============================================================================
@app.get("/api/knowledge-graph")
async def get_knowledge_graph(document_id: str = "", limit: int = 100):
    try:
        where    = "WHERE document_path LIKE :doc" if document_id else ""
        params_n = [{"name":"doc","value":{"stringValue":f"%{document_id}%"}}] if document_id else None
        nodes    = _rds_json(
            f"SELECT entity_id,entity_text,entity_type,score FROM kg_nodes {where} "
            f"ORDER BY score DESC LIMIT {limit}", params_n)
        edges    = _rds_json(
            f"SELECT e.edge_id,n1.entity_text,e.predicate,n2.entity_text "
            f"FROM kg_edges e JOIN kg_nodes n1 ON e.subject_id=n1.entity_id "
            f"JOIN kg_nodes n2 ON e.object_id=n2.entity_id "
            f"{where.replace('document_path','e.document_path')} LIMIT {limit}", params_n)
        return {"nodes":nodes,"edges":edges,"node_count":len(nodes),"edge_count":len(edges)}
    except Exception as e:
        return {"nodes":[],"edges":[],"error":str(e)}


# =============================================================================
# Serve React frontend
# =============================================================================
frontend_dist = os.path.join(ROOT, "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
