"""
graph_db.py — Neo4j Property Graph Database Layer
===================================================
Uses Neo4j (AuraDB / self-hosted) via Bolt protocol with Cypher queries.

Graph Schema:
  (:Document)-[:CONTAINS]->(:Requirement)
  (:Requirement)-[:EXTRACTED_FROM]->(:Document)
  (:Expert)-[:SPECIALIZES_IN]->(:Domain)
  (:Expert)-[:ASSIGNED_TO {score, reason}]->(:Requirement)
  (:Requirement)-[:SIMILAR_TO {similarity}]->(:Requirement)
  (:Requirement)-[:PART_OF]->(:Project)
  (:Document)-[:MENTIONS]->(:Entity)
  (:Entity)-[:RELATES_TO {predicate}]->(:Entity)

Environment variables:
  NEO4J_URI      — bolt://host:7687 or neo4j+s://xxxxx.databases.neo4j.io
  NEO4J_USER     — neo4j
  NEO4J_PASSWORD — <password>
"""
import os
import json
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, basic_auth

# ── Connection ────────────────────────────────────────────────────────────────
NEO4J_URI  = os.environ.get("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "password")

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=basic_auth(NEO4J_USER, NEO4J_PASS),
            max_connection_lifetime=300,
            connection_timeout=10,
        )
    return _driver


def _run(cypher: str, params: Dict = None) -> List[Dict]:
    """Execute a Cypher query and return list of record dicts."""
    driver = _get_driver()
    with driver.session() as session:
        result = session.run(cypher, params or {})
        return [dict(record) for record in result]


def _run_write(cypher: str, params: Dict = None) -> List[Dict]:
    """Execute a write Cypher query."""
    driver = _get_driver()
    with driver.session() as session:
        result = session.execute_write(
            lambda tx: list(tx.run(cypher, params or {}))
        )
        return [dict(r) for r in result]


def close():
    global _driver
    if _driver:
        _driver.close()
        _driver = None


# ── Schema / Constraints ──────────────────────────────────────────────────────
CONSTRAINTS = [
    "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document)    REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT req_id IF NOT EXISTS FOR (r:Requirement) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT exp_id IF NOT EXISTS FOR (e:Expert)      REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT dom_id IF NOT EXISTS FOR (d:Domain)      REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT prj_id IF NOT EXISTS FOR (p:Project)     REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT ent_id IF NOT EXISTS FOR (e:Entity)      REQUIRE e.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX req_domain  IF NOT EXISTS FOR (r:Requirement) ON (r.domain)",
    "CREATE INDEX req_priority IF NOT EXISTS FOR (r:Requirement) ON (r.priority)",
    "CREATE INDEX req_status  IF NOT EXISTS FOR (r:Requirement) ON (r.status)",
    "CREATE INDEX exp_dept    IF NOT EXISTS FOR (e:Expert)      ON (e.department)",
    "CREATE INDEX doc_name    IF NOT EXISTS FOR (d:Document)    ON (d.name)",
    "CREATE FULLTEXT INDEX req_text IF NOT EXISTS FOR (r:Requirement) ON EACH [r.description]",
]


def init_schema():
    """Create constraints and indexes in Neo4j."""
    for cypher in CONSTRAINTS + INDEXES:
        try:
            _run_write(cypher)
            print(f"  OK: {cypher[:60]}")
        except Exception as e:
            if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                print(f"  ~  {cypher[:60]} (exists)")
            else:
                print(f"  !! {cypher[:60]}: {e}")


# ── Node operations ───────────────────────────────────────────────────────────
def upsert_node(label: str, node_id: str, props: Dict,
                embedding: List[float] = None) -> str:
    """MERGE a node by id, set all properties."""
    all_props = {**props, "id": node_id, "label": label}
    if embedding:
        all_props["embedding"] = embedding

    cypher = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $props
        RETURN n.id AS id
    """
    _run_write(cypher, {"id": node_id, "props": all_props})
    return node_id


def get_node(label: str, node_id: str) -> Optional[Dict]:
    """Get a node by label and id."""
    rows = _run(
        f"MATCH (n:{label} {{id: $id}}) RETURN properties(n) AS props, labels(n) AS labels",
        {"id": node_id}
    )
    if rows:
        return {"id": node_id, "label": label, "properties": rows[0].get("props", {})}
    return None


def find_nodes(label: str, limit: int = 100) -> List[Dict]:
    """Find all nodes of a given label."""
    rows = _run(
        f"MATCH (n:{label}) RETURN properties(n) AS props ORDER BY n.id LIMIT $limit",
        {"limit": limit}
    )
    return [{"label": label, "properties": r.get("props", {})} for r in rows]


# ── Edge operations ───────────────────────────────────────────────────────────
def upsert_edge(from_label: str, from_id: str, rel: str,
                to_label: str, to_id: str,
                props: Dict = None, weight: float = 1.0) -> str:
    """MERGE a relationship between two nodes."""
    edge_props = {**(props or {}), "weight": weight}
    cypher = f"""
        MERGE (a:{from_label} {{id: $from_id}})
        MERGE (b:{to_label}   {{id: $to_id}})
        MERGE (a)-[r:{rel}]->(b)
        SET r += $props
        RETURN type(r) AS rel
    """
    _run_write(cypher, {
        "from_id": from_id,
        "to_id":   to_id,
        "props":   edge_props,
    })
    return f"{from_id}-[{rel}]->{to_id}"


# ── Graph Traversal ───────────────────────────────────────────────────────────
def traverse_out(label: str, node_id: str, rel: str = None,
                 limit: int = 20) -> List[Dict]:
    """Follow outgoing relationships from a node."""
    rel_pattern = f"[r:{rel}]" if rel else "[r]"
    cypher = f"""
        MATCH (n:{label} {{id: $id}})-{rel_pattern}->(m)
        RETURN properties(m) AS props, labels(m) AS labels,
               type(r) AS relationship, r.weight AS weight
        ORDER BY r.weight DESC LIMIT $limit
    """
    rows = _run(cypher, {"id": node_id, "limit": limit})
    return [{
        "label":        r["labels"][0] if r.get("labels") else "",
        "properties":   r.get("props", {}),
        "relationship": r.get("relationship", ""),
        "weight":       r.get("weight", 1.0),
    } for r in rows]


def traverse_in(label: str, node_id: str, rel: str = None,
                limit: int = 20) -> List[Dict]:
    """Follow incoming relationships to a node."""
    rel_pattern = f"[r:{rel}]" if rel else "[r]"
    cypher = f"""
        MATCH (m)-{rel_pattern}->(n:{label} {{id: $id}})
        RETURN properties(m) AS props, labels(m) AS labels,
               type(r) AS relationship, r.weight AS weight
        ORDER BY r.weight DESC LIMIT $limit
    """
    rows = _run(cypher, {"id": node_id, "limit": limit})
    return [{
        "label":        r["labels"][0] if r.get("labels") else "",
        "properties":   r.get("props", {}),
        "relationship": r.get("relationship", ""),
        "weight":       r.get("weight", 1.0),
    } for r in rows]


def shortest_path(from_label: str, from_id: str,
                  to_label: str, to_id: str,
                  max_depth: int = 4) -> List[Dict]:
    """Find shortest path between two nodes using Cypher shortestPath."""
    cypher = f"""
        MATCH (a:{from_label} {{id: $from_id}}),
              (b:{to_label}   {{id: $to_id}})
        MATCH path = shortestPath((a)-[*..{max_depth}]-(b))
        RETURN [node IN nodes(path) | {{
            label: labels(node)[0],
            id:    node.id,
            name:  coalesce(node.name, node.description, node.id)
        }}] AS path_nodes,
        length(path) AS depth
    """
    rows = _run(cypher, {"from_id": from_id, "to_id": to_id})
    return rows


def semantic_search_nodes(embedding: List[float], label: str = None,
                           top_k: int = 10) -> List[Dict]:
    """
    Semantic similarity search using Neo4j vector index (if available)
    or fallback to Aurora pgvector via the document_chunks table.
    Neo4j 5.x+ supports native vector indexes.
    """
    # Try Neo4j vector index first (Neo4j 5.11+)
    try:
        index_name = f"{label.lower()}_embedding" if label else "node_embedding"
        cypher = f"""
            CALL db.index.vector.queryNodes($index, $k, $embedding)
            YIELD node, score
            RETURN properties(node) AS props, labels(node) AS labels, score AS similarity
            ORDER BY similarity DESC
        """
        rows = _run(cypher, {"index": index_name, "k": top_k, "embedding": embedding})
        if rows:
            return [{
                "label":      r["labels"][0] if r.get("labels") else label or "",
                "properties": r.get("props", {}),
                "similarity": float(r.get("similarity", 0)),
            } for r in rows]
    except Exception:
        pass

    # Fallback: text-based search using full-text index
    if label == "Requirement":
        return _fulltext_search_requirements("", top_k)

    # Last fallback: return all nodes of label
    return find_nodes(label or "Requirement", limit=top_k)


def _fulltext_search_requirements(query: str, limit: int = 10) -> List[Dict]:
    """Full-text search on requirement descriptions."""
    if not query:
        return find_nodes("Requirement", limit=limit)
    cypher = """
        CALL db.index.fulltext.queryNodes('req_text', $query)
        YIELD node, score
        RETURN properties(node) AS props, score AS similarity
        LIMIT $limit
    """
    try:
        rows = _run(cypher, {"query": query, "limit": limit})
        return [{
            "label":      "Requirement",
            "properties": r.get("props", {}),
            "similarity": float(r.get("similarity", 0)),
        } for r in rows]
    except Exception:
        return find_nodes("Requirement", limit=limit)


def get_neighbourhood(label: str, node_id: str, depth: int = 2) -> Dict:
    """Get full neighbourhood context for a node."""
    node     = get_node(label, node_id)
    out_1hop = traverse_out(label, node_id, limit=20)
    in_1hop  = traverse_in(label,  node_id, limit=20)

    out_2hop = []
    if depth >= 2:
        for n in out_1hop[:5]:
            n_id    = n.get("properties", {}).get("id", "")
            n_label = n.get("label", "")
            if n_id and n_label:
                hop2 = traverse_out(n_label, n_id, limit=5)
                out_2hop.extend(hop2)

    return {
        "node":     node,
        "outgoing": out_1hop,
        "incoming": in_1hop,
        "depth2":   out_2hop,
    }


# ── Domain-specific helpers ───────────────────────────────────────────────────
def store_document(doc_path: str, doc_name: str, meta: Dict = None) -> str:
    """Store a Document node."""
    return upsert_node("Document", doc_path, {
        "name": doc_name, "path": doc_path, **(meta or {})
    })


def store_requirement(req_id: str, doc_id: str, description: str,
                      req_type: str, priority: str, domain: str,
                      confidence: float, embedding: List[float] = None) -> str:
    """Store a Requirement node and link it to its Document."""
    upsert_node("Requirement", req_id, {
        "description": description, "type": req_type,
        "priority": priority, "domain": domain,
        "confidence": confidence, "document_id": doc_id,
        "status": "extracted",
    }, embedding=embedding)
    # Create relationships
    upsert_edge("Document",    doc_id, "CONTAINS",       "Requirement", req_id,
                {"confidence": confidence}, weight=confidence)
    upsert_edge("Requirement", req_id, "EXTRACTED_FROM", "Document",    doc_id,
                {"confidence": confidence}, weight=confidence)
    return req_id


def store_expert(expert_id: str, name: str, dept: str,
                 skills: List[str], specs: List[str],
                 embedding: List[float] = None) -> str:
    """Store an Expert node and link to Domain nodes."""
    upsert_node("Expert", expert_id, {
        "name": name, "department": dept,
        "skills": skills, "specializations": specs,
        "availability": "available", "workload": 0,
    }, embedding=embedding)
    for spec in specs:
        upsert_node("Domain", spec, {"name": spec})
        upsert_edge("Expert", expert_id, "SPECIALIZES_IN", "Domain", spec,
                    {"level": "primary"}, weight=1.0)
    return expert_id


def assign_expert(req_id: str, expert_id: str,
                  score: float, reason: str = "") -> str:
    """Create ASSIGNED_TO relationship between Expert and Requirement."""
    return upsert_edge("Expert", expert_id, "ASSIGNED_TO", "Requirement", req_id,
                       {"score": score, "reason": reason}, weight=score)


def link_similar_requirements(req_id1: str, req_id2: str,
                               similarity: float) -> str:
    """Create SIMILAR_TO relationship between two Requirements."""
    return upsert_edge("Requirement", req_id1, "SIMILAR_TO", "Requirement", req_id2,
                       {"similarity": similarity}, weight=similarity)


def store_project(project_id: str, name: str, meta: Dict = None) -> str:
    return upsert_node("Project", project_id, {"name": name, **(meta or {})})


def link_req_to_project(req_id: str, project_id: str) -> str:
    return upsert_edge("Requirement", req_id, "PART_OF", "Project", project_id)


def get_experts_for_domain(domain: str, limit: int = 5) -> List[Dict]:
    """Find experts specializing in a domain via Cypher traversal."""
    cypher = """
        MATCH (e:Expert)-[:SPECIALIZES_IN]->(d:Domain {name: $domain})
        RETURN properties(e) AS props, e.workload AS workload
        ORDER BY workload ASC LIMIT $limit
    """
    rows = _run(cypher, {"domain": domain, "limit": limit})
    return [{"label": "Expert", "properties": r.get("props", {})} for r in rows]


def get_past_requirements(domain: str = None, limit: int = 10) -> List[Dict]:
    """Retrieve past requirements, optionally filtered by domain."""
    if domain:
        cypher = """
            MATCH (r:Requirement {domain: $domain})
            RETURN properties(r) AS props
            ORDER BY r.confidence DESC LIMIT $limit
        """
        rows = _run(cypher, {"domain": domain, "limit": limit})
    else:
        cypher = """
            MATCH (r:Requirement)
            RETURN properties(r) AS props
            ORDER BY r.confidence DESC LIMIT $limit
        """
        rows = _run(cypher, {"limit": limit})
    return [{"label": "Requirement", "properties": r.get("props", {})} for r in rows]


def cypher_query(cypher: str, params: Dict = None) -> List[Dict]:
    """Execute a raw Cypher query — for advanced graph operations."""
    return _run(cypher, params or {})


def graph_stats() -> Dict:
    """Return graph statistics using Cypher."""
    node_rows = _run("""
        MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c
        ORDER BY c DESC
    """)
    edge_rows = _run("""
        MATCH ()-[r]->() RETURN type(r) AS relationship, count(r) AS c
        ORDER BY c DESC
    """)
    nodes = {r["label"]: r["c"] for r in node_rows if r.get("label")}
    edges = {r["relationship"]: r["c"] for r in edge_rows if r.get("relationship")}
    return {
        "nodes":       nodes,
        "edges":       edges,
        "total_nodes": sum(nodes.values()),
        "total_edges": sum(edges.values()),
    }
