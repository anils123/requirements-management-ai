"""Expert action group - delegates to ExpertMatcher Lambda."""
import boto3, json, os
from typing import Dict, List, Any


def find_experts(requirements: List[Dict], criteria: Dict = None) -> Dict[str, Any]:
    client = boto3.client("lambda")
    resp   = client.invoke(
        FunctionName=os.environ.get("EXPERT_MATCHER_LAMBDA_ARN", "ExpertMatcher"),
        Payload=json.dumps({
            "actionGroup": "ExpertMatcher",
            "apiPath":     "/assign-experts",
            "httpMethod":  "POST",
            "requestBody": {"content": {"application/json": {"properties": [
                {"name": "requirements",         "value": json.dumps(requirements)},
                {"name": "assignment_criteria",  "value": json.dumps(criteria or {})},
            ]}}},
        }),
    )
    return json.loads(resp["Payload"].read())
