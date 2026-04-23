"""
Expert Matcher Lambda — Graph-Enhanced
Uses graph DB to find experts via SPECIALIZES_IN edges and semantic similarity,
then creates ASSIGNED_TO edges in the graph.
"""
import json, os, sys
import boto3
import numpy as np
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

def _cosine(a, b):
    va, vb = np.array(a), np.array(b)
    d = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va,vb)/d) if d else 0.0

def _get_graph():
    import graph_db
    return graph_db


def _match_experts_graph(req, g):
    """
    Multi-strategy expert matching using graph DB:
    1. Domain traversal: Expert -[SPECIALIZES_IN]-> Domain
    2. Semantic similarity: embed requirement, search Expert nodes
    3. Past assignment: Expert -[ASSIGNED_TO]-> similar Requirement
    """
    domain    = req.get("domain","general")
    desc      = req.get("description","")
    req_id    = req.get("requirement_id","")
    req_emb   = _embed(f"{desc} {domain}")

    # Strategy 1: Domain graph traversal
    domain_experts = g.get_experts_for_domain(domain, limit=10)

    # Strategy 2: Semantic similarity on Expert nodes
    semantic_experts = g.semantic_search_nodes(req_emb, label="Expert", top_k=10)

    # Strategy 3: Find experts who handled similar past requirements
    similar_reqs = g.semantic_search_nodes(req_emb, label="Requirement", top_k=5)
    past_experts = []
    for sr in similar_reqs:
        sr_key = sr.get("properties",{}).get("_key","")
        if sr_key and sr_key != req_id:
            assigned = g.traverse_in("Requirement", sr_key, rel="ASSIGNED_TO", limit=3)
            past_experts.extend(assigned)

    # Merge all candidates
    expert_scores = {}
    for e in domain_experts:
        eid = e.get("properties",{}).get("_key","")
        if eid:
            expert_scores[eid] = expert_scores.get(eid, {"expert":e,"score":0.0})
            expert_scores[eid]["score"] += 0.4  # domain match bonus

    for e in semantic_experts:
        eid = e.get("properties",{}).get("_key","")
        sim = float(e.get("similarity",0))
        if eid:
            expert_scores.setdefault(eid, {"expert":e,"score":0.0})
            expert_scores[eid]["score"] += sim * 0.5

    for e in past_experts:
        eid = e.get("properties",{}).get("_key","")
        if eid:
            expert_scores.setdefault(eid, {"expert":e,"score":0.0})
            expert_scores[eid]["score"] += 0.3  # past assignment bonus

    # Sort and return top matches
    ranked = sorted(expert_scores.values(), key=lambda x: x["score"], reverse=True)
    matches = []
    for item in ranked[:3]:
        e     = item["expert"]
        props = e.get("properties",{})
        matches.append({
            "expert_id":      props.get("_key",""),
            "name":           props.get("name",""),
            "department":     props.get("department",""),
            "specializations":props.get("specializations",[]),
            "combined_score": round(min(item["score"],1.0),4),
            "match_reason":   f"Domain:{domain}, Semantic+Graph traversal",
        })

    return matches


def handler(event, context: Any):
    print(f"Event: {json.dumps(event)[:500]}")
    params = _parse_event(event)
    reqs   = params.get("requirements",[])
    if isinstance(reqs, str):
        try: reqs = json.loads(reqs)
        except: reqs = []

    if not reqs:
        return _wrap(event, {"status":"error","message":"requirements required"})

    g           = _get_graph()
    assignments = []

    for req in reqs:
        matches = _match_experts_graph(req, g)

        # Create ASSIGNED_TO edges in graph for top match
        for m in matches[:1]:
            if m["expert_id"] and req.get("requirement_id"):
                g.assign_expert(
                    req["requirement_id"], m["expert_id"],
                    m["combined_score"],
                    m["match_reason"])

        assignments.append({
            "requirement_id":      req.get("requirement_id",""),
            "assigned_experts":    matches,
            "assignment_confidence": matches[0]["combined_score"] if matches else 0.0,
        })

    return _wrap(event, {
        "status":      "success",
        "assignments": assignments,
        "total":       len(assignments),
    })
