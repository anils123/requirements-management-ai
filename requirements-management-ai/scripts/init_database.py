"""Initialize Aurora PostgreSQL schema for requirements management."""
import json
import os
import boto3

# ── Resolve ARNs from cdk_outputs.json or env vars ───────────────────────────
REGION   = os.environ.get("AWS_REGION", "us-east-1")
ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUTS  = os.path.join(ROOT, "cdk_outputs.json")


def _load_outputs() -> dict:
    if os.path.exists(OUTPUTS):
        with open(OUTPUTS) as f:
            data = json.load(f)
        flat = {}
        for v in data.values():
            flat.update(v)
        return flat
    return {}


def initialize_database():
    """Initialize database schema for requirements management."""

    out          = _load_outputs()
    region       = os.environ.get("AWS_REGION", "us-east-1")
    cluster_arn  = os.environ.get("DB_CLUSTER_ARN")  or out.get("DbClusterArn",  "")
    secret_arn   = os.environ.get("DB_SECRET_ARN")   or out.get("DbSecretArn",   "")
    database_name = "requirements_db"

    if not cluster_arn or not secret_arn:
        raise RuntimeError(
            "DB_CLUSTER_ARN and DB_SECRET_ARN must be set or present in cdk_outputs.json"
        )

    print(f"  DB Cluster: {cluster_arn}")
    print(f"  DB Secret:  {secret_arn}")

    rds_client = boto3.client("rds-data", region_name=region)

    # Run each statement separately — RDS Data API doesn't support multi-statement SQL
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",

        """CREATE TABLE IF NOT EXISTS document_chunks (
            id              SERIAL PRIMARY KEY,
            document_path   VARCHAR(500) NOT NULL,
            chunk_id        INTEGER NOT NULL,
            text_content    TEXT NOT NULL,
            embedding       vector(1024),
            entities        JSONB,
            metadata        JSONB,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )""",

        """CREATE TABLE IF NOT EXISTS requirements (
            id                  SERIAL PRIMARY KEY,
            requirement_id      VARCHAR(50) UNIQUE NOT NULL,
            document_id         VARCHAR(100) NOT NULL,
            type                VARCHAR(50) NOT NULL,
            category            VARCHAR(100),
            priority            VARCHAR(20),
            description         TEXT NOT NULL,
            acceptance_criteria JSONB,
            domain              VARCHAR(100),
            complexity          VARCHAR(20),
            status              VARCHAR(50) DEFAULT 'extracted',
            confidence_score    FLOAT,
            source_chunk_ids    INTEGER[],
            created_at          TIMESTAMP DEFAULT NOW(),
            updated_at          TIMESTAMP DEFAULT NOW()
        )""",

        """CREATE TABLE IF NOT EXISTS domain_experts (
            id                  SERIAL PRIMARY KEY,
            expert_id           VARCHAR(50) UNIQUE NOT NULL,
            name                VARCHAR(200) NOT NULL,
            email               VARCHAR(200) NOT NULL,
            department          VARCHAR(100),
            skills              JSONB NOT NULL,
            specializations     JSONB NOT NULL,
            skill_embeddings    vector(1024),
            current_workload    INTEGER DEFAULT 0,
            max_workload        INTEGER DEFAULT 10,
            availability_status VARCHAR(50) DEFAULT 'available',
            created_at          TIMESTAMP DEFAULT NOW(),
            updated_at          TIMESTAMP DEFAULT NOW()
        )""",

        """CREATE TABLE IF NOT EXISTS expert_assignments (
            id                SERIAL PRIMARY KEY,
            requirement_id    VARCHAR(50) NOT NULL,
            expert_id         VARCHAR(50) NOT NULL,
            assignment_type   VARCHAR(50) DEFAULT 'primary',
            confidence_score  FLOAT,
            assignment_reason TEXT,
            status            VARCHAR(50) DEFAULT 'assigned',
            assigned_at       TIMESTAMP DEFAULT NOW()
        )""",

        """CREATE TABLE IF NOT EXISTS compliance_suggestions (
            id               SERIAL PRIMARY KEY,
            requirement_id   VARCHAR(50) NOT NULL,
            regulation_type  VARCHAR(100),
            suggestion_text  TEXT NOT NULL,
            confidence_score FLOAT,
            source_documents JSONB,
            status           VARCHAR(50) DEFAULT 'pending',
            created_at       TIMESTAMP DEFAULT NOW()
        )""",

        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_path      ON document_chunks(document_path)",
        "CREATE INDEX IF NOT EXISTS idx_reqs_domain      ON requirements(domain)",
        "CREATE INDEX IF NOT EXISTS idx_reqs_status      ON requirements(status)",
        "CREATE INDEX IF NOT EXISTS idx_experts_avail    ON domain_experts(availability_status)",
        "CREATE INDEX IF NOT EXISTS idx_assign_req       ON expert_assignments(requirement_id)",
        "CREATE INDEX IF NOT EXISTS idx_assign_exp       ON expert_assignments(expert_id)",
    ]

    for sql in statements:
        label = sql.strip().split("\n")[0][:60]
        try:
            rds_client.execute_statement(
                resourceArn=cluster_arn,
                secretArn=secret_arn,
                database=database_name,
                sql=sql,
            )
            print(f"  ✓ {label}")
        except Exception as e:
            err = str(e)
            # Ignore "already exists" errors — idempotent
            if "already exists" in err.lower():
                print(f"  ~ {label} (already exists)")
            else:
                print(f"  ✗ {label}: {err}")
                raise

    print("Database schema initialized successfully.")


if __name__ == "__main__":
    initialize_database()
