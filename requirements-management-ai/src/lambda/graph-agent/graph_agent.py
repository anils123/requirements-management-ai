"""
Graph Agent Lambda — Neo4j Backend
====================================
Central AgentCore tool for all Neo4j graph operations.
Registered as an action group in Bedrock AgentCore.

Env vars required:
  NEO4J_URI      — neo4j+s://xxxxx.databases.neo4j.io  (AuraDB) or bolt://host:7687
  NEO4J_USER     — neo4j
  NEO4J_PASSWORD — <password>
"""
import json, os, sys
import boto3
from typing import Any

sys.path.insert(0, "/var/task")

REGION     = os.environ.get("AWS_ACCOUNT_REGION", "us-east-1")
NEO4J_URI  = os.environ.get("NEO4J_URI",      "")
NEO4J_USER = os.environ.get("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)


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

def _embed(text: str):
    r = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text[:8000]}))
    return json.loads(r["body"].read())["embedding"]

def _get_graph():
    """Import graph_db with Neo4j env vars set."""
    os.environ["NEO4J_URI"]      = NEO4J_URI
    os.environ["NEO4J_USER"]     = NEO4J_USER
    os.environ["NEO4J_PASSWORD"] = NEO4J_PASS
    import graph_db
    return graph_db


# ── Action handlers ───────────────────────────────────────────────────────────

def _semantic_search(p):
    query  = p.get("query","")
    label  = p.get("label","") or None
    top_k  = int(p.get("top_k",8))
    g      = _get_graph()
    emb    = _embed(query)
    results= g.semantic_search_nodes(emb, label=label, top_k=top_k)
    # Deduplicate by id
    seen, deduped = set(), []
    for r in results:
        rid = r.get("properties",{}).get("id","")
        if rid not in seen:
            seen.add(rid); deduped.append(r)
    return {"status":"success","action":"semantic_search",
            "query":query,"label":label,"results":deduped,"total":len(deduped)}


def _traverse(p):
    label  = p.get("label","")
    key    = p.get("key","")
    rel    = p.get("relationship","") or None
    dirn   = p.get("direction","out")
    limit  = int(p.get("limit",20))
    g      = _get_graph()
    if dirn == "out":
        results = g.traverse_out(label, key, rel=rel, limit=limit)
    elif dirn == "in":
        results = g.traverse_in(label, key, rel=rel, limit=limit)
    else:
        results = g.traverse_out(label,key,rel=rel,limit=limit//2) + \
                  g.traverse_in(label, key,rel=rel,limit=limit//2)
    return {"status":"success","action":"traverse","from":{"label":label,"key":key},
            "relationship":rel,"direction":dirn,"results":results,"total":len(results)}


def _neighbourhood(p):
    g   = _get_graph()
    ctx = g.get_neighbourhood(p.get("label",""), p.get("key",""),
                               depth=int(p.get("depth",2)))
    return {"status":"success","action":"neighbourhood",**ctx}


def _find_experts(p):
    domain = p.get("domain","")
    query  = p.get("query","")
    limit  = int(p.get("limit",5))
    g      = _get_graph()
    if domain:
        experts = g.get_experts_for_domain(domain, limit=limit)
    elif query:
        experts = g.semantic_search_nodes(_embed(query), label="Expert", top_k=limit)
    else:
        experts = g.find_nodes("Expert", limit=limit)
    return {"status":"success","action":"find_experts",
            "domain":domain,"experts":experts,"total":len(experts)}


def _past_requirements(p):
    domain = p.get("domain","")
    query  = p.get("query","")
    limit  = int(p.get("limit",10))
    g      = _get_graph()
    if query:
        results = g.semantic_search_nodes(_embed(query), label="Requirement", top_k=limit)
    else:
        results = g.get_past_requirements(domain=domain or None, limit=limit)
    return {"status":"success","action":"past_requirements",
            "domain":domain,"results":results,"total":len(results)}


def _store_requirement(p):
    g   = _get_graph()
    emb = _embed(p.get("description",""))
    nid = g.store_requirement(
        p.get("requirement_id",""), p.get("document_id",""),
        p.get("description",""),    p.get("type","functional"),
        p.get("priority","medium"), p.get("domain","general"),
        float(p.get("confidence_score",0.8)), emb)
    # Link similar past requirements
    similar = g.semantic_search_nodes(emb, label="Requirement", top_k=5)
    linked  = 0
    for s in similar:
        s_id = s.get("properties",{}).get("id","")
        sim  = float(s.get("similarity",0))
        if s_id and s_id != p.get("requirement_id") and sim > 0.7:
            g.link_similar_requirements(p["requirement_id"], s_id, sim)
            linked += 1
    return {"status":"success","action":"store_requirement",
            "node_id":nid,"requirement_id":p.get("requirement_id"),"similar_linked":linked}


def _store_expert(p):
    g      = _get_graph()
    skills = json.loads(p["skills"]) if isinstance(p.get("skills"),str) else p.get("skills",[])
    specs  = json.loads(p["specializations"]) if isinstance(p.get("specializations"),str) else p.get("specializations",[])
    emb    = _embed(" ".join(skills+specs))
    nid    = g.store_expert(p.get("expert_id",""), p.get("name",""),
                             p.get("department",""), skills, specs, emb)
    return {"status":"success","action":"store_expert",
            "node_id":nid,"expert_id":p.get("expert_id"),"domains_linked":len(specs)}


def _assign_expert(p):
    g      = _get_graph()
    edge   = g.assign_expert(p.get("requirement_id",""), p.get("expert_id",""),
                              float(p.get("score",0.8)), p.get("reason",""))
    return {"status":"success","action":"assign_expert","edge":edge,
            "requirement_id":p.get("requirement_id"),"expert_id":p.get("expert_id")}


def _graph_stats(p):
    g = _get_graph()
    return {"status":"success","action":"graph_stats",**g.graph_stats()}


def _list_documents(p):
    g    = _get_graph()
    docs = g.find_nodes("Document", limit=100)
    return {"status":"success","action":"list_documents","documents":docs,"total":len(docs)}


def _cypher_query(p):
    """Execute a raw Cypher query — for advanced graph operations."""
    cypher = p.get("cypher","")
    params = json.loads(p.get("params","{}")) if isinstance(p.get("params"),str) else p.get("params",{})
    if not cypher:
        return {"status":"error","message":"cypher query required"}
    g       = _get_graph()
    results = g.cypher_query(cypher, params)
    return {"status":"success","action":"cypher_query","results":results,"total":len(results)}


def _shortest_path(p):
    g = _get_graph()
    result = g.shortest_path(
        p.get("from_label",""), p.get("from_id",""),
        p.get("to_label",""),   p.get("to_id",""),
        max_depth=int(p.get("max_depth",4)))
    return {"status":"success","action":"shortest_path","path":result}


# ── Router ────────────────────────────────────────────────────────────────────
ACTIONS = {
    "semantic_search":   _semantic_search,
    "traverse":          _traverse,
    "neighbourhood":     _neighbourhood,
    "find_experts":      _find_experts,
    "past_requirements": _past_requirements,
    "store_requirement": _store_requirement,
    "store_expert":      _store_expert,
    "assign_expert":     _assign_expert,
    "graph_stats":       _graph_stats,
    "list_documents":    _list_documents,
    "cypher_query":      _cypher_query,
    "shortest_path":     _shortest_path,
}


def handler(event, context: Any):
    print(f"GraphAgent: {json.dumps(event)[:400]}")
    params = _parse_event(event)
    action = params.get("action","semantic_search")
    print(f"Action={action} NEO4J_URI={NEO4J_URI[:30] if NEO4J_URI else 'NOT SET'}")

    fn = ACTIONS.get(action)
    if not fn:
        return _wrap(event, {"status":"error",
            "message":f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"})
    try:
        return _wrap(event, fn(params))
    except Exception as e:
        print(f"GraphAgent error: {e}")
        return _wrap(event, {"status":"error","message":str(e),"action":action})
