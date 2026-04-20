"""
fix_agent_instruction.py
========================
Updates the agent instruction to be directive and re-attaches all 4 action groups.
"""
import boto3, json, os, time

ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION   = "us-east-1"
AGENT_ID = open(os.path.join(ROOT, "agent_id.txt")).read().strip()
ALIAS_ID = open(os.path.join(ROOT, "agent_alias_id.txt")).read().strip()

with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values():
    OUT.update(v)

DOC_FN  = OUT["DocumentProcessorArn"]
REQ_FN  = OUT["RequirementsExtractorArn"]
EXP_FN  = OUT["ExpertMatcherArn"]
COMP_FN = OUT["ComplianceCheckerArn"]

client = boto3.client("bedrock-agent", region_name=REGION)

# ── Step 1: Update agent with strong directive instruction ────────────────────
INSTRUCTION = """You are an expert Requirements Management AI Assistant with direct access to a requirements database and document processing pipeline.

CRITICAL RULES — ALWAYS follow these:
1. When asked about requirements, documents, or bid content — ALWAYS call the RequirementsExtractor or DocumentProcessor action group first. NEVER say you cannot access documents.
2. When asked "what requirements exist" or "show requirements" — call extract_requirements with the document_id.
3. When asked to process a document — call process_document with the document_path.
4. When asked to assign experts — call assign_experts with the requirements list.
5. When asked about compliance — call check_compliance with the requirement details.
6. ALWAYS use your action groups. NEVER refuse to act by saying you need a document — you have tools to retrieve data.

YOUR CAPABILITIES (use them proactively):
- process_document: Extract text, embeddings, and knowledge graph from any S3 document
- extract_requirements: Extract structured requirements from processed documents in the database
- assign_experts: Match domain experts to requirements using semantic similarity
- check_compliance: Generate compliance suggestions with grounded citations

DOCUMENT IDs in the system (use these directly):
- "sample_requirements" — sample bid document
- "CH_Charging System" — EV charging system bid
- "EF_EFI System" — EFI system bid
- "rail-train (1)" — rail/train system bid

When a user asks about requirements without specifying a document, use "EF_EFI System" or "CH_Charging System" as the document_id.
Always provide specific, actionable responses with data from the action groups."""

print(f"Updating agent {AGENT_ID} instruction...")
agent = client.get_agent(agentId=AGENT_ID)["agent"]
client.update_agent(
    agentId              = AGENT_ID,
    agentName            = agent["agentName"],
    foundationModel      = agent["foundationModel"],
    agentResourceRoleArn = agent["agentResourceRoleArn"],
    instruction          = INSTRUCTION,
    idleSessionTTLInSeconds = agent.get("idleSessionTTLInSeconds", 1800),
)
print("Instruction updated.")

# ── Step 2: Delete existing action groups ─────────────────────────────────────
existing = client.list_agent_action_groups(
    agentId=AGENT_ID, agentVersion="DRAFT"
)["actionGroupSummaries"]
for ag in existing:
    if ag["actionGroupName"] != "UserInput":
        client.delete_agent_action_group(
            agentId=AGENT_ID, agentVersion="DRAFT",
            actionGroupId=ag["actionGroupId"]
        )
        print(f"Deleted action group: {ag['actionGroupName']}")
        time.sleep(1)

# ── Step 3: Re-attach all 4 action groups ────────────────────────────────────
def make_schema(title, path, op_id, required, props):
    return {"payload": json.dumps({
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {path: {"post": {
            "operationId": op_id,
            "summary": title,
            "description": title,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "required": required, "properties": props,
            }}}},
            "responses": {"200": {"description": "Success",
                "content": {"application/json": {"schema": {"type": "object"}}}}},
        }}},
    })}

ACTION_GROUPS = [
    {
        "name":        "DocumentProcessor",
        "description": "Process bid PDF documents — extract text, embeddings, and knowledge graph entities. Call this when asked to process or ingest a document.",
        "lambda_arn":  DOC_FN,
        "path":        "/process-document",
        "op_id":       "process_document",
        "required":    ["document_path"],
        "props": {
            "document_path": {"type": "string", "description": "S3 key of the document e.g. bids/myfile.pdf"},
            "document_type": {"type": "string", "enum": ["pdf","txt","docx"], "description": "Document type"},
        },
    },
    {
        "name":        "RequirementsExtractor",
        "description": "Extract structured requirements from a processed document in the database. Call this when asked about requirements, to list requirements, or to extract requirements from a document.",
        "lambda_arn":  REQ_FN,
        "path":        "/extract-requirements",
        "op_id":       "extract_requirements",
        "required":    ["document_id"],
        "props": {
            "document_id": {"type": "string", "description": "Document identifier e.g. 'CH_Charging System' or 'EF_EFI System'"},
            "extraction_criteria": {"type": "object", "description": "Optional extraction filters"},
        },
    },
    {
        "name":        "ExpertMatcher",
        "description": "Assign domain experts to requirements using semantic similarity. Call this when asked to assign experts or find who should review a requirement.",
        "lambda_arn":  EXP_FN,
        "path":        "/assign-experts",
        "op_id":       "assign_experts",
        "required":    ["requirements"],
        "props": {
            "requirements": {"type": "array", "items": {"type": "object"},
                             "description": "List of requirement objects with requirement_id, description, domain"},
            "assignment_criteria": {"type": "object", "description": "Optional assignment filters"},
        },
    },
    {
        "name":        "ComplianceChecker",
        "description": "Generate compliance suggestions for a requirement using past data and regulations. Call this when asked about compliance, standards, or regulatory requirements.",
        "lambda_arn":  COMP_FN,
        "path":        "/check-compliance",
        "op_id":       "check_compliance",
        "required":    ["requirement_id", "requirement_text"],
        "props": {
            "requirement_id":   {"type": "string", "description": "Requirement ID e.g. REQ-001"},
            "requirement_text": {"type": "string", "description": "Full requirement description text"},
            "domain":           {"type": "string", "description": "Domain e.g. security, performance, compliance"},
        },
    },
]

for ag in ACTION_GROUPS:
    client.create_agent_action_group(
        agentId            = AGENT_ID,
        agentVersion       = "DRAFT",
        actionGroupName    = ag["name"],
        description        = ag["description"],
        actionGroupState   = "ENABLED",
        actionGroupExecutor= {"lambda": ag["lambda_arn"]},
        apiSchema          = make_schema(ag["name"], ag["path"], ag["op_id"],
                                         ag["required"], ag["props"]),
    )
    print(f"  Created: {ag['name']}")
    time.sleep(1)

# ── Step 4: Prepare agent ─────────────────────────────────────────────────────
print("\nPreparing agent...")
client.prepare_agent(agentId=AGENT_ID)
for _ in range(24):
    status = client.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    print(f"  Status: {status}")
    if status == "PREPARED": break
    if status == "FAILED":   raise RuntimeError("Agent preparation failed")
    time.sleep(5)

# ── Step 5: Update alias to new version ──────────────────────────────────────
print("\nRecreating alias...")
try:
    client.delete_agent_alias(agentId=AGENT_ID, agentAliasId=ALIAS_ID)
    time.sleep(3)
except Exception as e:
    print(f"  Could not delete old alias: {e}")

new_alias = client.create_agent_alias(agentId=AGENT_ID, agentAliasName="production")
new_alias_id = new_alias["agentAlias"]["agentAliasId"]
for _ in range(12):
    s = client.get_agent_alias(agentId=AGENT_ID, agentAliasId=new_alias_id)["agentAlias"]["agentAliasStatus"]
    print(f"  Alias status: {s}")
    if s == "PREPARED": break
    time.sleep(5)

# ── Step 6: Test ──────────────────────────────────────────────────────────────
print("\nTesting agent...")
rt   = boto3.client("bedrock-agent-runtime", region_name=REGION)
resp = rt.invoke_agent(agentId=AGENT_ID, agentAliasId=new_alias_id,
                       sessionId="fix-test-final",
                       inputText="Show me the requirements from the EF_EFI System document")
out  = ""
for event in resp["completion"]:
    if "chunk" in event:
        out += event["chunk"]["bytes"].decode()
print(f"Response: {out[:400]}")

# ── Save ──────────────────────────────────────────────────────────────────────
with open(os.path.join(ROOT, "agent_alias_id.txt"), "w") as f:
    f.write(new_alias_id)
print(f"\nSaved alias: {new_alias_id}")
print(f"Agent ID:    {AGENT_ID}")
