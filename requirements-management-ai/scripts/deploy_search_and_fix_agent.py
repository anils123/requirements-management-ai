"""
deploy_search_and_fix_agent.py
Deploys DocumentSearch Lambda, updates agent instruction to be a search engine,
re-attaches all 5 action groups.
"""
import boto3, json, os, time, zipfile, tempfile

ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION   = "us-east-1"
AGENT_ID = open(os.path.join(ROOT, "agent_id.txt")).read().strip()
ALIAS_ID = open(os.path.join(ROOT, "agent_alias_id.txt")).read().strip()

with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values(): OUT.update(v)

lam    = boto3.client("lambda",       region_name=REGION)
iam    = boto3.client("iam",          region_name=REGION)
agent  = boto3.client("bedrock-agent",region_name=REGION)
rt     = boto3.client("bedrock-agent-runtime", region_name=REGION)

LAYER_ARN = "arn:aws:lambda:us-east-1:672996977856:layer:RequirementsManagementDeps:2"
ROLE_ARN  = next(
    r["Arn"] for page in iam.get_paginator("list_roles").paginate()
    for r in page["Roles"] if r["RoleName"].startswith("RequirementsManagementSta-LambdaExecution")
)

# ── Step 1: Deploy DocumentSearch Lambda ─────────────────────────────────────
print("Deploying DocumentSearch Lambda...")
src = os.path.join(ROOT, "src", "lambda", "document-search")
tmp = tempfile.mktemp(suffix=".zip")
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in os.listdir(src):
        if not f.endswith(".pyc"):
            zf.write(os.path.join(src, f), f)
with open(tmp, "rb") as f:
    zip_data = f.read()
os.unlink(tmp)

# Get shared env from existing Lambda
existing_env = lam.get_function_configuration(
    FunctionName=OUT["DocumentProcessorArn"].split(":")[-1]
)["Environment"]["Variables"]

try:
    lam.create_function(
        FunctionName = "DocumentSearch",
        Runtime      = "python3.11",
        Role         = ROLE_ARN,
        Handler      = "document_search.handler",
        Code         = {"ZipFile": zip_data},
        Timeout      = 60,
        MemorySize   = 512,
        Layers       = [LAYER_ARN],
        Environment  = {"Variables": existing_env},
        Description  = "Semantic search across all uploaded PDFs",
    )
    print("  Created DocumentSearch Lambda")
except lam.exceptions.ResourceConflictException:
    lam.update_function_code(FunctionName="DocumentSearch", ZipFile=zip_data)
    for _ in range(20):
        if lam.get_function_configuration(FunctionName="DocumentSearch")["LastUpdateStatus"] == "Successful":
            break
        time.sleep(3)
    print("  Updated DocumentSearch Lambda")

# Wait for active
for _ in range(20):
    state = lam.get_function_configuration(FunctionName="DocumentSearch")["State"]
    if state == "Active": break
    time.sleep(3)

SEARCH_FN_ARN = lam.get_function(FunctionName="DocumentSearch")["Configuration"]["FunctionArn"]
print(f"  ARN: {SEARCH_FN_ARN}")

# Allow Bedrock to invoke it
try:
    lam.add_permission(
        FunctionName = "DocumentSearch",
        StatementId  = "BedrockInvoke",
        Action       = "lambda:InvokeFunction",
        Principal    = "bedrock.amazonaws.com",
        SourceArn    = f"arn:aws:bedrock:{REGION}:{OUT['DbClusterArn'].split(':')[4]}:agent/*",
    )
except lam.exceptions.ResourceConflictException:
    pass

# ── Step 2: Update agent instruction ─────────────────────────────────────────
print("\nUpdating agent instruction...")

# Build document list for the instruction
doc_list = "\n".join([
    "- bids/CH_Charging System.pdf  → document_id: 'CH_Charging System'",
    "- bids/EF_EFI System.pdf       → document_id: 'EF_EFI System'",
    "- bids/rail-train (1).pdf      → document_id: 'rail-train (1)'",
    "- bids/sample_requirements.pdf → document_id: 'sample_requirements'",
    "- bids/sample_requirements.txt → document_id: 'sample_requirements'",
])

INSTRUCTION = f"""You are an intelligent Requirements Management Search Engine with full access to all uploaded bid documents and extracted requirements.

AVAILABLE DOCUMENTS IN THE SYSTEM:
{doc_list}

CRITICAL RULES — NEVER break these:
1. NEVER ask the user to provide a document path or S3 key. You already have all documents.
2. NEVER say "I cannot directly process documents" or "please provide the document path".
3. For ANY question about document content, requirements, specifications, or technical details — ALWAYS call DocumentSearch with action="search" and the user's question as the query.
4. To list all documents — call DocumentSearch with action="list_documents".
5. To list requirements — call DocumentSearch with action="list_requirements" or call RequirementsExtractor.
6. To process a NEW uploaded document — call DocumentProcessor with the s3 key.
7. To assign experts — call ExpertMatcher.
8. To check compliance — call ComplianceChecker.

SEARCH BEHAVIOR:
- Search across ALL documents by default (leave document_filter empty).
- If the user mentions a specific document, set document_filter to its name.
- Always return the answer WITH citations showing which document and chunk the answer came from.
- For "what requirements exist" → use action="list_requirements".
- For "what documents are uploaded" → use action="list_documents".
- For any technical question → use action="search" with the question as query.

You are a search engine. Answer every question by searching the document database first."""

ag_info = agent.get_agent(agentId=AGENT_ID)["agent"]
agent.update_agent(
    agentId              = AGENT_ID,
    agentName            = ag_info["agentName"],
    foundationModel      = ag_info["foundationModel"],
    agentResourceRoleArn = ag_info["agentResourceRoleArn"],
    instruction          = INSTRUCTION,
    idleSessionTTLInSeconds = ag_info.get("idleSessionTTLInSeconds", 1800),
)
print("  Instruction updated")

# ── Step 3: Delete agent entirely and recreate fresh ─────────────────────────
print("\nDeleting agent and recreating fresh...")
try:
    agent.delete_agent(agentId=AGENT_ID, skipResourceInUseCheck=True)
    for _ in range(24):
        try:
            agent.get_agent(agentId=AGENT_ID)
            time.sleep(5)
        except agent.exceptions.ResourceNotFoundException:
            print("  Agent deleted")
            break
except Exception as e:
    print(f"  Delete warning: {e}")

# Recreate agent
ag_role = next(
    r["Arn"] for page in iam.get_paginator("list_roles").paginate()
    for r in page["Roles"] if r["RoleName"].startswith("AmazonBedrockServiceRole")
)
new_agent = agent.create_agent(
    agentName               = "RequirementsManagementAgent",
    foundationModel         = "amazon.nova-micro-v1:0",
    agentResourceRoleArn    = ag_role,
    instruction             = INSTRUCTION,
    idleSessionTTLInSeconds = 1800,
    description             = "Requirements Management Search Engine",
)
AGENT_ID = new_agent["agent"]["agentId"]
print(f"  New agent: {AGENT_ID}")
for _ in range(24):
    s = agent.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    if s in ("NOT_PREPARED","PREPARED"): break
    time.sleep(5)

with open(os.path.join(ROOT, "agent_id.txt"), "w") as f:
    f.write(AGENT_ID)

def schema(title, path, op_id, desc, required, props):
    return {"payload": json.dumps({
        "openapi":"3.0.0","info":{"title":title,"version":"1.0.0"},
        "paths":{path:{"post":{
            "operationId":op_id,"summary":title,"description":desc,
            "requestBody":{"required":True,"content":{"application/json":{"schema":{
                "type":"object","required":required,"properties":props}}}},
            "responses":{"200":{"description":"Success","content":{"application/json":{"schema":{"type":"object"}}}}},
        }}},
    })}

ACTION_GROUPS = [
    {
        "name": "DocumentSearch",
        "desc": "Search across ALL uploaded PDF documents semantically. Use action='search' for questions, action='list_documents' to list PDFs, action='list_requirements' to list requirements. ALWAYS call this first for any content question.",
        "arn":  SEARCH_FN_ARN,
        "path": "/search",
        "op":   "search_documents",
        "req":  ["action"],
        "props": {
            "action":          {"type":"string","enum":["search","list_documents","list_requirements"],
                                "description":"search=semantic search, list_documents=list all PDFs, list_requirements=list all requirements"},
            "query":           {"type":"string","description":"Search query for semantic search"},
            "document_filter": {"type":"string","description":"Optional: filter by document name e.g. 'EF_EFI System'"},
            "top_k":           {"type":"integer","description":"Number of results (default 8)"},
        },
    },
    {
        "name": "DocumentProcessor",
        "desc": "Process a NEW uploaded PDF document — extract text, embeddings, and knowledge graph. Only call this for newly uploaded documents not yet in the system.",
        "arn":  OUT["DocumentProcessorArn"],
        "path": "/process-document",
        "op":   "process_document",
        "req":  ["document_path"],
        "props": {
            "document_path": {"type":"string","description":"S3 key e.g. bids/myfile.pdf"},
            "document_type": {"type":"string","enum":["pdf","txt","docx"]},
        },
    },
    {
        "name": "RequirementsExtractor",
        "desc": "Extract and store structured requirements from a processed document. Use document_id without path prefix or extension.",
        "arn":  OUT["RequirementsExtractorArn"],
        "path": "/extract-requirements",
        "op":   "extract_requirements",
        "req":  ["document_id"],
        "props": {
            "document_id":         {"type":"string","description":"Document ID e.g. 'EF_EFI System'"},
            "extraction_criteria": {"type":"object","description":"Optional filters"},
        },
    },
    {
        "name": "ExpertMatcher",
        "desc": "Assign domain experts to requirements using semantic similarity and workload balancing.",
        "arn":  OUT["ExpertMatcherArn"],
        "path": "/assign-experts",
        "op":   "assign_experts",
        "req":  ["requirements"],
        "props": {
            "requirements":        {"type":"array","items":{"type":"object"},
                                    "description":"List of requirement objects"},
            "assignment_criteria": {"type":"object","description":"Optional criteria"},
        },
    },
    {
        "name": "ComplianceChecker",
        "desc": "Generate compliance suggestions for a requirement using regulations and past project data.",
        "arn":  OUT["ComplianceCheckerArn"],
        "path": "/check-compliance",
        "op":   "check_compliance",
        "req":  ["requirement_id","requirement_text"],
        "props": {
            "requirement_id":   {"type":"string"},
            "requirement_text": {"type":"string"},
            "domain":           {"type":"string"},
        },
    },
]

for ag in ACTION_GROUPS:
    agent.create_agent_action_group(
        agentId=AGENT_ID, agentVersion="DRAFT",
        actionGroupName    = ag["name"],
        description        = ag["desc"][:200],
        actionGroupState   = "ENABLED",
        actionGroupExecutor= {"lambda": ag["arn"]},
        apiSchema          = schema(ag["name"], ag["path"], ag["op"],
                                    ag["desc"][:200], ag["req"], ag["props"]),
    )
    print(f"  Created: {ag['name']}")
    time.sleep(1)

# ── Step 4: Prepare + new alias ───────────────────────────────────────────────
print("\nPreparing agent...")
agent.prepare_agent(agentId=AGENT_ID)
for _ in range(30):
    s = agent.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    print(f"  Status: {s}")
    if s == "PREPARED": break
    if s == "FAILED":   raise RuntimeError("Agent failed")
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

# ── Step 5: Test ──────────────────────────────────────────────────────────────
print("\nTesting...")
for q in ["What documents are available?",
          "What are the fuel system requirements in the EFI document?"]:
    resp = rt.invoke_agent(agentId=AGENT_ID, agentAliasId=new_id,
                           sessionId=f"test-{q[:10]}", inputText=q)
    out = "".join(e["chunk"]["bytes"].decode() for e in resp["completion"] if "chunk" in e)
    print(f"\nQ: {q}\nA: {out[:300]}")

with open(os.path.join(ROOT, "agent_alias_id.txt"), "w") as f:
    f.write(new_id)
print(f"\nDone. New alias: {new_id}")
