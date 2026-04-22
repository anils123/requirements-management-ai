import boto3, json

rds     = boto3.client("rds-data",        region_name="us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

DB  = "arn:aws:rds:us-east-1:672996977856:cluster:requirementsmanagementstack-vectordatabase3f35b757-1puh70gvsblh"
SEC = "arn:aws:secretsmanager:us-east-1:672996977856:secret:RequirementsManagementStack-uEpN70J2Wx5n-KmDmDi"

def q(sql):
    r = rds.execute_statement(resourceArn=DB, secretArn=SEC,
                              database="requirements_db", sql=sql,
                              formatRecordsAs="JSON")
    return json.loads(r.get("formattedRecords", "[]"))

# Generate embedding
r   = bedrock.invoke_model(modelId="amazon.titan-embed-text-v2:0",
                            body=json.dumps({"inputText": "charging system voltage"}))
emb = json.loads(r["body"].read())["embedding"]
emb_str = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
print(f"Embedding dim: {len(emb)}, SQL size: {len(emb_str)} chars")

# Test 1: ORDER BY only, no computed column
print("\nTest 1: ORDER BY vector distance only")
try:
    rows = q(f"SELECT document_path, chunk_id, LEFT(text_content,80) as txt "
             f"FROM document_chunks ORDER BY embedding<=>'{emb_str}'::vector LIMIT 5")
    print(f"  Results: {len(rows)}")
    for row in rows:
        print(f"  {row.get('document_path','').split('/')[-1]}: {row.get('txt','')[:60]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 2: With similarity score as separate subquery
print("\nTest 2: Subquery with similarity")
try:
    rows = q(f"SELECT document_path, chunk_id, LEFT(text_content,80) as txt, "
             f"(1-(embedding<=>'{emb_str}'::vector)) as sim "
             f"FROM document_chunks ORDER BY sim DESC LIMIT 5")
    print(f"  Results: {len(rows)}")
    for row in rows:
        print(f"  [{row.get('sim',0):.3f}] {row.get('document_path','').split('/')[-1]}: {row.get('txt','')[:60]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 3: Check if embeddings are actually vector type
print("\nTest 3: Check vector type")
try:
    rows = q("SELECT pg_typeof(embedding) as typ FROM document_chunks LIMIT 1")
    print(f"  Type: {rows}")
except Exception as e:
    print(f"  Error: {e}")
