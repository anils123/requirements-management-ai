"""
add_kg_tables.py  —  Add knowledge graph and document registry tables to Aurora.
"""
import boto3, json, os

ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "cdk_outputs.json")) as f:
    raw = json.load(f)
OUT = {}
for v in raw.values(): OUT.update(v)

DB_ARN    = OUT["DbClusterArn"]
DB_SECRET = OUT["DbSecretArn"]
rds       = boto3.client("rds-data", region_name="us-east-1")

def q(sql):
    label = sql.strip()[:60].replace("\n"," ")
    try:
        rds.execute_statement(resourceArn=DB_ARN, secretArn=DB_SECRET,
                              database="requirements_db", sql=sql)
        print(f"  OK: {label}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  ~  {label} (exists)")
        else:
            print(f"  !! {label}: {e}")

print("Adding Knowledge Graph + Document Registry tables...\n")

# Document registry — tracks every uploaded document with full metadata
q("""CREATE TABLE IF NOT EXISTS document_registry (
    id              SERIAL PRIMARY KEY,
    document_path   VARCHAR(500) UNIQUE NOT NULL,
    document_name   VARCHAR(255) NOT NULL,
    document_type   VARCHAR(20)  DEFAULT 'pdf',
    s3_bucket       VARCHAR(255),
    file_size_bytes BIGINT       DEFAULT 0,
    page_count      INTEGER      DEFAULT 0,
    chunk_count     INTEGER      DEFAULT 0,
    text_length     INTEGER      DEFAULT 0,
    kb_synced       BOOLEAN      DEFAULT FALSE,
    kb_ingestion_id VARCHAR(100),
    processing_status VARCHAR(50) DEFAULT 'pending',
    uploaded_at     TIMESTAMP    DEFAULT NOW(),
    processed_at    TIMESTAMP,
    metadata        JSONB        DEFAULT '{}'
)""")

# Knowledge graph nodes — entities extracted from documents
q("""CREATE TABLE IF NOT EXISTS kg_nodes (
    id          SERIAL PRIMARY KEY,
    entity_id   VARCHAR(100) UNIQUE NOT NULL,
    entity_text VARCHAR(500) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    document_path VARCHAR(500),
    chunk_id    INTEGER      DEFAULT 0,
    score       FLOAT        DEFAULT 1.0,
    embedding   vector(1024),
    metadata    JSONB        DEFAULT '{}',
    created_at  TIMESTAMP    DEFAULT NOW()
)""")

# Knowledge graph edges — relations between entities
q("""CREATE TABLE IF NOT EXISTS kg_edges (
    id          SERIAL PRIMARY KEY,
    edge_id     VARCHAR(100) UNIQUE NOT NULL,
    subject_id  VARCHAR(100) NOT NULL,
    predicate   VARCHAR(200) NOT NULL,
    object_id   VARCHAR(100) NOT NULL,
    document_path VARCHAR(500),
    confidence  FLOAT        DEFAULT 1.0,
    created_at  TIMESTAMP    DEFAULT NOW()
)""")

# Indexes
for sql in [
    "CREATE INDEX IF NOT EXISTS idx_kg_nodes_entity_text ON kg_nodes(entity_text)",
    "CREATE INDEX IF NOT EXISTS idx_kg_nodes_entity_type ON kg_nodes(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_kg_nodes_doc        ON kg_nodes(document_path)",
    "CREATE INDEX IF NOT EXISTS idx_kg_edges_subject    ON kg_edges(subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_kg_edges_object     ON kg_edges(object_id)",
    "CREATE INDEX IF NOT EXISTS idx_kg_edges_doc        ON kg_edges(document_path)",
    "CREATE INDEX IF NOT EXISTS idx_doc_registry_path   ON document_registry(document_path)",
    "CREATE INDEX IF NOT EXISTS idx_doc_registry_status ON document_registry(processing_status)",
]:
    q(sql)

print("\nDone.")
