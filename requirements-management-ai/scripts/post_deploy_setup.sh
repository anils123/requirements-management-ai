#!/usr/bin/env bash
# =============================================================================
# post_deploy_setup.sh
# Runs all 6 post-deployment steps after CDK deploy completes.
# Usage: ./scripts/post_deploy_setup.sh
# =============================================================================
set -euo pipefail

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${CYAN}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

PYTHON="/c/Users/z0044e6b/AppData/Local/Programs/Python/Python313/python.exe"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUTS_FILE="$PROJECT_ROOT/cdk_outputs.json"
REGION="${AWS_REGION:-us-east-1}"

# ── Load CDK outputs ──────────────────────────────────────────────────────────
[[ -f "$OUTPUTS_FILE" ]] || error "cdk_outputs.json not found. Run CDK deploy first."

parse_output() {
  "$PYTHON" -c "
import json, sys
with open('$OUTPUTS_FILE') as f:
    data = json.load(f)
for stack in data.values():
    if '$1' in stack:
        print(stack['$1']); sys.exit(0)
print('')
"
}

export DB_CLUSTER_ARN=$(parse_output "DbClusterArn")
export DB_SECRET_ARN=$(parse_output "DbSecretArn")
export BUCKET_NAME=$(parse_output "DocumentBucketName")
export OPENSEARCH_ENDPOINT=$(parse_output "OpenSearchEndpoint")
export DOCUMENT_PROCESSOR_LAMBDA_ARN=$(parse_output "DocumentProcessorArn")
export REQUIREMENTS_EXTRACTOR_LAMBDA_ARN=$(parse_output "RequirementsExtractorArn")
export EXPERT_MATCHER_LAMBDA_ARN=$(parse_output "ExpertMatcherArn")
export COMPLIANCE_CHECKER_LAMBDA_ARN=$(parse_output "ComplianceCheckerArn")
export REQUIREMENTS_KB_ID=$(parse_output "RequirementsKbId")
export REGULATORY_KB_ID=$(parse_output "RegulatoryKbId")
export EXPERTS_KB_ID=$(parse_output "ExpertsKbId")
export AWS_REGION="$REGION"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

info "Account:  $ACCOUNT"
info "Region:   $REGION"
info "Bucket:   $BUCKET_NAME"

# =============================================================================
# STEP 1 — Enable Bedrock Model Access
# =============================================================================
step "Step 1: Verify Bedrock Model Access"

REQUIRED_MODELS=(
  "anthropic.claude-3-5-sonnet-20241022-v2:0"
  "anthropic.claude-3-haiku-20240307-v1:0"
  "amazon.titan-embed-text-v2:0"
)

ALL_OK=true
for MODEL in "${REQUIRED_MODELS[@]}"; do
  STATUS=$(aws bedrock get-foundation-model \
    --model-identifier "$MODEL" \
    --region "$REGION" \
    --query "modelDetails.modelLifecycle.status" \
    --output text 2>/dev/null || echo "NOT_FOUND")

  ACCESS=$(aws bedrock list-foundation-models \
    --region "$REGION" \
    --query "modelSummaries[?modelId=='$MODEL'].modelLifecycle.status" \
    --output text 2>/dev/null || echo "")

  if aws bedrock invoke-model \
      --model-id "$MODEL" \
      --body '{"inputText":"test"}' \
      --region "$REGION" \
      /tmp/bedrock_test.json &>/dev/null 2>&1; then
    success "Model accessible: $MODEL"
  else
    warn "Model NOT accessible: $MODEL"
    warn "  → Go to: https://console.aws.amazon.com/bedrock/home?region=$REGION#/modelaccess"
    warn "  → Click 'Manage model access' and enable: Claude 3.5 Sonnet, Claude 3 Haiku, Titan Embeddings V2"
    ALL_OK=false
  fi
done

if [[ "$ALL_OK" == "false" ]]; then
  echo ""
  warn "Some models are not enabled. Enable them in the console then re-run this script."
  warn "URL: https://console.aws.amazon.com/bedrock/home?region=$REGION#/modelaccess"
  read -p "Press Enter once you have enabled model access to continue..."
fi

# =============================================================================
# STEP 2 — Set up Knowledge Bases (create OpenSearch indexes + sync data sources)
# =============================================================================
step "Step 2: Configure Bedrock Knowledge Bases"

setup_kb_index() {
  local INDEX_NAME=$1
  local COLLECTION_ENDPOINT=$2
  info "Creating OpenSearch index: $INDEX_NAME"

  curl -s -X PUT \
    "${COLLECTION_ENDPOINT}/${INDEX_NAME}" \
    -H "Content-Type: application/json" \
    --aws-sigv4 "aws:amz:${REGION}:aoss" \
    --user "$(aws configure get aws_access_key_id):$(aws configure get aws_secret_access_key)" \
    -d '{
      "settings": { "index": { "knn": true } },
      "mappings": {
        "properties": {
          "vector_field": { "type": "knn_vector", "dimension": 1536,
            "method": { "name": "hnsw", "space_type": "cosinesimil",
              "engine": "nmslib", "parameters": { "ef_construction": 512, "m": 16 } }
          },
          "text":     { "type": "text" },
          "metadata": { "type": "object" }
        }
      }
    }' | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print('  Created' if d.get('acknowledged') else f'  {d}')"
}

if [[ -n "$OPENSEARCH_ENDPOINT" ]]; then
  setup_kb_index "requirements-index" "$OPENSEARCH_ENDPOINT"
  setup_kb_index "regulatory-index"   "$OPENSEARCH_ENDPOINT"
  setup_kb_index "experts-index"      "$OPENSEARCH_ENDPOINT"
  success "OpenSearch indexes created"
else
  warn "OPENSEARCH_ENDPOINT not found in CDK outputs — skipping index creation"
fi

# Sync Knowledge Base data sources if KB IDs are available
for KB_ID in "$REQUIREMENTS_KB_ID" "$REGULATORY_KB_ID" "$EXPERTS_KB_ID"; do
  if [[ -n "$KB_ID" ]]; then
    DS_ID=$(aws bedrock-agent list-data-sources \
      --knowledge-base-id "$KB_ID" \
      --region "$REGION" \
      --query "dataSourceSummaries[0].dataSourceId" \
      --output text 2>/dev/null || echo "")
    if [[ -n "$DS_ID" && "$DS_ID" != "None" ]]; then
      aws bedrock-agent start-ingestion-job \
        --knowledge-base-id "$KB_ID" \
        --data-source-id "$DS_ID" \
        --region "$REGION" &>/dev/null || true
      info "Started ingestion for KB: $KB_ID"
    fi
  fi
done
success "Knowledge Bases configured"

# =============================================================================
# STEP 3 — Create Bedrock Agent
# =============================================================================
step "Step 3: Create Bedrock Agent"

if [[ -f "$PROJECT_ROOT/agent_id.txt" ]]; then
  EXISTING_AGENT=$(cat "$PROJECT_ROOT/agent_id.txt")
  info "Agent already exists: $EXISTING_AGENT — skipping creation"
else
  info "Creating Bedrock Agent..."
  "$PYTHON" "$SCRIPT_DIR/create_bedrock_agent.py"
  success "Bedrock Agent created: $(cat "$PROJECT_ROOT/agent_id.txt" 2>/dev/null)"
fi

export AGENT_ID=$(cat "$PROJECT_ROOT/agent_id.txt" 2>/dev/null || echo "")
export AGENT_ALIAS_ID=$(cat "$PROJECT_ROOT/agent_alias_id.txt" 2>/dev/null || echo "")

# =============================================================================
# STEP 4 — Initialize Database Schema
# =============================================================================
step "Step 4: Initialize Aurora PostgreSQL Schema"

info "Running database schema initialization..."
"$PYTHON" "$SCRIPT_DIR/init_database.py"
success "Database schema initialized (pgvector + all tables + indexes)"

info "Loading expert profiles..."
"$PYTHON" "$SCRIPT_DIR/load_sample_data.py"
success "Expert profiles loaded"

# =============================================================================
# STEP 5 — Upload Sample Documents
# =============================================================================
step "Step 5: Upload Sample Documents"

# Create folder structure in S3
for PREFIX in bids/ requirements/ regulatory/ experts/; do
  aws s3api put-object \
    --bucket "$BUCKET_NAME" \
    --key "$PREFIX" \
    --region "$REGION" &>/dev/null || true
done
success "S3 folder structure created: bids/, requirements/, regulatory/, experts/"

# Upload the sample PDF if it exists
SAMPLE_PDF="$PROJECT_ROOT/examples/sample_requirements.pdf"
if [[ -f "$SAMPLE_PDF" ]]; then
  aws s3 cp "$SAMPLE_PDF" "s3://$BUCKET_NAME/bids/sample_requirements.pdf"
  success "Sample PDF uploaded: s3://$BUCKET_NAME/bids/sample_requirements.pdf"

  # Trigger document processing via Lambda
  info "Triggering document processing..."
  aws lambda invoke \
    --function-name "$(parse_output "DocumentProcessorArn" | sed 's/.*function://')" \
    --region "$REGION" \
    --payload "$(echo '{"actionGroup":"DocumentProcessor","apiPath":"/process-document","httpMethod":"POST","requestBody":{"content":{"application/json":{"properties":[{"name":"document_path","value":"bids/sample_requirements.pdf"}]}}}}' | base64 -w0)" \
    /tmp/lambda_response.json &>/dev/null || true
  success "Document processing triggered"
else
  warn "No sample PDF found at examples/sample_requirements.pdf"
  info "To test, upload any PDF:"
  info "  aws s3 cp your-bid.pdf s3://$BUCKET_NAME/bids/"
fi

# =============================================================================
# STEP 6 — Configure CI/CD (GitHub Actions secrets guidance)
# =============================================================================
step "Step 6: Configure CI/CD — GitHub Actions Secrets"

API_ENDPOINT=$(parse_output "ApiEndpoint")

echo ""
echo -e "${YELLOW}Add these secrets to your GitHub repository:${NC}"
echo -e "  Settings → Secrets and variables → Actions → New repository secret"
echo ""
echo -e "  ${CYAN}Secret Name${NC}                        ${CYAN}Value${NC}"
echo    "  ─────────────────────────────────────────────────────────────────"
echo -e "  AWS_ACCESS_KEY_ID                  $(aws configure get aws_access_key_id)"
echo -e "  AWS_SECRET_ACCESS_KEY              $(aws configure get aws_secret_access_key)"
echo -e "  AWS_ACCESS_KEY_ID_PROD             $(aws configure get aws_access_key_id)"
echo -e "  AWS_SECRET_ACCESS_KEY_PROD         $(aws configure get aws_secret_access_key)"
echo -e "  DB_CLUSTER_ARN                     $DB_CLUSTER_ARN"
echo -e "  DB_SECRET_ARN                      $DB_SECRET_ARN"
echo -e "  BUCKET_NAME                        $BUCKET_NAME"
echo -e "  OPENSEARCH_ENDPOINT                $OPENSEARCH_ENDPOINT"
echo -e "  AGENT_ID                           ${AGENT_ID:-<see agent_id.txt>}"
echo -e "  AGENT_ALIAS_ID                     ${AGENT_ALIAS_ID:-<see agent_alias_id.txt>}"
echo ""

# Write secrets to a local file for reference (gitignored)
SECRETS_FILE="$PROJECT_ROOT/.env.secrets"
cat > "$SECRETS_FILE" <<EOF
# GitHub Actions secrets — DO NOT COMMIT THIS FILE
AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id)
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key)
DB_CLUSTER_ARN=$DB_CLUSTER_ARN
DB_SECRET_ARN=$DB_SECRET_ARN
BUCKET_NAME=$BUCKET_NAME
OPENSEARCH_ENDPOINT=$OPENSEARCH_ENDPOINT
AGENT_ID=${AGENT_ID:-}
AGENT_ALIAS_ID=${AGENT_ALIAS_ID:-}
API_ENDPOINT=$API_ENDPOINT
EOF

# Ensure .env.secrets is gitignored
grep -q ".env.secrets" "$PROJECT_ROOT/.gitignore" 2>/dev/null || \
  echo ".env.secrets" >> "$PROJECT_ROOT/.gitignore"

success "Secrets written to .env.secrets (gitignored)"

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Post-deployment setup complete!                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}API Endpoint:${NC}   $API_ENDPOINT"
echo -e "  ${CYAN}Agent ID:${NC}       ${AGENT_ID:-see agent_id.txt}"
echo -e "  ${CYAN}S3 Bucket:${NC}      $BUCKET_NAME"
echo -e "  ${CYAN}OpenSearch:${NC}     $OPENSEARCH_ENDPOINT"
echo ""
echo -e "  ${YELLOW}Test the agent:${NC}"
echo -e "  aws bedrock-agent-runtime invoke-agent \\"
echo -e "    --agent-id ${AGENT_ID:-\$AGENT_ID} \\"
echo -e "    --agent-alias-id ${AGENT_ALIAS_ID:-\$AGENT_ALIAS_ID} \\"
echo -e "    --session-id test-session-001 \\"
echo -e "    --input-text 'Process the bid document at bids/sample_requirements.pdf' \\"
echo -e "    --region $REGION \\"
echo -e "    output.json"
echo ""
