"""
Test the full upload → process → extract pipeline for a new PDF.
Simulates exactly what the frontend does.
"""
import boto3, json, time, os, requests

ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION = "us-east-1"
lam    = boto3.client("lambda",   region_name=REGION)
s3     = boto3.client("s3",       region_name=REGION)
rds    = boto3.client("rds-data", region_name=REGION)

DB  = "arn:aws:rds:us-east-1:672996977856:cluster:requirementsmanagementstack-vectordatabase3f35b757-1puh70gvsblh"
SEC = "arn:aws:secretsmanager:us-east-1:672996977856:secret:RequirementsManagementStack-uEpN70J2Wx5n-KmDmDi"
BUCKET = "requirementsmanagementstack-documentbucketae41e5a9-v7g01d4l2urm"

DOC_FN = "RequirementsManagementSta-DocumentProcessor3D49A08-kKbHVGTb1bVQ"
REQ_FN = "RequirementsManagementSta-RequirementsExtractor1D9-uZTylX0rYPcR"

def q(sql, params=None):
    kw = dict(resourceArn=DB, secretArn=SEC, database="requirements_db",
              sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords","[]"))

def invoke(fn, props):
    payload = {"actionGroup": fn.split("-")[0], "apiPath": "/test",
               "httpMethod": "POST",
               "requestBody": {"content": {"application/json": {"properties": props}}}}
    r = lam.invoke(FunctionName=fn, LogType="Tail", Payload=json.dumps(payload))
    import base64
    result = json.loads(r["Payload"].read())
    log    = base64.b64decode(r.get("LogResult","")).decode()
    body   = json.loads(result.get("response",{}).get("responseBody",{})
                              .get("application/json",{}).get("body","{}"))
    return body, log

# ── Step 1: Create a test PDF with real content ───────────────────────────────
print("Step 1: Creating test PDF with real requirements content...")
test_pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 800>>
stream
BT /F1 12 Tf 50 750 Td
(REQUIREMENTS SPECIFICATION - TEST DOCUMENT) Tj
0 -20 Td (REQ-001: The system shall authenticate users via OAuth2 with MFA.) Tj
0 -20 Td (REQ-002: API response time shall not exceed 200ms at P95 under load.) Tj
0 -20 Td (REQ-003: All data shall be encrypted at rest using AES-256 encryption.) Tj
0 -20 Td (REQ-004: The system shall support 10000 concurrent users without degradation.) Tj
0 -20 Td (REQ-005: Audit logs shall be retained for minimum 7 years per compliance.) Tj
0 -20 Td (REQ-006: The system shall provide REST API conforming to OpenAPI 3.0 spec.) Tj
0 -20 Td (REQ-007: Recovery Time Objective shall be less than 4 hours for DR scenarios.) Tj
0 -20 Td (REQ-008: The system shall integrate with SAP ERP via certified REST connector.) Tj
0 -20 Td (REQ-009: User interface shall meet WCAG 2.1 AA accessibility standards.) Tj
0 -20 Td (REQ-010: System shall provide real-time monitoring dashboard with alerts.) Tj
ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000125 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
1200
%%EOF"""

test_key = "bids/test_requirements_new.pdf"
s3.put_object(Bucket=BUCKET, Key=test_key, Body=test_pdf_content,
              ContentType="application/pdf")
print(f"  Uploaded: s3://{BUCKET}/{test_key}")

# ── Step 2: Process document ──────────────────────────────────────────────────
print("\nStep 2: Processing document (extract text + embeddings)...")
body, log = invoke(DOC_FN, [
    {"name": "document_path", "value": test_key},
    {"name": "document_type", "value": "pdf"},
])
print(f"  Status:        {body.get('status')}")
print(f"  chunks_created:{body.get('chunks_created',0)}")
print(f"  text_length:   {body.get('text_length',0)}")
print(f"  kg_nodes:      {body.get('kg_nodes',0)}")
for line in log.split("\n"):
    if any(k in line for k in ["pypdf","Textract","Text length","chunks","Error","error"]):
        print(f"  LOG: {line.strip()}")

if body.get("chunks_created", 0) == 0:
    print("\n  ERROR: No chunks created! Checking why...")
    rows = q("SELECT document_path, COUNT(*) as c FROM document_chunks "
             "WHERE document_path LIKE '%test_requirements%' GROUP BY document_path")
    print(f"  Chunks in DB: {rows}")

# ── Step 3: Extract requirements ─────────────────────────────────────────────
print("\nStep 3: Extracting requirements...")
doc_id = test_key.replace("bids/","").replace(".pdf","")
body2, log2 = invoke(REQ_FN, [
    {"name": "document_id", "value": doc_id},
])
print(f"  Status:    {body2.get('status')}")
print(f"  Extracted: {body2.get('requirements_extracted',0)}")
for line in log2.split("\n"):
    if any(k in line for k in ["Found","Stored","Extracted","Error","error","chunks"]):
        print(f"  LOG: {line.strip()}")

reqs = body2.get("requirements", [])
print(f"\n  Requirements:")
for r in reqs[:5]:
    print(f"    {r.get('requirement_id','?')}: {r.get('description','')[:70]}")

# ── Step 4: Verify in Aurora ──────────────────────────────────────────────────
print("\nStep 4: Verifying in Aurora...")
rows = q("SELECT requirement_id, description FROM requirements "
         "WHERE document_id = :d ORDER BY requirement_id",
         [{"name":"d","value":{"stringValue": doc_id}}])
print(f"  Requirements in Aurora: {len(rows)}")
for r in rows[:3]:
    print(f"    {r['requirement_id']}: {r['description'][:60]}")

# ── Step 5: Test via backend API ──────────────────────────────────────────────
print("\nStep 5: Testing via backend API (http://localhost:8000)...")
try:
    r = requests.post("http://localhost:8000/api/requirements",
                      json={"document_id": doc_id, "extraction_criteria": {}},
                      timeout=120)
    data = r.json()
    print(f"  API status:    {data.get('status')}")
    print(f"  API extracted: {data.get('requirements_extracted',0)}")
    if data.get("requirements"):
        print(f"  First req: {data['requirements'][0].get('description','')[:70]}")
except Exception as e:
    print(f"  Backend not running or error: {e}")

print("\n=== DONE ===")
