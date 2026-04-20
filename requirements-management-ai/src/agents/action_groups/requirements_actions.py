"""Action group entry points for Bedrock Agent - delegate to Lambda handlers."""
from typing import Dict, List, Any


def extract_requirements(document_id: str,
                          extraction_criteria: Dict[str, Any] = None) -> Dict[str, Any]:
    """Invoke requirements extraction for a processed document."""
    import boto3, json
    client = boto3.client("lambda")
    resp   = client.invoke(
        FunctionName=_lambda_arn("RequirementsExtractor"),
        Payload=json.dumps({
            "actionGroup": "RequirementsExtractor",
            "apiPath":     "/extract-requirements",
            "httpMethod":  "POST",
            "requestBody": {"content": {"application/json": {"properties": [
                {"name": "document_id",          "value": document_id},
                {"name": "extraction_criteria",  "value": json.dumps(extraction_criteria or {})},
            ]}}},
        }),
    )
    return json.loads(resp["Payload"].read())


def _lambda_arn(name: str) -> str:
    import os
    return os.environ.get(f"{name.upper()}_LAMBDA_ARN", name)
