"""
Create and configure the Requirements Management Bedrock Agent.
Looks up the IAM role CDK already created instead of using placeholders.
"""
import os
import sys
import json
import boto3

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

REGION  = os.environ.get("AWS_REGION", "us-east-1")
ACCOUNT = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]


def _get_agent_role_arn() -> str:

    """Find or create the Bedrock Agent execution role."""
    iam = boto3.client("iam", region_name=REGION)

    # Search priority: CDK-created role first, then existing Bedrock service roles
    search_prefixes = [
        "BedrockAgentRole",
        "AmazonBedrockServiceRole",
        "RequirementsManagementSta",
    ]

    paginator = iam.get_paginator("list_roles")
    all_roles = []
    for page in paginator.paginate():
        all_roles.extend(page["Roles"])

    for prefix in search_prefixes:
        for role in all_roles:
            if role["RoleName"].startswith(prefix):
                print(f"  Found agent role: {role['RoleName']}")
                return role["Arn"]

    # No suitable role found — create a minimal one
    print("  No existing Bedrock role found — creating BedrockAgentExecutionRole...")
    trust_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": ACCOUNT},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:agent/*"}
            }
        }]
    })
    role = iam.create_role(
        RoleName="BedrockAgentExecutionRole",
        AssumeRolePolicyDocument=trust_policy,
        Description="Execution role for Requirements Management Bedrock Agent",
    )
    iam.attach_role_policy(
        RoleName="BedrockAgentExecutionRole",
        PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
    )
    iam.attach_role_policy(
        RoleName="BedrockAgentExecutionRole",
        PolicyArn="arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
    )
    print(f"  Created role: BedrockAgentExecutionRole")
    return role["Role"]["Arn"]


def _ensure_passrole_permission(role_arn: str) -> None:
    """
    Add iam:PassRole inline policy to the current IAM user so
    CreateAgent can pass the execution role to Bedrock.
    AmazonBedrockFullAccess does NOT include iam:PassRole.
    """
    iam      = boto3.client("iam", region_name=REGION)
    username = boto3.client("sts", region_name=REGION) \
                   .get_caller_identity()["Arn"].split("/")[-1]
    policy   = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect":   "Allow",
            "Action":   "iam:PassRole",
            "Resource": role_arn,
            "Condition": {
                "StringEquals": {
                    "iam:PassedToService": "bedrock.amazonaws.com"
                }
            }
        }]
    }
    try:
        iam.put_user_policy(
            UserName=username,
            PolicyName="BedrockPassAgentRole",
            PolicyDocument=json.dumps(policy),
        )
        print(f"  iam:PassRole granted to user: {username}")
    except Exception as e:
        print(f"  [WARN] Could not attach PassRole policy: {e}")
        print(f"  Manually add iam:PassRole for {role_arn} to user {username}")


def _delete_existing_agent(client, name: str) -> None:
    """Delete any existing agent with the same name to avoid ConflictException."""
    import time
    try:
        agents = client.list_agents()["agentSummaries"]
        for a in agents:
            if a["agentName"] == name:
                print(f"  Deleting existing agent: {a['agentId']}")
                client.delete_agent(
                    agentId=a["agentId"],
                    skipResourceInUseCheck=True
                )
                # Wait for deletion to complete
                for _ in range(24):
                    try:
                        status = client.get_agent(agentId=a["agentId"])["agent"]["agentStatus"]
                        print(f"  Waiting for deletion... status: {status}")
                        time.sleep(5)
                    except client.exceptions.ResourceNotFoundException:
                        print(f"  Agent deleted: {a['agentId']}")
                        break
    except Exception as e:
        print(f"  [WARN] Could not clean up existing agent: {e}")


def main(lambda_arns: dict = None):
    import time
    client = boto3.client("bedrock-agent", region_name=REGION)

    # Allow caller to pass ARNs directly instead of relying on env vars
    arns = lambda_arns or {
        "document_processor":    os.environ.get("DOCUMENT_PROCESSOR_LAMBDA_ARN", ""),
        "requirements_extractor": os.environ.get("REQUIREMENTS_EXTRACTOR_LAMBDA_ARN", ""),
        "expert_matcher":        os.environ.get("EXPERT_MATCHER_LAMBDA_ARN", ""),
        "compliance_checker":    os.environ.get("COMPLIANCE_CHECKER_LAMBDA_ARN", ""),
    }

    # ── Resolve agent role ────────────────────────────────────────────────────
    print("Looking up Bedrock Agent IAM role...")
    agent_role_arn = _get_agent_role_arn()
    _ensure_passrole_permission(agent_role_arn)

    # ── Delete any existing agent with same name ────────────────────────────
    _delete_existing_agent(client, "RequirementsManagementAgent")

    # ── Build agent config ───────────────────────────────────────────────────
    agent_cfg = {
        "agentName":               "RequirementsManagementAgent",
        "description":             "Agentic AI for automated requirements management from bid PDFs",
        "foundationModel":         "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "agentResourceRoleArn":    agent_role_arn,
        "idleSessionTTLInSeconds": 1800,
        "instruction": (
            "You are an expert Requirements Management AI Assistant. "
            "Capabilities: document processing (200+ page PDFs), requirements extraction, "
            "expert assignment, and compliance analysis with grounded citations. "
            "Always cite sources with relevance scores. Flag low-confidence items for review."
        ),
    }

    # ── Create agent ──────────────────────────────────────────────────────────
    resp     = client.create_agent(**agent_cfg)
    agent_id = resp["agent"]["agentId"]
    print(f"Agent created: {agent_id}")

    # ── Action groups ─────────────────────────────────────────────────────────
    action_groups = [
        {
            "actionGroupName":     "DocumentProcessor",
            "description":         "Process bid PDFs up to 200+ pages",
            "actionGroupExecutor": {"lambda": arns["document_processor"]},
            "actionGroupState":    "ENABLED",
            "apiSchema": {"payload": json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Document Processing API", "version": "1.0.0"},
                "paths": {"/process-document": {"post": {
                    "operationId": "process_document",
                    "summary": "Process a bid PDF document",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["document_path"],
                        "properties": {
                            "document_path": {"type": "string"},
                            "document_type": {"type": "string", "enum": ["pdf","docx"], "default": "pdf"},
                        },
                    }}}},
                    "responses": {"200": {"description": "Processing result"}},
                }}},
            })},
        },
        {
            "actionGroupName":     "RequirementsExtractor",
            "description":         "Extract structured requirements from processed documents",
            "actionGroupExecutor": {"lambda": arns["requirements_extractor"]},
            "actionGroupState":    "ENABLED",
            "apiSchema": {"payload": json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Requirements Extraction API", "version": "1.0.0"},
                "paths": {"/extract-requirements": {"post": {
                    "operationId": "extract_requirements",
                    "summary": "Extract requirements from a processed document",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["document_id"],
                        "properties": {
                            "document_id":         {"type": "string"},
                            "extraction_criteria": {"type": "object"},
                        },
                    }}}},
                    "responses": {"200": {"description": "Extracted requirements"}},
                }}},
            })},
        },
        {
            "actionGroupName":     "ExpertMatcher",
            "description":         "Assign domain experts to requirements",
            "actionGroupExecutor": {"lambda": arns["expert_matcher"]},
            "actionGroupState":    "ENABLED",
            "apiSchema": {"payload": json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Expert Matching API", "version": "1.0.0"},
                "paths": {"/assign-experts": {"post": {
                    "operationId": "assign_experts",
                    "summary": "Assign experts to requirements",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["requirements"],
                        "properties": {
                            "requirements":        {"type": "array", "items": {"type": "object"}},
                            "assignment_criteria": {"type": "object"},
                        },
                    }}}},
                    "responses": {"200": {"description": "Expert assignments"}},
                }}},
            })},
        },
        {
            "actionGroupName":     "ComplianceChecker",
            "description":         "Generate compliance suggestions with grounded citations",
            "actionGroupExecutor": {"lambda": arns["compliance_checker"]},
            "actionGroupState":    "ENABLED",
            "apiSchema": {"payload": json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Compliance Checker API", "version": "1.0.0"},
                "paths": {"/check-compliance": {"post": {
                    "operationId": "check_compliance",
                    "summary": "Generate compliance suggestions for a requirement",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {
                        "type": "object", "required": ["requirement_id", "requirement_text"],
                        "properties": {
                            "requirement_id":   {"type": "string"},
                            "requirement_text": {"type": "string"},
                            "domain":           {"type": "string"},
                        },
                    }}}},
                    "responses": {"200": {"description": "Compliance suggestions with citations"}},
                }}},
            })},
        },
    ]

    for ag in action_groups:
        # Skip action groups with empty Lambda ARNs
        executor_arn = ag.get("actionGroupExecutor", {}).get("lambda", "")
        if not executor_arn or executor_arn.startswith("$"):
            print(f"  [SKIP] {ag['actionGroupName']} — Lambda ARN not set")
            continue
        try:
            client.create_agent_action_group(
                agentId=agent_id, agentVersion="DRAFT", **ag
            )
            print(f"  Action group: {ag['actionGroupName']}")
        except Exception as e:
            print(f"  [WARN] {ag['actionGroupName']}: {e}")

    # ── Wait for agent to leave CREATING state before preparing ─────────────
    import time
    print("  Waiting for agent to reach NOT_PREPARED state...")
    for _ in range(24):  # wait up to 2 minutes
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"  Agent status: {status}")
        if status in ("NOT_PREPARED", "PREPARED", "FAILED"):
            break
        time.sleep(5)

    if status == "FAILED":
        raise RuntimeError(f"Agent entered FAILED state: {agent_id}")

    # ── Prepare agent ─────────────────────────────────────────────────────────
    client.prepare_agent(agentId=agent_id)
    print(f"Agent {agent_id} prepared.")

    # Wait for PREPARED state before creating alias
    print("  Waiting for agent to reach PREPARED state...")
    for _ in range(24):
        status = client.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"  Agent status: {status}")
        if status == "PREPARED":
            break
        if status == "FAILED":
            raise RuntimeError(f"Agent failed during preparation: {agent_id}")
        time.sleep(5)

    # ── Create production alias ───────────────────────────────────────────────
    alias    = client.create_agent_alias(agentId=agent_id, agentAliasName="production")
    alias_id = alias["agentAlias"]["agentAliasId"]
    print(f"Alias: {alias_id}")

    # ── Persist IDs ───────────────────────────────────────────────────────────
    with open(os.path.join(PROJECT_ROOT, "agent_id.txt"), "w") as f:
        f.write(agent_id)
    with open(os.path.join(PROJECT_ROOT, "agent_alias_id.txt"), "w") as f:
        f.write(alias_id)
    print("Written: agent_id.txt  agent_alias_id.txt")

    return agent_id, alias_id


if __name__ == "__main__":
    main()
