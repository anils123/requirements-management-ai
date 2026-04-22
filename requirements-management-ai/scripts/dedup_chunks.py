"""
dedup_chunks.py — Remove duplicate document chunks from Aurora.
Keeps only the latest chunk per (document_path, chunk_id) pair.
"""
import boto3, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values(): OUT.update(v)

DB  = OUT["DbClusterArn"]
SEC = OUT["DbSecretArn"]
rds = boto3.client("rds-data", region_name="us-east-1")

def q(sql, fmt=False):
    kw = dict(resourceArn=DB, secretArn=SEC, database="requirements_db", sql=sql)
    if fmt: kw["formatRecordsAs"] = "JSON"
    r = rds.execute_statement(**kw)
    if fmt: return json.loads(r.get("formattedRecords", "[]"))
    return r

# Check duplicates before
rows = q("SELECT document_path, COUNT(*) as total, COUNT(DISTINCT chunk_id) as unique_chunks FROM document_chunks GROUP BY document_path ORDER BY total DESC", fmt=True)
print("Before dedup:")
for r in rows:
    dups = r['total'] - r['unique_chunks']
    print(f"  {r['document_path'].split('/')[-1]:40s} total={r['total']} unique={r['unique_chunks']} dups={dups}")

# Delete duplicates — keep only the row with the highest id per (document_path, chunk_id)
print("\nRemoving duplicates...")
q("""
DELETE FROM document_chunks
WHERE id NOT IN (
    SELECT MAX(id)
    FROM document_chunks
    GROUP BY document_path, chunk_id
)
""")
print("Duplicates removed.")

# Also fix the ON CONFLICT clause — add unique constraint if missing
try:
    q("CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_unique ON document_chunks(document_path, chunk_id)")
    print("Unique index created on (document_path, chunk_id)")
except Exception as e:
    print(f"Index note: {e}")

# Check after
rows2 = q("SELECT document_path, COUNT(*) as total FROM document_chunks GROUP BY document_path ORDER BY total DESC", fmt=True)
print("\nAfter dedup:")
for r in rows2:
    print(f"  {r['document_path'].split('/')[-1]:40s} chunks={r['total']}")
