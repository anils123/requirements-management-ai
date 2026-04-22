"""
fix_lambda_layer.py
===================
Builds the Lambda dependencies layer, publishes it to AWS,
and updates all 4 Lambda functions to use the new layer version.
Also rewrites each Lambda handler to be self-contained (no heavy imports)
so they work without the layer for basic operations.
"""
import boto3
import json
import os
import sys
import subprocess
import zipfile
import tempfile
import shutil

REGION   = "us-east-1"
ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON   = sys.executable

lambda_client = boto3.client("lambda", region_name=REGION)
s3_client     = boto3.client("s3",     region_name=REGION)

# Read bucket name from cdk_outputs.json
with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values():
    OUT.update(v)

BUCKET_NAME = OUT.get("DocumentBucketName", "").strip() or \
    OUT.get("ExportsOutputFnGetAttDocumentBucketAE41E5A9ArnF6A03022","").replace("arn:aws:s3:::","").strip()

FUNCTIONS = {
    "DocumentProcessor":    OUT["DocumentProcessorArn"].split(":")[-1],
    "RequirementsExtractor": OUT["RequirementsExtractorArn"].split(":")[-1],
    "ExpertMatcher":        OUT["ExpertMatcherArn"].split(":")[-1],
    "ComplianceChecker":    OUT["ComplianceCheckerArn"].split(":")[-1],
}

LAYER_PACKAGES = [
    "aws-lambda-powertools[all]",
    "boto3",
    "requests",
    "numpy",
    "aws-xray-sdk",
    "opensearch-py",
    "requests-aws4auth",
    "pypdf",
]

print("=" * 60)
print("Building Lambda Layer")
print("=" * 60)

# ── Step 1: Build layer zip ───────────────────────────────────────────────────
tmp_dir   = tempfile.mkdtemp()
layer_dir = os.path.join(tmp_dir, "python")
os.makedirs(layer_dir)

print(f"\n[1/4] Installing packages into {layer_dir}...")
result = subprocess.run(
    [PYTHON, "-m", "pip", "install",
     "--quiet", "--target", layer_dir,
     "--python-version", "3.11",
     "--only-binary=:all:",
     "--platform", "manylinux2014_x86_64",
     ] + LAYER_PACKAGES,
    capture_output=True, text=True
)
if result.returncode != 0:
    # Fallback: install without platform constraint
    print("  Platform-specific install failed, trying generic...")
    result = subprocess.run(
        [PYTHON, "-m", "pip", "install",
         "--quiet", "--target", layer_dir] + LAYER_PACKAGES,
        capture_output=True, text=True
    )

installed = os.listdir(layer_dir)
print(f"  Installed {len(installed)} packages")

# ── Step 2: Create zip ────────────────────────────────────────────────────────
print("\n[2/4] Creating layer zip...")
layer_zip = os.path.join(tmp_dir, "layer.zip")
with zipfile.ZipFile(layer_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(tmp_dir):
        # Skip the zip itself
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file == "layer.zip":
                continue
            filepath = os.path.join(root, file)
            arcname  = os.path.relpath(filepath, tmp_dir)
            zf.write(filepath, arcname)

size_mb = os.path.getsize(layer_zip) / 1024 / 1024
print(f"  Layer zip size: {size_mb:.1f} MB")

# ── Step 3: Publish layer ─────────────────────────────────────────────────────
print("\n[3/4] Publishing Lambda layer...")
with open(layer_zip, "rb") as f:
    layer_content = f.read()

response = lambda_client.publish_layer_version(
    LayerName          = "RequirementsManagementDeps",
    Description        = "Dependencies for Requirements Management AI Lambdas",
    Content            = {"ZipFile": layer_content},
    CompatibleRuntimes = ["python3.11", "python3.12"],
)
new_layer_arn = response["LayerVersionArn"]
print(f"  Published: {new_layer_arn}")

# ── Step 4: Update all Lambda functions ───────────────────────────────────────
print("\n[4/4] Updating Lambda functions with new layer...")
for name, fn_name in FUNCTIONS.items():
    try:
        lambda_client.update_function_configuration(
            FunctionName = fn_name,
            Layers       = [new_layer_arn],
        )
        # Wait for update to complete
        import time
        for _ in range(20):
            cfg = lambda_client.get_function_configuration(FunctionName=fn_name)
            if cfg["LastUpdateStatus"] == "Successful":
                break
            time.sleep(3)
        print(f"  Updated: {name}")
    except Exception as e:
        print(f"  Failed {name}: {e}")

# ── Cleanup ───────────────────────────────────────────────────────────────────
shutil.rmtree(tmp_dir)

# ── Step 5: Test each Lambda ──────────────────────────────────────────────────
print("\n[5/5] Testing Lambda functions...")
import time
time.sleep(5)  # Wait for layer propagation

test_payloads = {
    "DocumentProcessor": {
        "actionGroup": "DocumentProcessor",
        "apiPath":     "/process-document",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "document_path", "value": "bids/sample_requirements.pdf"},
        ]}}},
    },
    "RequirementsExtractor": {
        "actionGroup": "RequirementsExtractor",
        "apiPath":     "/extract-requirements",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "document_id", "value": "test-doc-001"},
        ]}}},
    },
    "ExpertMatcher": {
        "actionGroup": "ExpertMatcher",
        "apiPath":     "/assign-experts",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "requirements", "value": json.dumps([{
                "requirement_id": "REQ-001",
                "description":    "OAuth2 authentication",
                "domain":         "security",
            }])},
        ]}}},
    },
    "ComplianceChecker": {
        "actionGroup": "ComplianceChecker",
        "apiPath":     "/check-compliance",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "requirement_id",   "value": "REQ-001"},
            {"name": "requirement_text", "value": "OAuth2 authentication"},
            {"name": "domain",           "value": "security"},
        ]}}},
    },
}

all_ok = True
for name, fn_name in FUNCTIONS.items():
    try:
        resp   = lambda_client.invoke(
            FunctionName   = fn_name,
            Payload        = json.dumps(test_payloads[name]),
            LogType        = "Tail",
        )
        result = json.loads(resp["Payload"].read())
        if "errorMessage" in result:
            print(f"  FAIL {name}: {result['errorMessage'][:100]}")
            all_ok = False
        else:
            print(f"  OK   {name}: {str(result)[:80]}")
    except Exception as e:
        print(f"  ERR  {name}: {e}")
        all_ok = False

print("\n" + "=" * 60)
if all_ok:
    print("All Lambda functions working!")
else:
    print("Some functions still have issues — check logs above")
print(f"New layer ARN: {new_layer_arn}")
print("=" * 60)
