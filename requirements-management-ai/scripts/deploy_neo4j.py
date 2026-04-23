"""
deploy_neo4j.py
===============
Migrates the graph architecture from Aurora to Neo4j.

Steps:
  1. Verify Neo4j connection
  2. Create Neo4j schema (constraints + indexes)
  3. Migrate data from Aurora graph tables to Neo4j
  4. Rebuild Lambda layer with neo4j package
  5. Redeploy all Lambdas with Neo4j env vars + graph_db.py
  6. Update Bedrock AgentCore with Neo4j-aware instruction
  7. Test end-to-end

Usage:
  NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io \\
  NEO4J_USER=neo4j \\
  NEO4J_PASSWORD=<password> \\
  python scripts/deploy_neo4j.py
"""
import boto3, json, os, sys, time, zipfile, tempfile, shutil

ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION = "us-east-1"

# ── Neo4j connection from env ─────────────────────────────────────────────────
NEO4J_URI  = os.environ.get("NEO4J_URI",      "")
NEO4J_USER = os.environ.get("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "")

if not NEO4J_URI or not NEO4J_PASS:
    print("""
ERROR: Neo4j credentials not set.

Set these environment variables before running:

  In Git Bash:
    export NEO4J_URI="neo4j+s://xxxxx.databases.neo4j.io"
    export NEO4J_USER="neo4j"
    export NEO4J_PASSWORD="your-password"

  Get a free Neo4j AuraDB instance at: https://console.neo4j.io
  (Free tier: 200k nodes, 400k relationships)
""")
    sys.exit(1)

with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values(): OUT.update(v)

DB_ARN    = OUT["DbClusterArn"]
DB_SECRET = OUT["DbSecretArn"]
AGENT_ID  = open(os.path.join(ROOT, "agent_id.txt")).read().strip()
ALIAS_ID  = open(os.path.join(ROOT, "agent_alias_id.txt")).read().strip()

lam   = boto3.client("lambda",       region_name=REGION)
rds   = boto3.client("rds-data",     region_name=REGION)
iam   = boto3.client("iam",          region_name=REGION)
agent = boto3.client("bedrock-agent",region_name=REGION)
rt    = boto3.client("bedrock-agent-runtime", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

GRAPH_DB_SRC = os.path.join(ROOT, "src", "graph", "graph_db.py")

ROLE_ARN = next(
    r["Arn"] for page in iam.get_paginator("list_roles").paginate()
    for r in page["Roles"]
    if r["RoleName"].startswith("RequirementsManagementSta-LambdaExecution")
)
SHARED_ENV = lam.get_function_configuration(
    FunctionName=OUT["DocumentProcessorArn"].split(":")[-1]
)["Environment"]["Variables"]

# Add Neo4j vars to shared env
NEO4J_ENV = {
    **SHARED_ENV,
    "NEO4J_URI":      NEO4J_URI,
    "NEO4J_USER":     NEO4J_USER,
    "NEO4J_PASSWORD": NEO4J_PASS,
}


def rds_json(sql, params=None):
    kw = dict(resourceArn=DB_ARN, secretArn=DB_SECRET,
              database="requirements_db", sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords","[]"))


def embed(text):
    r = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                             body=json.dumps({"inputText":text[:8000]}))
    return json.loads(r["body"].read())["embedding"]


def zip_lambda(src_dir, extra_files=None):
    tmp = tempfile.mkdtemp()
    try:
        for f in os.listdir(src_dir):
            fp = os.path.join(src_dir, f)
            if os.path.isfile(fp) and f.endswith(".py") and not f.endswith(".pyc"):
                shutil.copy2(fp, os.path.join(tmp, f))
        for src_path, dest_name in (extra_files or []):
            shutil.copy2(src_path, os.path.join(tmp, dest_name))
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


def wait_lambda(fn_name):
    for _ in range(30):
        cfg = lam.get_function_configuration(FunctionName=fn_name)
        if cfg["LastUpdateStatus"] == "Successful": return
        if cfg["LastUpdateStatus"] == "Failed":
            raise RuntimeError(f"Lambda update failed: {fn_name}")
        time.sleep(3)


# =============================================================================
# Step 1: Verify Neo4j connection
# =============================================================================
print("\n" + "="*60)
print("Step 1: Verifying Neo4j connection")
print("="*60)

sys.path.insert(0, os.path.join(ROOT, "src", "graph"))
os.environ["NEO4J_URI"]      = NEO4J_URI
os.environ["NEO4J_USER"]     = NEO4J_USER
os.environ["NEO4J_PASSWORD"] = NEO4J_PASS

import graph_db as g

try:
    result = g._run("RETURN 'Neo4j connected' AS msg, datetime() AS ts")
    print(f"  Connected: {result[0]['msg']} at {result[0]['ts']}")
except Exception as e:
    print(f"  ERROR: Cannot connect to Neo4j: {e}")
    print(f"  URI: {NEO4J_URI}")
    sys.exit(1)


# =============================================================================
# Step 2: Create Neo4j schema
# =============================================================================
print("\n" + "="*60)
print("Step 2: Creating Neo4j schema (constraints + indexes)")
print("="*60)

g.init_schema()


# =============================================================================
# Step 3: Migrate data from Aurora to Neo4j
# =============================================================================
print("\n" + "="*60)
print("Step 3: Migrating data from Aurora to Neo4j")
print("="*60)

# 3a. Documents
doc_rows = rds_json("SELECT DISTINCT document_path FROM document_chunks")
for row in doc_rows:
    path = row["document_path"]
    name = path.split("/")[-1]
    g.store_document(path, name)
    print(f"  Document: {name}")

# 3b. Requirements (with embeddings)
req_rows = rds_json(
    "SELECT requirement_id,document_id,type,priority,description,domain,confidence_score "
    "FROM requirements LIMIT 500")
print(f"  Migrating {len(req_rows)} requirements...")
for i, row in enumerate(req_rows):
    try:
        emb = embed(row["description"])
        g.store_requirement(
            row["requirement_id"], row["document_id"],
            row["description"],    row.get("type","functional"),
            row.get("priority","medium"), row.get("domain","general"),
            float(row.get("confidence_score",0.8)), emb)
        if (i+1) % 10 == 0:
            print(f"    {i+1}/{len(req_rows)} requirements migrated")
    except Exception as e:
        print(f"  Req error {row['requirement_id']}: {e}")

# 3c. Experts (with embeddings)
exp_rows = rds_json(
    "SELECT expert_id,name,department,skills,specializations FROM domain_experts")
print(f"  Migrating {len(exp_rows)} experts...")
for row in exp_rows:
    try:
        skills = json.loads(row["skills"]) if isinstance(row["skills"],str) else row["skills"] or []
        specs  = json.loads(row["specializations"]) if isinstance(row["specializations"],str) else row["specializations"] or []
        emb    = embed(" ".join(skills+specs))
        g.store_expert(row["expert_id"], row["name"], row["department"], skills, specs, emb)
        print(f"  Expert: {row['name']} ({row['department']})")
    except Exception as e:
        print(f"  Expert error {row['expert_id']}: {e}")

# 3d. Link similar requirements
print("  Creating SIMILAR_TO relationships...")
req_nodes = g.find_nodes("Requirement", limit=200)
linked = 0
for req in req_nodes[:50]:  # limit to avoid too many embeddings
    props = req.get("properties",{})
    req_id = props.get("id","")
    desc   = props.get("description","")
    if not req_id or not desc: continue
    try:
        emb     = embed(desc)
        similar = g.semantic_search_nodes(emb, label="Requirement", top_k=4)
        for s in similar:
            s_id = s.get("properties",{}).get("id","")
            sim  = float(s.get("similarity",0))
            if s_id and s_id != req_id and sim > 0.75:
                g.link_similar_requirements(req_id, s_id, sim)
                linked += 1
    except Exception as e:
        pass
print(f"  Created {linked} SIMILAR_TO relationships")

stats = g.graph_stats()
print(f"\n  Neo4j graph stats:")
print(f"    Nodes: {stats['total_nodes']} — {stats['nodes']}")
print(f"    Edges: {stats['total_edges']} — {stats['edges']}")


# =============================================================================
# Step 4: Rebuild Lambda layer with neo4j
# =============================================================================
print("\n" + "="*60)
print("Step 4: Rebuilding Lambda layer with neo4j package")
print("="*60)

import subprocess
tmp_layer = tempfile.mkdtemp()
layer_python = os.path.join(tmp_layer, "python")
os.makedirs(layer_python)

packages = [
    "aws-lambda-powertools[all]", "boto3", "requests", "numpy",
    "aws-xray-sdk", "opensearch-py", "requests-aws4auth", "pypdf", "neo4j",
]
print(f"  Installing {len(packages)} packages...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "--quiet",
     "--target", layer_python,
     "--platform", "manylinux2014_x86_64",
     "--python-version", "3.11",
     "--only-binary=:all:"] + packages,
    capture_output=True, text=True)
if result.returncode != 0:
    # Fallback without platform constraint
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "--target", layer_python] + packages)

# Zip the layer
layer_zip = tempfile.mktemp(suffix=".zip")
with zipfile.ZipFile(layer_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(tmp_layer):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if not file.endswith(".pyc"):
                fp = os.path.join(root, file)
                zf.write(fp, os.path.relpath(fp, tmp_layer))
shutil.rmtree(tmp_layer)

with open(layer_zip, "rb") as f:
    layer_data = f.read()
os.unlink(layer_zip)
print(f"  Layer size: {len(layer_data)/1024/1024:.1f} MB")

layer_resp = lam.publish_layer_version(
    LayerName          = "RequirementsManagementDeps",
    Description        = "Requirements Management AI deps including neo4j",
    Content            = {"ZipFile": layer_data},
    CompatibleRuntimes = ["python3.11","python3.12"],
)
NEW_LAYER_ARN = layer_resp["LayerVersionArn"]
print(f"  Published: {NEW_LAYER_ARN}")


# =============================================================================
# Step 5: Redeploy all Lambdas with Neo4j env vars
# =============================================================================
print("\n" + "="*60)
print("Step 5: Redeploying Lambdas with Neo4j")
print("="*60)

LAMBDAS = {
    "GraphAgent":           ("GraphAgent",                                    "src/lambda/graph-agent"),
    "DocumentProcessor":    (OUT["DocumentProcessorArn"].split(":")[-1],      "src/lambda/document-processor"),
    "RequirementsExtractor":(OUT["RequirementsExtractorArn"].split(":")[-1],  "src/lambda/requirements-extractor"),
    "ExpertMatcher":        (OUT["ExpertMatcherArn"].split(":")[-1],          "src/lambda/expert-matcher"),
    "ComplianceChecker":    (OUT["ComplianceCheckerArn"].split(":")[-1],      "src/lambda/compliance-checker"),
}

for name, (fn_name, src_rel) in LAMBDAS.items():
    src_dir  = os.path.join(ROOT, src_rel)
    zip_data = zip_lambda(src_dir, [(GRAPH_DB_SRC, "graph_db.py")])
    lam.update_function_code(FunctionName=fn_name, ZipFile=zip_data)
    wait_lambda(fn_name)
    # Update env vars with Neo4j credentials
    lam.update_function_configuration(
        FunctionName = fn_name,
        Layers       = [NEW_LAYER_ARN],
        Environment  = {"Variables": NEO4J_ENV},
    )
    wait_lambda(fn_name)
    print(f"  Deployed: {name} ({len(zip_data)/1024:.1f} KB)")


# =============================================================================
# Step 6: Update Bedrock AgentCore
# =============================================================================
print("\n" + "="*60)
print("Step 6: Updating Bedrock AgentCore instruction")
print("="*60)

INSTRUCTION = """You are a Requirements Management AI powered by Neo4j Graph Database.

NEO4J GRAPH CONTAINS:
- (:Document) nodes — all uploaded bid PDFs
- (:Requirement) nodes — extracted requirements with embeddings
- (:Expert) nodes — domain experts with specializations
- (:Domain) nodes — security, performance, integration, data, compliance, etc.
- (:Entity) nodes — technical entities extracted from documents
- (:Project) nodes — past projects

NEO4J RELATIONSHIPS:
- (:Document)-[:CONTAINS]->(:Requirement)
- (:Requirement)-[:EXTRACTED_FROM]->(:Document)
- (:Expert)-[:SPECIALIZES_IN]->(:Domain)
- (:Expert)-[:ASSIGNED_TO {score}]->(:Requirement)
- (:Requirement)-[:SIMILAR_TO {similarity}]->(:Requirement)
- (:Document)-[:MENTIONS]->(:Entity)
- (:Entity)-[:RELATES_TO {predicate}]->(:Entity)

ORCHESTRATION — ALWAYS follow:
1. Content questions -> GraphAgent action=semantic_search OR DocumentSearch
2. Expert assignment -> GraphAgent action=find_experts then action=assign_expert
3. Past requirements -> GraphAgent action=past_requirements
4. Graph traversal   -> GraphAgent action=traverse or action=neighbourhood
5. Cypher queries    -> GraphAgent action=cypher_query with Cypher statement
6. Compliance        -> ComplianceChecker (uses Neo4j internally)
7. NEVER answer from memory — always query Neo4j or DocumentSearch first

DOCUMENT ROUTING (set document_filter in DocumentSearch):
- charging/alternator -> CH_Charging System
- EFI/fuel injection  -> EF_EFI System
- emission/exhaust    -> EC_Emission Control Systems

EXAMPLE CYPHER QUERIES you can run via GraphAgent action=cypher_query:
- Find all requirements for a domain:
  MATCH (r:Requirement {domain:'security'}) RETURN r.id, r.description LIMIT 10
- Find experts for a requirement:
  MATCH (e:Expert)-[:ASSIGNED_TO]->(r:Requirement {id:'REQ-001'}) RETURN e.name, e.department
- Find similar requirements:
  MATCH (r:Requirement {id:'REQ-001'})-[:SIMILAR_TO]->(s:Requirement) RETURN s.description, s.similarity"""

ag_info = agent.get_agent(agentId=AGENT_ID)["agent"]
agent.update_agent(
    agentId              = AGENT_ID,
    agentName            = ag_info["agentName"],
    foundationModel      = ag_info["foundationModel"],
    agentResourceRoleArn = ag_info["agentResourceRoleArn"],
    instruction          = INSTRUCTION,
    idleSessionTTLInSeconds = 1800,
)
print("  Instruction updated")

agent.prepare_agent(agentId=AGENT_ID)
for _ in range(24):
    status = agent.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    print(f"  Status: {status}")
    if status == "PREPARED": break
    if status == "FAILED":   raise RuntimeError("Agent failed")
    time.sleep(5)

try:
    agent.delete_agent_alias(agentId=AGENT_ID, agentAliasId=ALIAS_ID)
    time.sleep(3)
except: pass

new_alias = agent.create_agent_alias(agentId=AGENT_ID, agentAliasName="production")
new_id    = new_alias["agentAlias"]["agentAliasId"]
for _ in range(12):
    s = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=new_id)["agentAlias"]["agentAliasStatus"]
    print(f"  Alias: {s}")
    if s == "PREPARED": break
    time.sleep(5)

with open(os.path.join(ROOT, "agent_alias_id.txt"), "w") as f:
    f.write(new_id)

# Save Neo4j config for backend
neo4j_config = {"NEO4J_URI": NEO4J_URI, "NEO4J_USER": NEO4J_USER}
with open(os.path.join(ROOT, "neo4j_config.json"), "w") as f:
    json.dump(neo4j_config, f, indent=2)
print("  Saved neo4j_config.json (without password)")


# =============================================================================
# Step 7: Test
# =============================================================================
print("\n" + "="*60)
print("Step 7: Testing Neo4j graph architecture")
print("="*60)

# Test GraphAgent
r = lam.invoke(FunctionName="GraphAgent",
               Payload=json.dumps({"actionGroup":"GraphAgent","apiPath":"/graph",
                                   "httpMethod":"POST","requestBody":{"content":{"application/json":
                                   {"properties":[{"name":"action","value":"graph_stats"}]}}}}))
body = json.loads(json.loads(r["Payload"].read())["response"]["responseBody"]["application/json"]["body"])
print(f"  Neo4j graph: {body.get('total_nodes',0)} nodes, {body.get('total_edges',0)} edges")
print(f"  Node types:  {body.get('nodes',{})}")

# Test agent
resp = rt.invoke_agent(agentId=AGENT_ID, agentAliasId=new_id,
                       sessionId="test-neo4j-001",
                       inputText="What are the voltage requirements in the charging system?")
out = "".join(e["chunk"]["bytes"].decode() for e in resp["completion"] if "chunk" in e)
print(f"\n  Agent test: {out[:300]}")

print(f"\n{'='*60}")
print("Neo4j graph architecture deployment complete!")
print(f"  Neo4j URI:   {NEO4J_URI}")
print(f"  Graph nodes: {body.get('total_nodes',0)}")
print(f"  Graph edges: {body.get('total_edges',0)}")
print(f"  Agent ID:    {AGENT_ID}")
print(f"  Alias ID:    {new_id}")
print(f"  Layer ARN:   {NEW_LAYER_ARN}")
print(f"{'='*60}")
