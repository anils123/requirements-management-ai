"""Smoke tests to validate the deployment is working end-to-end."""
import json
import os
import sys
import boto3

PYTHON_PATH = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, PYTHON_PATH)

lambda_client  = boto3.client("lambda",        region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock_agent  = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
results = []


def test(name: str, fn):
    try:
        fn()
        print(f"{PASS} {name}")
        results.append((name, True))
    except Exception as e:
        print(f"{FAIL} {name}: {e}")
        results.append((name, False))


def invoke_lambda(fn_name: str, payload: dict) -> dict:
    resp = lambda_client.invoke(
        FunctionName=fn_name,
        Payload=json.dumps(payload),
    )
    body = json.loads(resp["Payload"].read())
    if resp.get("FunctionError"):
        raise RuntimeError(f"Lambda error: {body}")
    return body


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_document_processor():
    body = invoke_lambda("DocumentProcessor", {
        "actionGroup": "DocumentProcessor",
        "apiPath":     "/process-document",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "document_path", "value": "test/sample.pdf"},
        ]}}},
    })
    assert body is not None


def test_requirements_extractor():
    body = invoke_lambda("RequirementsExtractor", {
        "actionGroup": "RequirementsExtractor",
        "apiPath":     "/extract-requirements",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "document_id", "value": "test-doc-001"},
        ]}}},
    })
    assert body is not None


def test_expert_matcher():
    body = invoke_lambda("ExpertMatcher", {
        "actionGroup": "ExpertMatcher",
        "apiPath":     "/assign-experts",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "requirements", "value": json.dumps([{
                "requirement_id": "REQ-TEST-001",
                "description":    "The system shall implement OAuth2 authentication",
                "domain":         "security",
                "category":       "security",
            }])},
        ]}}},
    })
    assert body is not None


def test_compliance_checker():
    body = invoke_lambda("ComplianceChecker", {
        "actionGroup": "ComplianceChecker",
        "apiPath":     "/check-compliance",
        "httpMethod":  "POST",
        "requestBody": {"content": {"application/json": {"properties": [
            {"name": "requirement_id",   "value": "REQ-TEST-001"},
            {"name": "requirement_text", "value": "The system shall implement OAuth2 authentication"},
            {"name": "domain",           "value": "security"},
        ]}}},
    })
    assert body is not None


def test_bedrock_agent():
    agent_id    = os.environ.get("AGENT_ID", "")
    agent_alias = os.environ.get("AGENT_ALIAS_ID", "")
    if not agent_id or not agent_alias:
        raise RuntimeError("AGENT_ID or AGENT_ALIAS_ID not set — skipping agent test")
    resp = bedrock_agent.invoke_agent(
        agentId=agent_id,
        agentAliasId=agent_alias,
        sessionId="smoke-test-session",
        inputText="List the main capabilities of the requirements management system.",
    )
    output = ""
    for event in resp["completion"]:
        if "chunk" in event:
            output += event["chunk"]["bytes"].decode()
    assert len(output) > 10


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Requirements Management Deployment Tests ===\n")
    test("DocumentProcessor Lambda",    test_document_processor)
    test("RequirementsExtractor Lambda", test_requirements_extractor)
    test("ExpertMatcher Lambda",        test_expert_matcher)
    test("ComplianceChecker Lambda",    test_compliance_checker)
    test("Bedrock Agent invocation",    test_bedrock_agent)

    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"\n{'='*48}")
    print(f"Results: {passed}/{total} tests passed")
    if passed < total:
        sys.exit(1)
