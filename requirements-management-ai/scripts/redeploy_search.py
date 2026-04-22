import boto3, json, zipfile, tempfile, os, time

ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION = "us-east-1"
lam    = boto3.client("lambda", region_name=REGION)

# Package and deploy
src = os.path.join(ROOT, "src", "lambda", "document-search")
tmp = tempfile.mktemp(suffix=".zip")
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in os.listdir(src):
        if not f.endswith(".pyc"):
            zf.write(os.path.join(src, f), f)
with open(tmp, "rb") as f:
    data = f.read()
os.unlink(tmp)

lam.update_function_code(FunctionName="DocumentSearch", ZipFile=data)
print("Deployed DocumentSearch")

# Wait
for _ in range(20):
    if lam.get_function_configuration(FunctionName="DocumentSearch")["LastUpdateStatus"] == "Successful":
        break
    time.sleep(3)
time.sleep(3)

# Test 1: list_documents
r = lam.invoke(FunctionName="DocumentSearch",
               Payload=json.dumps({"actionGroup":"DocumentSearch","apiPath":"/search",
                                   "httpMethod":"POST","requestBody":{"content":{"application/json":
                                   {"properties":[{"name":"action","value":"list_documents"}]}}}}))
body = json.loads(json.loads(r["Payload"].read())["response"]["responseBody"]["application/json"]["body"])
print(f"\nlist_documents: {body['total']} docs")
for d in body.get("documents", []):
    print(f"  {d['document_name']} ({d['chunks']} chunks)")

# Test 2: semantic search
r2 = lam.invoke(FunctionName="DocumentSearch",
                Payload=json.dumps({"actionGroup":"DocumentSearch","apiPath":"/search",
                                    "httpMethod":"POST","requestBody":{"content":{"application/json":
                                    {"properties":[{"name":"action","value":"search"},
                                                   {"name":"query","value":"charging system voltage requirements"}]}}}}))
body2 = json.loads(json.loads(r2["Payload"].read())["response"]["responseBody"]["application/json"]["body"])
print(f"\nsearch: {body2['total_sources']} sources")
print(f"Answer: {body2.get('answer','')[:300]}")
