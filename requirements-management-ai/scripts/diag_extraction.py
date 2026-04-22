import boto3, json, requests

DB  = "arn:aws:rds:us-east-1:672996977856:cluster:requirementsmanagementstack-vectordatabase3f35b757-1puh70gvsblh"
SEC = "arn:aws:secretsmanager:us-east-1:672996977856:secret:RequirementsManagementStack-uEpN70J2Wx5n-KmDmDi"
rds = boto3.client("rds-data", region_name="us-east-1")
lam = boto3.client("lambda",   region_name="us-east-1")

def q(sql, params=None):
    kw = dict(resourceArn=DB, secretArn=SEC, database="requirements_db",
              sql=sql, formatRecordsAs="JSON")
    if params: kw["parameters"] = params
    return json.loads(rds.execute_statement(**kw).get("formattedRecords","[]"))

print("=== All documents and chunk counts ===")
for row in q("SELECT document_path, COUNT(*) as chunks, MAX(created_at) as last FROM document_chunks GROUP BY document_path ORDER BY last DESC"):
    print(f"  {row['document_path'].split('/')[-1]:40s} chunks={row['chunks']}")

print("\n=== Requirements per document ===")
for row in q("SELECT document_id, COUNT(*) as cnt FROM requirements GROUP BY document_id ORDER BY cnt DESC"):
    print(f"  {row['document_id']:40s} reqs={row['cnt']}")

# Test extraction on a document with many chunks
print("\n=== Testing extraction on CH_Charging System ===")
payload = {
    "actionGroup":"RequirementsExtractor","apiPath":"/extract-requirements",
    "httpMethod":"POST","requestBody":{"content":{"application/json":{"properties":[
        {"name":"document_id","value":"CH_Charging System"}
    ]}}}
}
r = lam.invoke(FunctionName="RequirementsManagementSta-RequirementsExtractor1D9-uZTylX0rYPcR",
               LogType="Tail", Payload=json.dumps(payload))
import base64
result = json.loads(r["Payload"].read())
body   = json.loads(result["response"]["responseBody"]["application/json"]["body"])
print(f"  Extracted: {body.get('requirements_extracted',0)}")
print(f"  KG nodes:  {body.get('kg_nodes_used',0)}")
log = base64.b64decode(r.get("LogResult","")).decode()
# Show key log lines
for line in log.split("\n"):
    if any(k in line for k in ["Found","Stored","Extracted","Error","error","chunks"]):
        print(f"  LOG: {line}")
