# Deployment Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://python.org |
| Node.js | 20 LTS | https://nodejs.org |
| AWS CLI v2 | Latest | https://aws.amazon.com/cli |
| AWS CDK | 2.170+ | `npm install -g aws-cdk` |
| Git Bash | Latest | https://git-scm.com (Windows) |

### AWS Account Requirements
- IAM user with AdministratorAccess (or scoped permissions)
- Bedrock model access: Claude 3.5 Sonnet, Titan Embeddings V2, Nova Pro, Nova Micro
- Regions supported: `us-east-1` (recommended)

### Neo4j AuraDB (Free Tier)
1. Go to https://console.neo4j.io
2. Click **New Instance** → **AuraDB Free**
3. Note the connection URI: `neo4j+s://xxxxx.databases.neo4j.io`
4. Save the generated password

---

## Step 1 — Configure AWS Credentials

```bash
aws configure
# AWS Access Key ID: AKIA...
# AWS Secret Access Key: ...
# Default region: us-east-1
# Default output format: json

# Verify
aws sts get-caller-identity
```

---

## Step 2 — Deploy AWS Infrastructure (CDK)

```bash
cd cdk
npm install

# Bootstrap CDK (one-time per account/region)
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# Deploy all stacks
npx cdk deploy RequirementsManagementStack \
  --require-approval never \
  --outputs-file ../cdk_outputs.json

# This deploys (~20-25 minutes):
# - VPC with public/private/isolated subnets
# - Aurora PostgreSQL Serverless v2 with pgvector
# - S3 bucket for documents
# - 4 Lambda functions + API Gateway
# - OpenSearch Serverless collection
# - ElastiCache Redis
# - IAM roles and security groups
```

---

## Step 3 — Post-Deploy Setup

```bash
cd ..  # back to project root

# Run full setup (initializes DB, loads experts, creates Bedrock agent)
python scripts/post_deploy_setup.py
```

This script:
1. Verifies Bedrock model access
2. Creates OpenSearch indexes
3. Creates Bedrock AgentCore agent with 6 action groups
4. Initializes Aurora schema (pgvector + all tables)
5. Loads expert profiles with embeddings
6. Creates S3 folder structure
7. Writes GitHub Actions secrets to `.env.secrets`

---

## Step 4 — Deploy Neo4j Graph Architecture

```bash
# Set Neo4j credentials
export NEO4J_URI="neo4j+s://xxxxx.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"

# Deploy Neo4j integration
python scripts/deploy_neo4j.py
```

This script:
1. Verifies Neo4j connection
2. Creates graph schema (constraints + indexes)
3. Migrates existing data (documents, requirements, experts) to Neo4j
4. Rebuilds Lambda layer with `neo4j` package
5. Redeploys all Lambdas with Neo4j env vars
6. Updates Bedrock AgentCore instruction
7. Tests end-to-end

---

## Step 5 — Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

---

## Step 6 — Install Frontend Dependencies

```bash
cd frontend
npm install
```

---

## Step 7 — Start Development Servers

**Terminal 1 — Backend:**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open: **http://localhost:3000**

---

## Step 8 — Upload Sample Documents

```bash
# Upload to S3
aws s3 cp your-bid-document.pdf \
  s3://$(python -c "import json; d=json.load(open('cdk_outputs.json')); print(list(d.values())[0]['DocumentBucketName'])")/bids/

# Or use the UI: Documents tab → drag and drop
```

---

## Redeployment

### Redeploy Lambda Functions Only
```bash
python scripts/redeploy_lambdas.py
```

### Redeploy Full Infrastructure
```bash
cd cdk
npx cdk deploy RequirementsManagementStack --require-approval never
```

### Update Agent Instruction
```bash
python scripts/fix_agent_final.py
```

---

## Environment Variables

### Backend (set in shell or .env)
```bash
# Auto-loaded from cdk_outputs.json — no manual setup needed
AWS_ACCOUNT_REGION=us-east-1
DB_CLUSTER_ARN=arn:aws:rds:...
DB_SECRET_ARN=arn:aws:secretsmanager:...
BUCKET_NAME=requirementsmanagementstack-...

# Neo4j (required for graph features)
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>
```

### Lambda Functions (set via AWS Console or CDK)
All Lambda functions automatically receive env vars from the CDK stack.
Neo4j vars are added by `deploy_neo4j.py`.

---

## GitHub Actions CI/CD

Add these secrets to your GitHub repository:
**Settings → Secrets and variables → Actions**

```
AWS_ACCESS_KEY_ID          (from .env.secrets)
AWS_SECRET_ACCESS_KEY      (from .env.secrets)
AWS_ACCESS_KEY_ID_PROD     (production account)
AWS_SECRET_ACCESS_KEY_PROD (production account)
DB_CLUSTER_ARN             (from cdk_outputs.json)
DB_SECRET_ARN              (from cdk_outputs.json)
BUCKET_NAME                (from cdk_outputs.json)
OPENSEARCH_ENDPOINT        (from cdk_outputs.json)
AGENT_ID                   (from agent_id.txt)
AGENT_ALIAS_ID             (from agent_alias_id.txt)
NEO4J_URI                  (your AuraDB URI)
NEO4J_PASSWORD             (your AuraDB password)
```

Pipelines:
- **Push to `develop`** → deploy to staging
- **Push to `main`** → deploy to production

---

## Troubleshooting

### "No module named 'aws_lambda_powertools'"
```bash
python scripts/redeploy_lambdas.py
```
The Lambda layer needs rebuilding.

### "ResourceNotFoundException calling InvokeAgent"
The Bedrock agent alias is stale. Run:
```bash
python scripts/fix_agent_final.py
```

### "Cannot connect to Neo4j"
Check env vars are set:
```bash
echo $NEO4J_URI
echo $NEO4J_USER
```

### "No requirements found after extraction"
The document may not have been processed. Re-process it:
```bash
aws lambda invoke \
  --function-name RequirementsManagementSta-DocumentProcessor3D49A08-kKbHVGTb1bVQ \
  --payload '{"actionGroup":"DocumentProcessor","apiPath":"/process-document","httpMethod":"POST","requestBody":{"content":{"application/json":{"properties":[{"name":"document_path","value":"bids/your-file.pdf"}]}}}}' \
  response.json
cat response.json
```

### Aurora connection errors
Verify the Lambda is in the correct VPC subnet and security group allows port 5432.

### Cost Optimization
- Aurora Serverless v2 scales to 0 when idle (set min capacity to 0.5 ACU)
- Use `cdk destroy` to tear down all resources when not in use
- Estimated idle cost: ~$3-5/day (Aurora + Redis + OpenSearch)

---

## Production Checklist

- [ ] Enable AWS CloudTrail for audit logging
- [ ] Set up CloudWatch alarms for Lambda errors
- [ ] Enable S3 versioning and lifecycle policies
- [ ] Configure Aurora automated backups (7-day retention)
- [ ] Set up WAF for API Gateway
- [ ] Enable VPC Flow Logs
- [ ] Rotate Neo4j password and update Lambda env vars
- [ ] Set `removalPolicy: RETAIN` for Aurora in CDK (already set)
- [ ] Configure custom domain for API Gateway
- [ ] Enable HTTPS for frontend (CloudFront + ACM)
