"""Load sample expert profiles into the database with skill embeddings."""
import json
import os
import sys
import boto3

ROOT         = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUTS_FILE = os.path.join(ROOT, "cdk_outputs.json")
EXPERTS_FILE = os.path.join(ROOT, "examples", "expert_profiles.json")
REGION       = os.environ.get("AWS_REGION", "us-east-1")


def _load_outputs() -> dict:
    if os.path.exists(OUTPUTS_FILE):
        with open(OUTPUTS_FILE) as f:
            data = json.load(f)
        flat = {}
        for v in data.values():
            flat.update(v)
        return flat
    return {}


def load_experts():
    out      = _load_outputs()
    db_arn   = os.environ.get("DB_CLUSTER_ARN") or out.get("DbClusterArn", "")
    db_secret= os.environ.get("DB_SECRET_ARN")  or out.get("DbSecretArn",  "")

    if not db_arn or not db_secret:
        raise RuntimeError(
            "DB_CLUSTER_ARN and DB_SECRET_ARN must be set or present in cdk_outputs.json"
        )

    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    rds     = boto3.client("rds-data",        region_name=REGION)

    with open(EXPERTS_FILE) as f:
        experts = json.load(f)

    sql = """
        INSERT INTO domain_experts
            (expert_id, name, email, department, skills, specializations,
             skill_embeddings, current_workload, max_workload, availability_status)
        VALUES
            (:expert_id, :name, :email, :department, :skills::jsonb, :specializations::jsonb,
             :skill_embeddings::vector, :current_workload, :max_workload, :availability_status)
        ON CONFLICT (expert_id) DO UPDATE SET
            skills=EXCLUDED.skills,
            specializations=EXCLUDED.specializations,
            skill_embeddings=EXCLUDED.skill_embeddings,
            updated_at=NOW()
    """

    for expert in experts:
        skill_text = " ".join(expert["skills"] + expert["specializations"])
        resp       = bedrock.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": skill_text[:8000]}),
        )
        embedding = json.loads(resp["body"].read())["embedding"]
        print(f"  Loading expert: {expert['expert_id']} — {expert['department']}")

        rds.execute_statement(
            resourceArn=db_arn,
            secretArn=db_secret,
            database="requirements_db",
            sql=sql,
            parameters=[
                {"name": "expert_id",           "value": {"stringValue": expert["expert_id"]}},
                {"name": "name",                "value": {"stringValue": expert["name"]}},
                {"name": "email",               "value": {"stringValue": expert["email"]}},
                {"name": "department",          "value": {"stringValue": expert["department"]}},
                {"name": "skills",              "value": {"stringValue": json.dumps(expert["skills"])}},
                {"name": "specializations",     "value": {"stringValue": json.dumps(expert["specializations"])}},
                {"name": "skill_embeddings",    "value": {"stringValue": str(embedding)}},
                {"name": "current_workload",    "value": {"longValue": expert.get("current_workload", 0)}},
                {"name": "max_workload",        "value": {"longValue": expert.get("max_workload", 10)}},
                {"name": "availability_status", "value": {"stringValue": expert.get("availability_status", "available")}},
            ],
        )

    print(f"Loaded {len(experts)} expert profiles successfully.")


if __name__ == "__main__":
    load_experts()
