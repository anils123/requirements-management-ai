import json
import boto3
from typing import List, Dict, Any, Optional
from ..utils.config import CONFIG

_bedrock    = boto3.client("bedrock-runtime", region_name=CONFIG["aws_region"])
_comprehend = boto3.client("comprehend",      region_name=CONFIG["aws_region"])

# Neptune client (Gremlin via boto3 neptune-graph or HTTP endpoint)
_neptune_endpoint = CONFIG.get("knowledge_graph_endpoint", "")


def extract_entities_and_relations(text: str) -> Dict[str, Any]:
    """Extract entities and their relationships from text using Comprehend + LLM."""
    # Step 1: NER with Comprehend
    entities = []
    for chunk in [text[i:i+4900] for i in range(0, len(text), 4900)]:
        resp = _comprehend.detect_entities(Text=chunk, LanguageCode="en")
        entities.extend(resp.get("Entities", []))

    # Step 2: Relation extraction with LLM
    entity_names = list({e["Text"] for e in entities[:30]})
    prompt = (
        f"Extract relationships between these entities from the text. "
        f"Return JSON: {{\"relations\": [{{\"subject\": \"A\", \"predicate\": \"relates_to\", \"object\": \"B\"}}]}}\n\n"
        f"Entities: {entity_names}\n\nText: {text[:2000]}"
    )
    relations = []
    try:
        resp = _bedrock.invoke_model(
            modelId=CONFIG["fast_llm_model"],
            body=json.dumps({
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.1,
                "anthropic_version": "bedrock-2023-05-31",
            }),
        )
        text_out = json.loads(resp["body"].read())["content"][0]["text"]
        start, end = text_out.find("{"), text_out.rfind("}") + 1
        relations = json.loads(text_out[start:end]).get("relations", [])
    except Exception:
        pass

    return {"entities": entities, "relations": relations}


def graph_traversal_search(entity: str, depth: int = 2) -> List[Dict]:
    """
    Traverse the knowledge graph starting from an entity node.
    Returns connected nodes up to `depth` hops away.
    Falls back to empty list if Neptune is not configured.
    """
    if not _neptune_endpoint:
        return []

    # Gremlin query via Neptune HTTP endpoint
    import urllib.request
    gremlin_query = (
        f"g.V().has('name', '{entity}')"
        f".repeat(both().simplePath()).times({depth})"
        f".path().by(valueMap('name','type','description'))"
    )
    try:
        url = f"https://{_neptune_endpoint}:8182/gremlin"
        data = json.dumps({"gremlin": gremlin_query}).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            result = json.loads(r.read())
        return result.get("result", {}).get("data", {}).get("@value", [])
    except Exception:
        return []


def enrich_results_with_graph(results: List[Dict]) -> List[Dict]:
    """Add graph-neighbour context to each retrieved chunk."""
    for result in results:
        entities = result.get("metadata", {}).get("entities", [])
        graph_context = []
        for ent in entities[:3]:  # limit graph calls
            neighbours = graph_traversal_search(ent, depth=1)
            graph_context.extend(neighbours)
        if graph_context:
            result["graph_context"] = graph_context
    return results
