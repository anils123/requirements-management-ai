import boto3, json, os

ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values(): OUT.update(v)

DB_ARN    = OUT["DbClusterArn"]
DB_SECRET = OUT["DbSecretArn"]
rds       = boto3.client("rds-data", region_name="us-east-1")

def q(sql, params=None):
    kw = dict(resourceArn=DB_ARN, secretArn=DB_SECRET,
              database="requirements_db", sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    r = rds.execute_statement(**kw)
    return json.loads(r.get("formattedRecords", "[]"))

print("=== document_chunks (distinct paths) ===")
for row in q("SELECT DISTINCT document_path, COUNT(*) as chunks FROM document_chunks GROUP BY document_path"):
    print(f"  path='{row['document_path']}' chunks={row['chunks']}")

print("\n=== requirements (distinct document_ids) ===")
for row in q("SELECT DISTINCT document_id, COUNT(*) as cnt FROM requirements GROUP BY document_id"):
    print(f"  document_id='{row['document_id']}' count={row['cnt']}")

print("\n=== latest 5 requirements ===")
for row in q("SELECT requirement_id, document_id, description FROM requirements ORDER BY created_at DESC LIMIT 5"):
    print(f"  {row['requirement_id']} | doc_id='{row['document_id']}' | {row['description'][:70]}")

print("\n=== Knowledge Graph nodes (top 10) ===")
for row in q("SELECT entity_text, entity_type, document_path, score FROM kg_nodes ORDER BY score DESC LIMIT 10"):
    print(f"  [{row['entity_type']}] {row['entity_text']} (score={row['score']:.2f}) from {row['document_path'].split('/')[-1]}")

print("\n=== Knowledge Graph edges (top 10) ===")
for row in q("SELECT n1.entity_text, e.predicate, n2.entity_text FROM kg_edges e JOIN kg_nodes n1 ON e.subject_id=n1.entity_id JOIN kg_nodes n2 ON e.object_id=n2.entity_id LIMIT 10"):
    print(f"  {row['n1.entity_text']} --[{row['e.predicate']}]--> {row['n2.entity_text']}")

print("\n=== Document Registry ===")
for row in q("SELECT document_name, chunk_count, kb_synced, processing_status FROM document_registry ORDER BY uploaded_at DESC LIMIT 10"):
    print(f"  {row['document_name']} | chunks={row['chunk_count']} | kb_synced={row['kb_synced']} | status={row['processing_status']}")
