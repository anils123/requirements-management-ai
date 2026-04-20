"""Document action group - delegates to DocumentProcessor Lambda."""
import boto3, json, os
from typing import Dict, Any


def ingest_document(document_path: str, document_type: str = "pdf") -> Dict[str, Any]:
    client = boto3.client("lambda")
    resp   = client.invoke(
        FunctionName=os.environ.get("DOCUMENT_PROCESSOR_LAMBDA_ARN", "DocumentProcessor"),
        Payload=json.dumps({
            "actionGroup": "DocumentProcessor",
            "apiPath":     "/process-document",
            "httpMethod":  "POST",
            "requestBody": {"content": {"application/json": {"properties": [
                {"name": "document_path", "value": document_path},
                {"name": "document_type", "value": document_type},
            ]}}},
        }),
    )
    return json.loads(resp["Payload"].read())
