import boto3
import json
import time
import os

REGION   = "us-east-1"
ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AGENT_ID = open(os.path.join(ROOT, "agent_id.txt")).read().strip()

rt      = boto3.client("bedrock-runtime",      region_name=REGION)
agent_c = boto3.client("bedrock-agent",        region_name=REGION)
agent_r = boto3.client("bedrock-agent-runtime", region_name=REGION)

# ── Step 1: Find a working model ──────────────────────────────────────────────
CANDIDATES = [
    ("amazon.nova-micro-v1:0",   {"messages":[{"role":"user","content":[{"text":"hi"}]}],"inferenceConfig":{"maxTokens":5}}),
    ("amazon.nova-lite-v1:0",    {"messages":[{"role":"user","content":[{"text":"hi"}]}],"inferenceConfig":{"maxTokens":5}}),
    ("amazon.nova-pro-v1:0",     {"messages":[{"role":"user","content":[{"text":"hi"}]}],"inferenceConfig":{"maxTokens":5}}),
    ("us.amazon.nova-micro-v1:0",{"messages":[{"role":"user","content":[{"text":"hi"}]}],"inferenceConfig":{"maxTokens":5}}),
    ("us.amazon.nova-lite-v1:0", {"messages":[{"role":"user","content":[{"text":"hi"}]}],"inferenceConfig":{"maxTokens":5}}),
    ("anthropic.claude-3-haiku-20240307-v1:0",
     {"anthropic_version":"bedrock-2023-05-31","max_tokens":5,"messages":[{"role":"user","content":"hi"}]}),
    ("us.anthropic.claude-3-haiku-20240307-v1:0",
     {"anthropic_version":"bedrock-2023-05-31","max_tokens":5,"messages":[{"role":"user","content":"hi"}]}),
    ("us.anthropic.claude-3-5-haiku-20241022-v1:0",
     {"anthropic_version":"bedrock-2023-05-31","max_tokens":5,"messages":[{"role":"user","content":"hi"}]}),
]

working_model = None
for model_id, body in CANDIDATES:
    try:
        r = rt.invoke_model(modelId=model_id, body=json.dumps(body))
        d = json.loads(r["body"].read())
        print(f"  WORKS: {model_id}")
        working_model = model_id
        break
    except Exception as e:
        print(f"  FAIL:  {model_id} -> {str(e)[:80]}")

if not working_model:
    print("\nNo working model found. Check Bedrock model access in the console.")
    exit(1)

print(f"\nUsing model: {working_model}")

# ── Step 2: Update agent with working model ───────────────────────────────────
agent = agent_c.get_agent(agentId=AGENT_ID)["agent"]
agent_c.update_agent(
    agentId              = AGENT_ID,
    agentName            = agent["agentName"],
    foundationModel      = working_model,
    agentResourceRoleArn = agent["agentResourceRoleArn"],
    instruction          = agent.get("instruction", "You are a helpful requirements management assistant."),
    idleSessionTTLInSeconds = agent.get("idleSessionTTLInSeconds", 1800),
)
print(f"Agent updated to: {working_model}")

# ── Step 3: Prepare ───────────────────────────────────────────────────────────
agent_c.prepare_agent(agentId=AGENT_ID)
for _ in range(30):
    status = agent_c.get_agent(agentId=AGENT_ID)["agent"]["agentStatus"]
    print(f"  Agent status: {status}")
    if status == "PREPARED":
        break
    if status == "FAILED":
        print("FAILED"); exit(1)
    time.sleep(5)

# ── Step 4: Delete all existing aliases and create fresh one ──────────────────
aliases = agent_c.list_agent_aliases(agentId=AGENT_ID)["agentAliasSummaries"]
for a in aliases:
    if a["agentAliasId"] != "TSTALIASID":
        try:
            agent_c.delete_agent_alias(agentId=AGENT_ID, agentAliasId=a["agentAliasId"])
            print(f"  Deleted alias: {a['agentAliasId']}")
            time.sleep(2)
        except Exception as e:
            print(f"  Could not delete {a['agentAliasId']}: {e}")

new_alias = agent_c.create_agent_alias(agentId=AGENT_ID, agentAliasName="production")
alias_id  = new_alias["agentAlias"]["agentAliasId"]
print(f"  Created alias: {alias_id}")

for _ in range(12):
    s = agent_c.get_agent_alias(agentId=AGENT_ID, agentAliasId=alias_id)["agentAlias"]["agentAliasStatus"]
    print(f"  Alias status: {s}")
    if s == "PREPARED":
        break
    time.sleep(5)

# ── Step 5: Test invoke ───────────────────────────────────────────────────────
print("\nTesting invoke...")
time.sleep(3)
try:
    resp = agent_r.invoke_agent(
        agentId=AGENT_ID, agentAliasId=alias_id,
        sessionId="fix-test-final", inputText="Hello, what can you help me with?",
    )
    out = ""
    for event in resp["completion"]:
        if "chunk" in event:
            out += event["chunk"]["bytes"].decode()
    print(f"SUCCESS: {out[:300]}")
except Exception as e:
    print(f"Invoke failed: {e}")

# ── Step 6: Save ──────────────────────────────────────────────────────────────
with open(os.path.join(ROOT, "agent_alias_id.txt"), "w") as f:
    f.write(alias_id)

print(f"\nSaved to agent_alias_id.txt")
print(f"AGENT_ID = {AGENT_ID}")
print(f"ALIAS_ID = {alias_id}")
print(f"MODEL    = {working_model}")
