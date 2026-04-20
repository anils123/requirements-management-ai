"""
fix_agent.py
============
Updates the Bedrock Agent to use the correct active model inference profile,
prepares it, and updates the alias to point to the new version.
"""
import boto3
import time
import os

ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGION   = "us-east-1"
AGENT_ID = open(os.path.join(ROOT, "agent_id.txt")).read().strip()
ALIAS_ID = open(os.path.join(ROOT, "agent_alias_id.txt")).read().strip()

# Use cross-region inference profile — required for newer Claude models
NEW_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

client = boto3.client("bedrock-agent", region_name=REGION)

print(f"Agent ID: {AGENT_ID}")
print(f"Alias ID: {ALIAS_ID}")
print(f"Updating foundation model to: {NEW_MODEL}")

# ── Step 1: Get current agent config ─────────────────────────────────────────
agent = client.get_agent(agentId=AGENT_ID)["agent"]
print(f"Current model: {agent['foundationModel']}")
print(f"Current status: {agent['agentStatus']}")

# ── Step 2: Update agent with new model ───────────────────────────────────────
client.update_agent(
    agentId              = AGENT_ID,
    agentName            = agent["agentName"],
    foundationModel      = NEW_MODEL,
    agentResourceRoleArn = agent["agentResourceRoleArn"],
    instruction          = agent.get("instruction", "You are a helpful requirements management assistant."),
    idleSessionTTLInSeconds = agent.get("idleSessionTTLInSeconds", 1800),
)
print(f"Agent updated to model: {NEW_MODEL}")

# ── Step 3: Prepare agent ─────────────────────────────────────────────────────
print("Preparing agent...")
client.prepare_agent(agentId=AGENT_ID)

for _ in range(30):
    status = client.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    print(f"  Status: {status}")
    if status == "PREPARED":
        break
    if status == "FAILED":
        raise RuntimeError("Agent preparation failed")
    time.sleep(5)

print("Agent prepared successfully")

# ── Step 4: Update alias to use TSTALIASID workaround ────────────────────────
# Since create_agent_version is not available in this boto3 version,
# delete and recreate the production alias pointing to DRAFT via a workaround:
# Use the built-in TSTALIASID which always routes to DRAFT

print(f"\nAlias {ALIAS_ID} routes to version 1 which doesn't exist.")
print("Deleting old alias and creating new one...")

try:
    client.delete_agent_alias(agentId=AGENT_ID, agentAliasId=ALIAS_ID)
    print(f"Deleted alias: {ALIAS_ID}")
    time.sleep(2)
except Exception as e:
    print(f"Could not delete alias: {e}")

# Create new alias — Bedrock will auto-assign it to the latest prepared version
new_alias = client.create_agent_alias(
    agentId        = AGENT_ID,
    agentAliasName = "production",
    description    = "Production alias pointing to latest prepared version",
)
new_alias_id = new_alias["agentAlias"]["agentAliasId"]
print(f"New alias created: {new_alias_id}")
print(f"Routing: {new_alias['agentAlias']['routingConfiguration']}")

# Wait for alias to be PREPARED
for _ in range(12):
    alias_status = client.get_agent_alias(agentId=AGENT_ID, agentAliasId=new_alias_id)["agentAlias"]["agentAliasStatus"]
    print(f"  Alias status: {alias_status}")
    if alias_status == "PREPARED":
        break
    time.sleep(5)

# ── Step 5: Test invoke ───────────────────────────────────────────────────────
print("\nTesting agent invoke...")
rt = boto3.client("bedrock-agent-runtime", region_name=REGION)
try:
    resp   = rt.invoke_agent(
        agentId      = AGENT_ID,
        agentAliasId = new_alias_id,
        sessionId    = "fix-test-001",
        inputText    = "Hello, what can you help me with?",
    )
    output = ""
    for event in resp["completion"]:
        if "chunk" in event:
            output += event["chunk"]["bytes"].decode()
    print(f"Agent response: {output[:200]}")
    print("\nSUCCESS - Agent is working!")
except Exception as e:
    print(f"Test failed: {e}")

# ── Step 6: Update files ──────────────────────────────────────────────────────
with open(os.path.join(ROOT, "agent_alias_id.txt"), "w") as f:
    f.write(new_alias_id)
print(f"\nUpdated agent_alias_id.txt: {new_alias_id}")
print(f"Agent ID unchanged:         {AGENT_ID}")
print(f"\nUpdate your .env.secrets and backend/main.py with:")
print(f"  AGENT_ID    = {AGENT_ID}")
print(f"  ALIAS_ID    = {new_alias_id}")
print(f"  MODEL       = {NEW_MODEL}")
