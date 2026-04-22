import boto3, json, os, time

ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION   = "us-east-1"
AGENT_ID = open(os.path.join(ROOT, "agent_id.txt")).read().strip()
ALIAS_ID = open(os.path.join(ROOT, "agent_alias_id.txt")).read().strip()

c  = boto3.client("bedrock-agent",         region_name=REGION)
rt = boto3.client("bedrock-agent-runtime", region_name=REGION)

INSTRUCTION = """You are a Requirements Management Search Engine with full access to all uploaded bid documents.

AVAILABLE DOCUMENTS (search all of them):
- CH_Charging System.pdf     -> charging, alternator, battery, voltage
- EF_EFI System.pdf          -> fuel injection, EFI, injector, ECU
- EC_Emission Control Systems.pdf -> emission, exhaust, catalytic
- rail-train (1).pdf         -> rail, train, railway
- sample_requirements.pdf    -> sample requirements
- test_requirements_new.pdf  -> test requirements

STRICT RULES - never break these:
1. ALWAYS call DocumentSearch first before answering ANY question about documents.
2. Use action="search" with the user's question as query for content questions.
3. Use action="list_documents" when asked what documents exist.
4. Use action="list_requirements" when asked to list requirements.
5. Set document_filter to the document name when user asks about a specific document.
6. NEVER say you cannot access documents - you have DocumentSearch tool.
7. NEVER answer from memory - always search first.
8. Search ALL documents by default (empty document_filter) unless user specifies one.

DOCUMENT ROUTING (set document_filter):
- "charging system" or "alternator" -> document_filter: CH_Charging System
- "EFI" or "fuel injection" or "injector" -> document_filter: EF_EFI System
- "emission" or "exhaust" -> document_filter: EC_Emission Control Systems
- specific document name mentioned -> use that name as document_filter
- general question -> leave document_filter empty (searches all documents)

Always cite which document each answer comes from with the similarity score."""

# Update instruction
ag = c.get_agent(agentId=AGENT_ID)["agent"]
c.update_agent(
    agentId              = AGENT_ID,
    agentName            = ag["agentName"],
    foundationModel      = ag["foundationModel"],
    agentResourceRoleArn = ag["agentResourceRoleArn"],
    instruction          = INSTRUCTION,
    idleSessionTTLInSeconds = 1800,
)
print("Instruction updated")

# Prepare
c.prepare_agent(agentId=AGENT_ID)
for _ in range(24):
    status = c.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    print(f"  Status: {status}")
    if status == "PREPARED": break
    if status == "FAILED":   raise RuntimeError("Failed")
    time.sleep(5)

# Delete old alias and create new one
try:
    c.delete_agent_alias(agentId=AGENT_ID, agentAliasId=ALIAS_ID)
    time.sleep(3)
except Exception as e:
    print(f"  Delete alias: {e}")

new_alias = c.create_agent_alias(agentId=AGENT_ID, agentAliasName="production")
new_id    = new_alias["agentAlias"]["agentAliasId"]
for _ in range(12):
    s = c.get_agent_alias(agentId=AGENT_ID, agentAliasId=new_id)["agentAlias"]["agentAliasStatus"]
    print(f"  Alias: {s}")
    if s == "PREPARED": break
    time.sleep(5)

# Test
print("\nTesting...")
for q_text in [
    "What documents are available?",
    "What are the voltage requirements in the charging system?",
    "What fuel injection requirements exist?",
]:
    resp = rt.invoke_agent(agentId=AGENT_ID, agentAliasId=new_id,
                           sessionId=f"test-{hash(q_text)%9999}", inputText=q_text)
    out = "".join(e["chunk"]["bytes"].decode() for e in resp["completion"] if "chunk" in e)
    print(f"\nQ: {q_text}")
    print(f"A: {out[:250]}")

with open(os.path.join(ROOT, "agent_alias_id.txt"), "w") as f:
    f.write(new_id)
print(f"\nNew alias: {new_id}")
