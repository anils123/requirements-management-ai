"""
redeploy_lambdas.py
===================
Repackages and redeploys all 4 Lambda function code zips.
"""
import boto3
import json
import os
import zipfile
import tempfile
import time

REGION = "us-east-1"
ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values():
    OUT.update(v)

lambda_client = boto3.client("lambda", region_name=REGION)

FUNCTIONS = {
    "DocumentProcessor":     (OUT["DocumentProcessorArn"].split(":")[-1],    "src/lambda/document-processor"),
    "RequirementsExtractor": (OUT["RequirementsExtractorArn"].split(":")[-1],"src/lambda/requirements-extractor"),
    "ExpertMatcher":         (OUT["ExpertMatcherArn"].split(":")[-1],        "src/lambda/expert-matcher"),
    "ComplianceChecker":     (OUT["ComplianceCheckerArn"].split(":")[-1],    "src/lambda/compliance-checker"),
}

TEST_PAYLOADS = {
    "DocumentProcessor": {
        "actionGroup":"DocumentProcessor","apiPath":"/process-document","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"document_path","value":"bids/sample_requirements.pdf"}
        ]}}},
    },
    "RequirementsExtractor": {
        "actionGroup":"RequirementsExtractor","apiPath":"/extract-requirements","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"document_id","value":"test-doc-001"}
        ]}}},
    },
    "ExpertMatcher": {
        "actionGroup":"ExpertMatcher","apiPath":"/assign-experts","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"requirements","value":json.dumps([{"requirement_id":"REQ-001","description":"OAuth2","domain":"security"}])}
        ]}}},
    },
    "ComplianceChecker": {
        "actionGroup":"ComplianceChecker","apiPath":"/check-compliance","httpMethod":"POST",
        "requestBody":{"content":{"application/json":{"properties":[
            {"name":"requirement_id","value":"REQ-001"},
            {"name":"requirement_text","value":"OAuth2 authentication"},
            {"name":"domain","value":"security"},
        ]}}},
    },
}

def zip_lambda(src_dir: str) -> bytes:
    """Zip a Lambda source directory."""
    tmp = tempfile.mktemp(suffix=".zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                if file.endswith(".pyc"):
                    continue
                filepath = os.path.join(root, file)
                arcname  = os.path.relpath(filepath, src_dir)
                zf.write(filepath, arcname)
    with open(tmp, "rb") as f:
        data = f.read()
    os.unlink(tmp)
    return data

print("Redeploying Lambda functions...\n")

for name, (fn_name, src_rel) in FUNCTIONS.items():
    src_dir = os.path.join(ROOT, src_rel)
    print(f"[{name}]")
    print(f"  Packaging: {src_dir}")

    zip_data = zip_lambda(src_dir)
    print(f"  Zip size:  {len(zip_data)/1024:.1f} KB")

    # Update function code
    lambda_client.update_function_code(
        FunctionName = fn_name,
        ZipFile      = zip_data,
    )

    # Wait for update
    for _ in range(20):
        cfg = lambda_client.get_function_configuration(FunctionName=fn_name)
        if cfg["LastUpdateStatus"] == "Successful":
            break
        if cfg["LastUpdateStatus"] == "Failed":
            print(f"  Update FAILED: {cfg.get('LastUpdateStatusReasonCode')}")
            break
        time.sleep(3)

    print(f"  Deployed: {fn_name}")

print("\nWaiting 5s for propagation...")
time.sleep(5)

print("\nTesting all functions...\n")
all_ok = True
for name, (fn_name, _) in FUNCTIONS.items():
    try:
        resp   = lambda_client.invoke(FunctionName=fn_name, Payload=json.dumps(TEST_PAYLOADS[name]))
        result = json.loads(resp["Payload"].read())
        if "errorMessage" in result:
            err = result["errorMessage"]
            print(f"  FAIL {name}: {err[:120]}")
            all_ok = False
        else:
            print(f"  OK   {name}: {str(result)[:100]}")
    except Exception as e:
        print(f"  ERR  {name}: {e}")
        all_ok = False

print("\n" + "="*60)
print("All functions OK!" if all_ok else "Some functions need attention — check errors above")
print("="*60)
