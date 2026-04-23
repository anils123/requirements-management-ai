"""
redeploy_lambdas.py — Redeploy all Lambda functions.
Packages graph_db.py into each Lambda for Neo4j graph access.
"""
import boto3, json, os, zipfile, tempfile, shutil, time

ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION = "us-east-1"

with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values(): OUT.update(v)

lam          = boto3.client("lambda", region_name=REGION)
GRAPH_DB_SRC = os.path.join(ROOT, "src", "graph", "graph_db.py")

FUNCTIONS = {
    "DocumentProcessor":     (OUT["DocumentProcessorArn"].split(":")[-1],     "src/lambda/document-processor"),
    "RequirementsExtractor": (OUT["RequirementsExtractorArn"].split(":")[-1], "src/lambda/requirements-extractor"),
    "ExpertMatcher":         (OUT["ExpertMatcherArn"].split(":")[-1],         "src/lambda/expert-matcher"),
    "ComplianceChecker":     (OUT["ComplianceCheckerArn"].split(":")[-1],     "src/lambda/compliance-checker"),
    "GraphAgent":            ("GraphAgent",                                    "src/lambda/graph-agent"),
    "DocumentSearch":        ("DocumentSearch",                                "src/lambda/document-search"),
}

TEST_PAYLOADS = {
    "DocumentProcessor": {
        "actionGroup":"DocumentProcessor","apiPath":"/process-document","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"document_path","value":"bids/sample_requirements.txt"}]}}},
    },
    "RequirementsExtractor": {
        "actionGroup":"RequirementsExtractor","apiPath":"/extract-requirements","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"document_id","value":"sample_requirements"}]}}},
    },
    "ExpertMatcher": {
        "actionGroup":"ExpertMatcher","apiPath":"/assign-experts","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"requirements","value":json.dumps([{"requirement_id":"REQ-001","description":"OAuth2","domain":"security"}])}]}}},
    },
    "ComplianceChecker": {
        "actionGroup":"ComplianceChecker","apiPath":"/check-compliance","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"requirement_id","value":"REQ-001"},
            {"name":"requirement_text","value":"OAuth2 authentication"},
            {"name":"domain","value":"security"}]}}},
    },
    "GraphAgent": {
        "actionGroup":"GraphAgent","apiPath":"/graph","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"action","value":"graph_stats"}]}}},
    },
    "DocumentSearch": {
        "actionGroup":"DocumentSearch","apiPath":"/search","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"action","value":"list_documents"}]}}},
    },
}


def zip_lambda(src_dir, include_graph_db=True):
    tmp = tempfile.mkdtemp()
    try:
        for f in os.listdir(src_dir):
            fp = os.path.join(src_dir, f)
            if os.path.isfile(fp) and f.endswith(".py") and not f.endswith(".pyc"):
                shutil.copy2(fp, os.path.join(tmp, f))
        if include_graph_db and os.path.exists(GRAPH_DB_SRC):
            shutil.copy2(GRAPH_DB_SRC, os.path.join(tmp, "graph_db.py"))
        zip_path = tempfile.mktemp(suffix=".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(tmp):
                fp = os.path.join(tmp, f)
                if os.path.isfile(fp):
                    zf.write(fp, f)
        with open(zip_path, "rb") as f:
            data = f.read()
        os.unlink(zip_path)
        return data
    finally:
        shutil.rmtree(tmp)


print("Redeploying Lambda functions...\n")
for name, (fn_name, src_rel) in FUNCTIONS.items():
    src_dir  = os.path.join(ROOT, src_rel)
    if not os.path.exists(src_dir):
        print(f"  SKIP {name} — directory not found: {src_dir}")
        continue
    zip_data = zip_lambda(src_dir)
    lam.update_function_code(FunctionName=fn_name, ZipFile=zip_data)
    for _ in range(20):
        cfg = lam.get_function_configuration(FunctionName=fn_name)
        if cfg["LastUpdateStatus"] == "Successful": break
        if cfg["LastUpdateStatus"] == "Failed":
            print(f"  FAILED: {name}"); break
        time.sleep(3)
    print(f"  Deployed: {name} ({len(zip_data)/1024:.1f} KB)")

print("\nWaiting 5s for propagation...")
time.sleep(5)

print("\nTesting all functions...")
all_ok = True
for name, (fn_name, _) in FUNCTIONS.items():
    if name not in TEST_PAYLOADS: continue
    try:
        resp   = lam.invoke(FunctionName=fn_name, Payload=json.dumps(TEST_PAYLOADS[name]))
        result = json.loads(resp["Payload"].read())
        if "errorMessage" in result:
            print(f"  FAIL {name}: {result['errorMessage'][:100]}")
            all_ok = False
        else:
            print(f"  OK   {name}")
    except Exception as e:
        print(f"  ERR  {name}: {e}")
        all_ok = False

print(f"\n{'All functions OK!' if all_ok else 'Some functions need attention'}")
