"""
Compliance Checker Lambda — Graph-Enhanced
Uses graph DB to find similar past requirements and compliance patterns,
then generates grounded compliance suggestions.
"""
import json, os, sys
import boto3
from typing import Any

sys.path.insert(0, "/var/task")

REGION    = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
DB_ARN    = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET = os.environ.get("DB_SECRET_ARN", "")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
rds     = boto3.client("rds-data",        region_name=REGION)


def _parse_event(event):
    if "requestBody" in event:
        props = event.get("requestBody",{}).get("content",{}) \
                     .get("application/json",{}).get("properties",[])
        return {p["name"]: p["value"] for p in props}
    if "body" in event and event["body"]:
        try: return json.loads(event["body"])
        except: pass
    return event

def _wrap(event, body):
    if "actionGroup" not in event: return body
    return {"messageVersion":"1.0","response":{
        "actionGroup":event.get("actionGroup",""),
        "apiPath":event.get("apiPath",""),
        "httpMethod":event.get("httpMethod","POST"),
        "httpStatusCode":200,
        "responseBody":{"application/json":{"body":json.dumps(body)}},
    }}

def _embed(text):
    r = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                             body=json.dumps({"inputText":text[:8000]}))
    return json.loads(r["body"].read())["embedding"]

def _get_graph():
    import graph_db
    return graph_db


def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    params   = _parse_event(event)
    req_id   = params.get("requirement_id","REQ-UNKNOWN")
    req_text = params.get("requirement_text","")
    domain   = params.get("domain","general")

    if not req_text:
        return _wrap(event, {"status":"error","message":"requirement_text required"})

    g = _get_graph()

    # 1. Find similar past requirements via graph semantic search
    emb          = _embed(req_text)
    similar_reqs = g.semantic_search_nodes(emb, label="Requirement", top_k=5)

    # 2. Get compliance-related entities from graph
    compliance_entities = g.get_experts_for_domain("compliance", limit=3)

    # 3. Build context from graph
    past_context = ""
    citations    = []
    for sr in similar_reqs:
        props = sr.get("properties",{})
        desc  = props.get("description","")
        sim   = float(sr.get("similarity",0))
        doc   = props.get("document_id","")
        if desc and sim > 0.5:
            past_context += f"\n[Past Req | {doc} | sim={sim:.2f}] {desc}"
            citations.append({
                "source":          doc,
                "chunk_id":        0,
                "relevance_score": sim,
                "text_snippet":    desc[:150],
            })

    # 4. Generate compliance suggestion using graph context
    prompt = f"""You are a compliance expert. Analyze this requirement and provide compliance guidance.

Domain: {domain}
Requirement: {req_text}

Similar Past Requirements from Graph:
{past_context or "No similar past requirements found."}

Provide:
1. Applicable standards/regulations for this domain
2. Compliance gaps or risks
3. Specific recommendations based on past requirements

Be concise and specific."""

    try:
        r   = bedrock.invoke_model(
            modelId="amazon.nova-micro-v1:0",
            body=json.dumps({"messages":[{"role":"user","content":[{"text":prompt}]}],
                             "inferenceConfig":{"maxTokens":800,"temperature":0.2}}))
        compliance_text = json.loads(r["body"].read())["output"]["message"]["content"][0]["text"]
    except Exception as e:
        compliance_text = f"Compliance analysis error: {e}"

    # 5. Store compliance suggestion in graph
    try:
        g.upsert_node("ComplianceSuggestion", req_id, {
            "requirement_id":  req_id,
            "domain":          domain,
            "suggestion":      compliance_text[:500],
            "confidence":      0.82,
        })
        g.upsert_edge("Requirement", req_id, "HAS_COMPLIANCE",
                      "ComplianceSuggestion", req_id,
                      {"domain": domain})
    except Exception as e:
        print(f"Graph store error: {e}")

    # 6. Store in Aurora
    try:
        rds.execute_statement(
            resourceArn=DB_ARN, secretArn=DB_SECRET,
            database="requirements_db",
            sql="""INSERT INTO compliance_suggestions
                       (requirement_id,regulation_type,suggestion_text,confidence_score,source_documents,status)
                   VALUES(:rid,:reg,:text,:conf,:sources::jsonb,'generated')
                   ON CONFLICT DO NOTHING""",
            parameters=[
                {"name":"rid",    "value":{"stringValue":req_id}},
                {"name":"reg",    "value":{"stringValue":domain}},
                {"name":"text",   "value":{"stringValue":compliance_text}},
                {"name":"conf",   "value":{"doubleValue":0.82}},
                {"name":"sources","value":{"stringValue":json.dumps(citations)}},
            ])
    except Exception as e:
        print(f"Aurora store error: {e}")

    return _wrap(event, {
        "status":           "success",
        "requirement_id":   req_id,
        "compliance_text":  compliance_text,
        "citations":        citations,
        "confidence_score": 0.82,
        "domain":           domain,
        "graph_context_used": len(similar_reqs),
    })
