"""Expert Matcher Lambda — assigns domain experts to requirements."""
import json
import os
import boto3
import numpy as np
from typing import Any

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


def _bedrock_response(event, body):
    if "actionGroup" not in event:
        return body
    return {
        "messageVersion":"1.0",
        "response":{
            "actionGroup": event.get("actionGroup",""),
            "apiPath":     event.get("apiPath",""),
            "httpMethod":  event.get("httpMethod","POST"),
            "httpStatusCode": 200,
            "responseBody":{"application/json":{"body":json.dumps(body)}},
        },
    }


def _embed(text: str) -> list:
    resp = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text[:8000]}),
    )
    return json.loads(resp["body"].read())["embedding"]


def _cosine(a, b) -> float:
    va, vb = np.array(a), np.array(b)
    d = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / d) if d else 0.0


def _load_experts() -> list:
    if not DB_ARN:
        return []
    try:
        resp = rds.execute_statement(
            resourceArn=DB_ARN, secretArn=DB_SECRET,
            database="requirements_db",
            sql="SELECT expert_id,name,email,department,skills,specializations,current_workload,skill_embeddings FROM domain_experts WHERE availability_status='available' ORDER BY current_workload ASC",
        )
        experts = []
        for r in resp.get("records",[]):
            try:
                emb_str = r[7].get("stringValue","[]")
                emb     = json.loads(emb_str) if emb_str else []
                experts.append({
                    "expert_id":       r[0]["stringValue"],
                    "name":            r[1]["stringValue"],
                    "email":           r[2]["stringValue"],
                    "department":      r[3]["stringValue"],
                    "skills":          json.loads(r[4]["stringValue"]),
                    "specializations": json.loads(r[5]["stringValue"]),
                    "current_workload":r[6]["longValue"],
                    "skill_embeddings":emb,
                })
            except Exception as e:
                print(f"Expert parse error: {e}")
        return experts
    except Exception as e:
        print(f"Load experts error: {e}")
        return []


def handler(event: dict, context: Any) -> dict:
    print(f"Event: {json.dumps(event)[:500]}")
    params = _parse_event(event)
    reqs   = params.get("requirements", [])
    if isinstance(reqs, str):
        try: reqs = json.loads(reqs)
        except: reqs = []

    if not reqs:
        return _bedrock_response(event, {"status":"error","message":"requirements required"})

    experts     = _load_experts()
    assignments = []

    for req in reqs:
        desc    = f"{req.get('description','')} {req.get('domain','')} {req.get('category','')}"
        req_emb = _embed(desc)
        matches = []

        for expert in experts:
            if not expert["skill_embeddings"]:
                continue
            sim    = _cosine(req_emb, expert["skill_embeddings"])
            domain = req.get("domain","").lower()
            specs  = [s.lower() for s in expert["specializations"]]
            d_score = 1.0 if domain in specs else 0.6 if any(domain in s for s in specs) else 0.0
            wl      = max(0.0, 1.0 - expert["current_workload"] / 10.0)
            score   = sim * 0.6 + d_score * 0.3 + wl * 0.1

            if score >= 0.3:
                matches.append({
                    "expert_id":       expert["expert_id"],
                    "name":            expert["name"],
                    "department":      expert["department"],
                    "similarity_score":round(sim, 4),
                    "domain_score":    round(d_score, 4),
                    "combined_score":  round(score, 4),
                })

        matches.sort(key=lambda x: x["combined_score"], reverse=True)
        assignments.append({
            "requirement_id":      req.get("requirement_id", req.get("id","")),
            "assigned_experts":    matches[:2],
            "assignment_confidence": round(matches[0]["combined_score"],4) if matches else 0.0,
        })

    return _bedrock_response(event, {
        "status":      "success",
        "assignments": assignments,
        "total":       len(assignments),
    })
