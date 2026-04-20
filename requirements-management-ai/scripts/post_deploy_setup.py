"""
post_deploy_setup.py  -  All 6 post-deployment steps in one script.
Reads everything from cdk_outputs.json. No env var dependencies.

Usage:
    python scripts/post_deploy_setup.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import boto3
import botocore.auth
import botocore.awsrequest

# =============================================================================
# Bootstrap
# =============================================================================
ROOT         = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUTPUTS_FILE = os.path.join(ROOT, "cdk_outputs.json")
sys.path.insert(0, ROOT)

if not os.path.exists(OUTPUTS_FILE):
    alt = os.path.join(ROOT, "cdk", "cdk_outputs.json")
    OUTPUTS_FILE = alt if os.path.exists(alt) else OUTPUTS_FILE

if not os.path.exists(OUTPUTS_FILE):
    print(f"ERROR: cdk_outputs.json not found. Run CDK deploy first.")
    sys.exit(1)

with open(OUTPUTS_FILE) as f:
    _raw = json.load(f)

OUT = {}
for v in _raw.values():
    OUT.update(v)

# =============================================================================
# Constants
# =============================================================================
REGION                     = "us-east-1"
DB_CLUSTER_ARN             = OUT["DbClusterArn"]
DB_SECRET_ARN              = OUT["DbSecretArn"]
OPENSEARCH_ENDPOINT        = OUT["OpenSearchEndpoint"]
DOCUMENT_PROCESSOR_ARN     = OUT["DocumentProcessorArn"]
REQUIREMENTS_EXTRACTOR_ARN = OUT["RequirementsExtractorArn"]
EXPERT_MATCHER_ARN         = OUT["ExpertMatcherArn"]
COMPLIANCE_CHECKER_ARN     = OUT["ComplianceCheckerArn"]
API_ENDPOINT               = OUT.get("ApiEndpoint") or OUT.get("RequirementsApiEndpointF7F3ECEE", "")

# Bucket name with fallback to S3 ARN export
BUCKET_NAME = OUT.get("DocumentBucketName", "").strip()
if not BUCKET_NAME:
    s3_arn = OUT.get("ExportsOutputFnGetAttDocumentBucketAE41E5A9ArnF6A03022", "")
    BUCKET_NAME = s3_arn.replace("arn:aws:s3:::", "").strip()
if not BUCKET_NAME:
    print("ERROR: Could not determine S3 bucket name from cdk_outputs.json")
    sys.exit(1)

# =============================================================================
# Boto3 clients
# =============================================================================
bedrock_rt    = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_agent = boto3.client("bedrock-agent",   region_name=REGION)
rds           = boto3.client("rds-data",        region_name=REGION)
s3            = boto3.client("s3",              region_name=REGION)
lambda_client = boto3.client("lambda",          region_name=REGION)
iam           = boto3.client("iam",             region_name=REGION)
sts           = boto3.client("sts",             region_name=REGION)

ACCOUNT  = sts.get_caller_identity()["Account"]
USERNAME = sts.get_caller_identity()["Arn"].split("/")[-1]

# =============================================================================
# Helpers
# =============================================================================
G = "\033[92m"; C = "\033[96m"; Y = "\033[93m"; N = "\033[0m"

def info(m):  print(f"{C}[INFO]{N}  {m}")
def ok(m):    print(f"{G}[OK]{N}    {m}")
def warn(m):  print(f"{Y}[WARN]{N}  {m}")
def step(t):  print(f"\n{C}{'='*62}\n  {t}\n{'='*62}{N}")

def _rds(sql):
    return rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database="requirements_db",
        sql=sql,
    )

# =============================================================================
# STEP 1 - Verify Bedrock Model Access
# =============================================================================
step("Step 1: Verify Bedrock Model Access")

MODELS = [
    ("anthropic.claude-3-5-sonnet-20241022-v2:0",
     json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 1,
                 "messages": [{"role": "user", "content": "hi"}]})),
    ("anthropic.claude-3-haiku-20240307-v1:0",
     json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 1,
                 "messages": [{"role": "user", "content": "hi"}]})),
    ("amazon.titan-embed-text-v2:0",
     json.dumps({"inputText": "test"})),
]

for model_id, body in MODELS:
    try:
        bedrock_rt.invoke_model(modelId=model_id, body=body)
        ok(f"Model ready: {model_id}")
    except bedrock_rt.exceptions.AccessDeniedException:
        warn(f"Model not accessible: {model_id}")
        input("  Enable in Bedrock console then press Enter to continue...")
    except Exception:
        ok(f"Model ready: {model_id}  (endpoint reachable)")

# =============================================================================
# STEP 2 - Create OpenSearch Indexes
# =============================================================================
step("Step 2: Create OpenSearch Indexes")

INDEX_BODY = json.dumps({
    "settings": {"index": {"knn": True}},
    "mappings": {"properties": {
        "vector_field": {
            "type": "knn_vector",
            "dimension": 1024,
            "method": {
                "name": "hnsw",
                "space_type": "cosinesimil",
                "engine": "nmslib",
                "parameters": {"ef_construction": 512, "m": 16},
            },
        },
        "text":     {"type": "text"},
        "metadata": {"type": "object"},
    }},
}).encode()

_boto_session = boto3.Session()
_creds        = _boto_session.get_credentials()
# get_credentials() may return a RefreshableCredentials or Credentials object
# Use botocore's resolve_credentials_from_http_credentials for safety
_frozen_creds = _creds.get_frozen_credentials()
_signer       = botocore.auth.SigV4Auth(_frozen_creds, "aoss", REGION)


def _create_index(name):
    url     = f"{OPENSEARCH_ENDPOINT}/{name}"
    aws_req = botocore.awsrequest.AWSRequest(
        method="PUT", url=url, data=INDEX_BODY,
        headers={"Content-Type": "application/json"},
    )
    _signer.add_auth(aws_req)
    prepped  = aws_req.prepare()
    http_req = urllib.request.Request(
        url, data=INDEX_BODY, headers=dict(prepped.headers), method="PUT"
    )
    try:
        with urllib.request.urlopen(http_req, timeout=20) as r:
            body = json.loads(r.read())
            if body.get("acknowledged"):
                ok(f"Index created: {name}")
            else:
                info(f"Index response: {body}")
    except urllib.error.HTTPError as e:
        body  = json.loads(e.read())
        etype = body.get("error", {}).get("type", "")
        if "already_exists" in etype:
            info(f"Index already exists: {name}")
        else:
            warn(f"Index error {name}: {body}")


for idx in ["requirements-index", "regulatory-index", "experts-index"]:
    _create_index(idx)

# =============================================================================
# STEP 3 - Create Bedrock Agent
# =============================================================================
step("Step 3: Create Bedrock Agent")

AGENT_ID_FILE       = os.path.join(ROOT, "agent_id.txt")
AGENT_ALIAS_ID_FILE = os.path.join(ROOT, "agent_alias_id.txt")


def _get_agent_role_arn():
    all_roles = [r for page in iam.get_paginator("list_roles").paginate()
                 for r in page["Roles"]]
    for prefix in ["BedrockAgentRole", "AmazonBedrockServiceRole"]:
        for role in all_roles:
            if role["RoleName"].startswith(prefix):
                return role["Arn"]
    trust = json.dumps({"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {
            "StringEquals": {"aws:SourceAccount": ACCOUNT},
            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:agent/*"},
        },
    }]})
    role = iam.create_role(RoleName="BedrockAgentExecutionRole",
                           AssumeRolePolicyDocument=trust)
    iam.attach_role_policy(RoleName="BedrockAgentExecutionRole",
                           PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockFullAccess")
    return role["Role"]["Arn"]


def _ensure_passrole(role_arn):
    policy = json.dumps({"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Action": "iam:PassRole", "Resource": role_arn,
        "Condition": {"StringEquals": {"iam:PassedToService": "bedrock.amazonaws.com"}},
    }]})
    try:
        iam.put_user_policy(UserName=USERNAME, PolicyName="BedrockPassAgentRole",
                            PolicyDocument=policy)
        info(f"iam:PassRole granted to: {USERNAME}")
    except Exception as e:
        warn(f"PassRole: {e}")


def _delete_agent_if_exists(name):
    try:
        for a in bedrock_agent.list_agents()["agentSummaries"]:
            if a["agentName"] == name:
                info(f"Deleting existing agent: {a['agentId']}")
                bedrock_agent.delete_agent(agentId=a["agentId"],
                                           skipResourceInUseCheck=True)
                for _ in range(24):
                    try:
                        bedrock_agent.get_agent(agentId=a["agentId"])
                        time.sleep(5)
                    except bedrock_agent.exceptions.ResourceNotFoundException:
                        info("Previous agent deleted")
                        break
    except Exception as e:
        warn(f"Cleanup: {e}")


def _wait_agent(agent_id, targets, timeout=120):
    for _ in range(timeout // 5):
        status = bedrock_agent.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        info(f"Agent status: {status}")
        if status in targets:
            return status
        if status == "FAILED":
            print("ERROR: Agent entered FAILED state"); sys.exit(1)
        time.sleep(5)
    return status


def _api_schema(title, path, op_id, required, props):
    return {"payload": json.dumps({
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {path: {"post": {
            "operationId": op_id,
            "summary": title,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "required": required, "properties": props,
            }}}},
            "responses": {"200": {"description": "Success"}},
        }}},
    })}


if os.path.exists(AGENT_ID_FILE):
    AGENT_ID = open(AGENT_ID_FILE).read().strip()
    info(f"Agent already exists: {AGENT_ID} - skipping creation")
else:
    agent_role_arn = _get_agent_role_arn()
    ok(f"Role: {agent_role_arn}")
    _ensure_passrole(agent_role_arn)
    _delete_agent_if_exists("RequirementsManagementAgent")

    resp     = bedrock_agent.create_agent(
        agentName               = "RequirementsManagementAgent",
        description             = "Agentic AI for requirements management from bid PDFs",
        foundationModel         = "anthropic.claude-3-5-sonnet-20241022-v2:0",
        agentResourceRoleArn    = agent_role_arn,
        idleSessionTTLInSeconds = 1800,
        instruction             = (
            "You are an expert Requirements Management AI Assistant. "
            "Process bid PDFs, extract requirements, assign domain experts, "
            "and generate compliance suggestions with grounded citations."
        ),
    )
    AGENT_ID = resp["agent"]["agentId"]
    ok(f"Agent created: {AGENT_ID}")
    _wait_agent(AGENT_ID, ["NOT_PREPARED", "PREPARED"])

    ACTION_GROUPS = [
        ("DocumentProcessor",     DOCUMENT_PROCESSOR_ARN,
         "/process-document",     "process_document",
         ["document_path"],
         {"document_path": {"type": "string"},
          "document_type": {"type": "string", "enum": ["pdf", "docx"]}}),
        ("RequirementsExtractor", REQUIREMENTS_EXTRACTOR_ARN,
         "/extract-requirements", "extract_requirements",
         ["document_id"],
         {"document_id":         {"type": "string"},
          "extraction_criteria": {"type": "object"}}),
        ("ExpertMatcher",         EXPERT_MATCHER_ARN,
         "/assign-experts",       "assign_experts",
         ["requirements"],
         {"requirements":        {"type": "array", "items": {"type": "object"}},
          "assignment_criteria": {"type": "object"}}),
        ("ComplianceChecker",     COMPLIANCE_CHECKER_ARN,
         "/check-compliance",     "check_compliance",
         ["requirement_id", "requirement_text"],
         {"requirement_id":   {"type": "string"},
          "requirement_text": {"type": "string"},
          "domain":           {"type": "string"}}),
    ]

    for ag_name, fn_arn, path, op_id, req, props in ACTION_GROUPS:
        if not fn_arn:
            warn(f"Skipping {ag_name} - no Lambda ARN")
            continue
        try:
            bedrock_agent.create_agent_action_group(
                agentId             = AGENT_ID,
                agentVersion        = "DRAFT",
                actionGroupName     = ag_name,
                description         = ag_name,
                actionGroupState    = "ENABLED",
                actionGroupExecutor = {"lambda": fn_arn},
                apiSchema           = _api_schema(ag_name, path, op_id, req, props),
            )
            ok(f"Action group: {ag_name}")
        except Exception as e:
            warn(f"Action group {ag_name}: {e}")

    bedrock_agent.prepare_agent(agentId=AGENT_ID)
    _wait_agent(AGENT_ID, ["PREPARED"])

    alias    = bedrock_agent.create_agent_alias(agentId=AGENT_ID,
                                                agentAliasName="production")
    ALIAS_ID = alias["agentAlias"]["agentAliasId"]
    ok(f"Alias: {ALIAS_ID}")

    with open(AGENT_ID_FILE,       "w") as f: f.write(AGENT_ID)
    with open(AGENT_ALIAS_ID_FILE, "w") as f: f.write(ALIAS_ID)

AGENT_ID = open(AGENT_ID_FILE).read().strip()
ALIAS_ID = (open(AGENT_ALIAS_ID_FILE).read().strip()
            if os.path.exists(AGENT_ALIAS_ID_FILE) else "")
ok(f"Agent: {AGENT_ID}  Alias: {ALIAS_ID}")

# =============================================================================
# STEP 4 - Initialize Database Schema
# =============================================================================
step("Step 4: Initialize Aurora PostgreSQL Schema")

# Migrate vector dimensions if tables already exist with wrong size
for sql in [
    "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024)",
    "ALTER TABLE domain_experts  ALTER COLUMN skill_embeddings TYPE vector(1024)",
    "DROP INDEX IF EXISTS idx_chunks_embedding",
]:
    try:
        _rds(sql)
        ok(f"Migration: {sql[:60]}")
    except Exception as e:
        info(f"Migration skipped: {str(e)[:70]}")

SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    """CREATE TABLE IF NOT EXISTS document_chunks (
        id SERIAL PRIMARY KEY,
        document_path VARCHAR(500) NOT NULL,
        chunk_id INTEGER NOT NULL,
        text_content TEXT NOT NULL,
        embedding vector(1024),
        entities JSONB,
        metadata JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS requirements (
        id SERIAL PRIMARY KEY,
        requirement_id VARCHAR(50) UNIQUE NOT NULL,
        document_id VARCHAR(100) NOT NULL,
        type VARCHAR(50) NOT NULL,
        category VARCHAR(100),
        priority VARCHAR(20),
        description TEXT NOT NULL,
        acceptance_criteria JSONB,
        domain VARCHAR(100),
        complexity VARCHAR(20),
        status VARCHAR(50) DEFAULT 'extracted',
        confidence_score FLOAT,
        source_chunk_ids INTEGER[],
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS domain_experts (
        id SERIAL PRIMARY KEY,
        expert_id VARCHAR(50) UNIQUE NOT NULL,
        name VARCHAR(200) NOT NULL,
        email VARCHAR(200) NOT NULL,
        department VARCHAR(100),
        skills JSONB NOT NULL,
        specializations JSONB NOT NULL,
        skill_embeddings vector(1024),
        current_workload INTEGER DEFAULT 0,
        max_workload INTEGER DEFAULT 10,
        availability_status VARCHAR(50) DEFAULT 'available',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS expert_assignments (
        id SERIAL PRIMARY KEY,
        requirement_id VARCHAR(50) NOT NULL,
        expert_id VARCHAR(50) NOT NULL,
        assignment_type VARCHAR(50) DEFAULT 'primary',
        confidence_score FLOAT,
        assignment_reason TEXT,
        status VARCHAR(50) DEFAULT 'assigned',
        assigned_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS compliance_suggestions (
        id SERIAL PRIMARY KEY,
        requirement_id VARCHAR(50) NOT NULL,
        regulation_type VARCHAR(100),
        suggestion_text TEXT NOT NULL,
        confidence_score FLOAT,
        source_documents JSONB,
        status VARCHAR(50) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_path   ON document_chunks(document_path)",
    "CREATE INDEX IF NOT EXISTS idx_reqs_domain   ON requirements(domain)",
    "CREATE INDEX IF NOT EXISTS idx_reqs_status   ON requirements(status)",
    "CREATE INDEX IF NOT EXISTS idx_experts_avail ON domain_experts(availability_status)",
    "CREATE INDEX IF NOT EXISTS idx_assign_req    ON expert_assignments(requirement_id)",
    "CREATE INDEX IF NOT EXISTS idx_assign_exp    ON expert_assignments(expert_id)",
]

for sql in SCHEMA:
    label = sql.strip().replace("\n", " ")[:60]
    try:
        _rds(sql)
        ok(label)
    except Exception as e:
        if "already exists" in str(e).lower():
            info(f"Already exists: {label}")
        else:
            warn(f"Schema error: {str(e)[:80]}")

ok("Database schema initialized")

# =============================================================================
# STEP 4b - Load Expert Profiles
# =============================================================================
EXPERTS_FILE = os.path.join(ROOT, "examples", "expert_profiles.json")
with open(EXPERTS_FILE) as f:
    experts = json.load(f)

INSERT_SQL = """
    INSERT INTO domain_experts
        (expert_id, name, email, department, skills, specializations,
         skill_embeddings, current_workload, max_workload, availability_status)
    VALUES
        (:expert_id,:name,:email,:department,
         :skills::jsonb,:specializations::jsonb,:skill_embeddings::vector,
         :current_workload,:max_workload,:availability_status)
    ON CONFLICT (expert_id) DO UPDATE SET
        skills=EXCLUDED.skills,
        specializations=EXCLUDED.specializations,
        skill_embeddings=EXCLUDED.skill_embeddings,
        updated_at=NOW()
"""

for expert in experts:
    skill_text = " ".join(expert["skills"] + expert["specializations"])
    emb        = json.loads(bedrock_rt.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": skill_text[:8000]}),
    )["body"].read())["embedding"]

    info(f"Loading: {expert['expert_id']} - {expert['department']}")
    rds.execute_statement(
        resourceArn=DB_CLUSTER_ARN,
        secretArn=DB_SECRET_ARN,
        database="requirements_db",
        sql=INSERT_SQL,
        parameters=[
            {"name": "expert_id",           "value": {"stringValue": expert["expert_id"]}},
            {"name": "name",                "value": {"stringValue": expert["name"]}},
            {"name": "email",               "value": {"stringValue": expert["email"]}},
            {"name": "department",          "value": {"stringValue": expert["department"]}},
            {"name": "skills",              "value": {"stringValue": json.dumps(expert["skills"])}},
            {"name": "specializations",     "value": {"stringValue": json.dumps(expert["specializations"])}},
            {"name": "skill_embeddings",    "value": {"stringValue": str(emb)}},
            {"name": "current_workload",    "value": {"longValue":   expert.get("current_workload", 0)}},
            {"name": "max_workload",        "value": {"longValue":   expert.get("max_workload", 10)}},
            {"name": "availability_status", "value": {"stringValue": expert.get("availability_status", "available")}},
        ],
    )

ok(f"Loaded {len(experts)} expert profiles")

# =============================================================================
# STEP 5 - Upload Sample Documents
# =============================================================================
step("Step 5: Upload Sample Documents")

ok(f"Using bucket: {BUCKET_NAME}")

for prefix in ["bids/", "requirements/", "regulatory/", "experts/"]:
    s3.put_object(Bucket=BUCKET_NAME, Key=prefix, Body=b"")
ok("S3 folder structure created")

sample_pdf = os.path.join(ROOT, "examples", "sample_requirements.pdf")
if os.path.exists(sample_pdf):
    s3.upload_file(sample_pdf, BUCKET_NAME, "bids/sample_requirements.pdf")
    ok(f"Uploaded: s3://{BUCKET_NAME}/bids/sample_requirements.pdf")
    fn_name = DOCUMENT_PROCESSOR_ARN.split(":")[-1]
    payload = json.dumps({
        "actionGroup": "DocumentProcessor",
        "apiPath":     "/process-document",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "document_path", "value": "bids/sample_requirements.pdf"},
        ]}}},
    }).encode()
    resp   = lambda_client.invoke(FunctionName=fn_name, Payload=payload)
    result = json.loads(resp["Payload"].read())
    ok(f"Document processing triggered: {result.get('statusCode', 'invoked')}")
else:
    warn("No sample PDF at examples/sample_requirements.pdf")
    info(f"Upload any PDF: aws s3 cp your-bid.pdf s3://{BUCKET_NAME}/bids/")

# =============================================================================
# STEP 6 - Write CI/CD Secrets
# =============================================================================
step("Step 6: CI/CD GitHub Actions Secrets")

_frozen = _boto_session.get_credentials().get_frozen_credentials()
secrets = {
    "AWS_ACCESS_KEY_ID":          _frozen.access_key,
    "AWS_SECRET_ACCESS_KEY":      _frozen.secret_key,
    "AWS_ACCESS_KEY_ID_PROD":     _frozen.access_key,
    "AWS_SECRET_ACCESS_KEY_PROD": _frozen.secret_key,
    "DB_CLUSTER_ARN":             DB_CLUSTER_ARN,
    "DB_SECRET_ARN":              DB_SECRET_ARN,
    "BUCKET_NAME":                BUCKET_NAME,
    "OPENSEARCH_ENDPOINT":        OPENSEARCH_ENDPOINT,
    "AGENT_ID":                   AGENT_ID,
    "AGENT_ALIAS_ID":             ALIAS_ID,
    "API_ENDPOINT":               API_ENDPOINT,
}

secrets_path = os.path.join(ROOT, ".env.secrets")
with open(secrets_path, "w") as f:
    f.write("# GitHub Actions secrets - DO NOT COMMIT\n")
    for k, v in secrets.items():
        f.write(f"{k}={v}\n")

gitignore_path = os.path.join(ROOT, ".gitignore")
if os.path.exists(gitignore_path):
    content = open(gitignore_path).read()
    if ".env.secrets" not in content:
        with open(gitignore_path, "a") as f:
            f.write("\n.env.secrets\n")

w = max(len(k) for k in secrets) + 2
print(f"\n{Y}Add these to GitHub -> Settings -> Secrets -> Actions:{N}\n")
for k, v in secrets.items():
    print(f"  {C}{k:<{w}}{N} {v}")

ok("Secrets saved to .env.secrets")

# =============================================================================
# DONE
# =============================================================================
print(f"""
{G}+--------------------------------------------------------------+
|         Post-deployment setup complete!                      |
+--------------------------------------------------------------+{N}

  {C}API Endpoint:{N}  {API_ENDPOINT}
  {C}Agent ID:{N}      {AGENT_ID}
  {C}Agent Alias:{N}   {ALIAS_ID}
  {C}S3 Bucket:{N}     {BUCKET_NAME}
  {C}OpenSearch:{N}    {OPENSEARCH_ENDPOINT}

  {Y}Test the agent:{N}
  aws bedrock-agent-runtime invoke-agent \\
    --agent-id {AGENT_ID} \\
    --agent-alias-id {ALIAS_ID} \\
    --session-id test-001 \\
    --input-text "Process the bid at bids/sample_requirements.pdf" \\
    --region {REGION} output.json
""")
