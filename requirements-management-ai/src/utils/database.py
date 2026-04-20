import json
import boto3
from typing import Any, Dict, List, Optional
from .config import CONFIG

_rds = boto3.client("rds-data", region_name=CONFIG["aws_region"])

def _exec(sql: str, params: List[Dict] = None) -> Dict:
    kwargs = dict(
        resourceArn=CONFIG["db_cluster_arn"],
        secretArn=CONFIG["db_secret_arn"],
        database=CONFIG["db_name"],
        sql=sql,
    )
    if params:
        kwargs["parameters"] = params
    return _rds.execute_statement(**kwargs)

def get_db_connection():
    """Return a thin wrapper for executing parameterised SQL via RDS Data API."""
    return _exec

def vector_similarity_search(embedding: List[float], table: str,
                              vector_col: str, select_cols: str,
                              limit: int = 10,
                              filter_sql: str = "") -> List[Dict]:
    where = f"WHERE {filter_sql}" if filter_sql else ""
    sql = f"""
        SELECT {select_cols},
               1 - ({vector_col} <=> '{embedding}'::vector) AS similarity
        FROM {table}
        {where}
        ORDER BY {vector_col} <=> '{embedding}'::vector
        LIMIT {limit}
    """
    resp = _exec(sql)
    return resp.get("records", [])

def upsert_expert(expert: Dict) -> None:
    sql = """
        INSERT INTO domain_experts
            (expert_id, name, email, department, skills, specializations,
             skill_embeddings, current_workload, availability_status)
        VALUES
            (:expert_id,:name,:email,:department,:skills,:specializations,
             :skill_embeddings::vector,:current_workload,:availability_status)
        ON CONFLICT (expert_id) DO UPDATE SET
            skills=EXCLUDED.skills,
            specializations=EXCLUDED.specializations,
            skill_embeddings=EXCLUDED.skill_embeddings,
            updated_at=NOW()
    """
    _exec(sql, [
        {"name": "expert_id",           "value": {"stringValue": expert["expert_id"]}},
        {"name": "name",                "value": {"stringValue": expert["name"]}},
        {"name": "email",               "value": {"stringValue": expert["email"]}},
        {"name": "department",          "value": {"stringValue": expert["department"]}},
        {"name": "skills",              "value": {"stringValue": json.dumps(expert["skills"])}},
        {"name": "specializations",     "value": {"stringValue": json.dumps(expert["specializations"])}},
        {"name": "skill_embeddings",    "value": {"stringValue": str(expert["skill_embeddings"])}},
        {"name": "current_workload",    "value": {"longValue": expert.get("current_workload", 0)}},
        {"name": "availability_status", "value": {"stringValue": expert.get("availability_status", "available")}},
    ])
