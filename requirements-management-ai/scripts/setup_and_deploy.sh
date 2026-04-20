#!/usr/bin/env bash
# =============================================================================
# setup_and_deploy.sh
# Requirements Management AI — Full setup + deployment for Git Bash on Windows
#
# Usage:
#   chmod +x scripts/setup_and_deploy.sh
#   ./scripts/setup_and_deploy.sh
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${CYAN}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="RequirementsManagementStack"
PYTHON="/c/Users/z0044e6b/AppData/Local/Programs/Python/Python313/python.exe"
PIP="/c/Users/z0044e6b/AppData/Local/Programs/Python/Python313/Scripts/pip.exe"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Step 0: Verify Git Bash environment ──────────────────────────────────────
step "Step 0: Verifying environment"

if [[ -z "${BASH_VERSION:-}" ]]; then
  error "This script must be run in Git Bash."
fi

if [[ ! -f "$PYTHON" ]]; then
  error "Python not found at $PYTHON. Adjust the PYTHON variable at the top of this script."
fi
success "Python found: $("$PYTHON" --version)"

# ── Step 1: Install AWS CLI v2 ────────────────────────────────────────────────
step "Step 1: AWS CLI"

if command -v aws &>/dev/null; then
  success "AWS CLI already installed: $(aws --version 2>&1 | head -1)"
else
  info "Downloading AWS CLI v2 installer..."
  AWSCLI_MSI="$TEMP/AWSCLIV2.msi"
  curl -sSL "https://awscli.amazonaws.com/AWSCLIV2.msi" -o "$AWSCLI_MSI"
  info "Installing AWS CLI v2 (requires admin — a UAC prompt may appear)..."
  msiexec.exe //i "$(cygpath -w "$AWSCLI_MSI")" //quiet //norestart
  # Reload PATH so aws is available in this session
  export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"
  if command -v aws &>/dev/null; then
    success "AWS CLI installed: $(aws --version 2>&1 | head -1)"
  else
    warn "AWS CLI installed but not yet on PATH. Close and reopen Git Bash, then re-run this script."
    warn "Or add 'C:/Program Files/Amazon/AWSCLIV2' to your PATH manually."
    exit 0
  fi
fi

# ── Step 2: Configure AWS credentials ────────────────────────────────────────
step "Step 2: AWS credentials"

if aws sts get-caller-identity &>/dev/null; then
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  success "Authenticated as account: $ACCOUNT_ID"
else
  warn "AWS credentials not configured. Running 'aws configure'..."
  echo ""
  echo "  You will need:"
  echo "    - AWS Access Key ID"
  echo "    - AWS Secret Access Key"
  echo "    - Default region (press Enter to use: $AWS_REGION)"
  echo "    - Output format (press Enter for: json)"
  echo ""
  aws configure
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  success "Authenticated as account: $ACCOUNT_ID"
fi

# ── Step 3: Install Node.js ───────────────────────────────────────────────────
step "Step 3: Node.js"

if command -v node &>/dev/null; then
  success "Node.js already installed: $(node --version)"
else
  info "Downloading Node.js LTS installer..."
  NODE_MSI="$TEMP/node-lts.msi"
  NODE_URL=$(curl -sSL https://nodejs.org/dist/index.json | \
    "$PYTHON" -c "import sys,json; d=[x for x in json.load(sys.stdin) if x['lts']]; print(d[0]['files'][0] if d else '')" 2>/dev/null || echo "")

  # Fallback to known stable URL
  curl -sSL "https://nodejs.org/dist/v20.18.0/node-v20.18.0-x64.msi" -o "$NODE_MSI"
  info "Installing Node.js LTS (a UAC prompt may appear)..."
  msiexec.exe //i "$(cygpath -w "$NODE_MSI")" //quiet //norestart

  export PATH="$PATH:/c/Program Files/nodejs"
  if command -v node &>/dev/null; then
    success "Node.js installed: $(node --version)"
  else
    warn "Node.js installed but not yet on PATH. Close and reopen Git Bash, then re-run this script."
    exit 0
  fi
fi

# ── Step 4: Install AWS CDK ───────────────────────────────────────────────────
step "Step 4: AWS CDK"

if command -v cdk &>/dev/null; then
  success "CDK already installed: $(cdk --version)"
else
  info "Installing AWS CDK and TypeScript globally..."
  npm install -g aws-cdk typescript ts-node
  success "CDK installed: $(cdk --version)"
fi

# ── Step 5: Install Python dependencies ──────────────────────────────────────
step "Step 5: Python dependencies"

info "Installing Lambda layer dependencies..."
"$PIP" install -q \
  boto3 \
  aws-lambda-powertools \
  opensearch-py \
  requests-aws4auth \
  redis \
  numpy \
  cohere \
  aws-cdk-lib \
  constructs
success "Python dependencies installed."

# ── Step 6: CDK bootstrap ─────────────────────────────────────────────────────
step "Step 6: CDK bootstrap (one-time per account/region)"

cd "$PROJECT_ROOT/cdk"
info "Installing CDK npm dependencies at pinned versions..."
npm install --silent
info "Verifying TypeScript compilation..."
npx tsc --noEmit && success "TypeScript compilation OK" || error "TypeScript errors — check cdk/lib/*.ts"
info "Bootstrapping CDK for account $ACCOUNT_ID / region $AWS_REGION..."
npx cdk bootstrap "aws://$ACCOUNT_ID/$AWS_REGION" --require-approval never
success "CDK bootstrap complete."

# ── Step 7: CDK deploy ────────────────────────────────────────────────────────
step "Step 7: CDK deploy — infrastructure"

info "Deploying all stacks (VPC, Aurora, OpenSearch, Redis, Lambdas, Bedrock Agent)..."
info "This typically takes 15-25 minutes on first deploy."
npx cdk deploy "$STACK_NAME" \
  --require-approval never \
  --outputs-file "$PROJECT_ROOT/cdk_outputs.json"

success "CDK deploy complete. Outputs saved to cdk_outputs.json"
cat "$PROJECT_ROOT/cdk_outputs.json"

# ── Step 8: Parse CDK outputs ─────────────────────────────────────────────────
step "Step 8: Reading CDK outputs"

parse_output() {
  "$PYTHON" -c "
import json, sys
with open('$PROJECT_ROOT/cdk_outputs.json') as f:
    data = json.load(f)
for stack in data.values():
    if '$1' in stack:
        print(stack['$1'])
        sys.exit(0)
print('')
"
}

export DB_CLUSTER_ARN=$(parse_output "DbClusterArn")
export DB_SECRET_ARN=$(parse_output "DbSecretArn")
export BUCKET_NAME=$(parse_output "DocumentBucketName")
export OPENSEARCH_ENDPOINT=$(parse_output "OpenSearchEndpoint")
export REDIS_ENDPOINT=$(parse_output "RedisEndpoint")
export DOCUMENT_PROCESSOR_LAMBDA_ARN=$(parse_output "DocumentProcessorArn")
export REQUIREMENTS_EXTRACTOR_LAMBDA_ARN=$(parse_output "RequirementsExtractorArn")
export EXPERT_MATCHER_LAMBDA_ARN=$(parse_output "ExpertMatcherArn")
export COMPLIANCE_CHECKER_LAMBDA_ARN=$(parse_output "ComplianceCheckerArn")
export REQUIREMENTS_KB_ID=$(parse_output "RequirementsKbId")
export REGULATORY_KB_ID=$(parse_output "RegulatoryKbId")
export EXPERTS_KB_ID=$(parse_output "ExpertsKbId")
export AWS_REGION="$AWS_REGION"

info "DB_CLUSTER_ARN:    $DB_CLUSTER_ARN"
info "BUCKET_NAME:       $BUCKET_NAME"
info "OPENSEARCH:        $OPENSEARCH_ENDPOINT"
info "REDIS:             $REDIS_ENDPOINT"
info "REQUIREMENTS_KB:   $REQUIREMENTS_KB_ID"

# ── Step 9: Build Lambda layer ────────────────────────────────────────────────
step "Step 9: Build Lambda dependencies layer"

LAYER_DIR="$PROJECT_ROOT/layers/dependencies/python"
mkdir -p "$LAYER_DIR"
info "Installing packages into layer directory..."
"$PIP" install -q \
  -r "$PROJECT_ROOT/layers/dependencies/requirements.txt" \
  -t "$LAYER_DIR"
success "Lambda layer built at $LAYER_DIR"

# ── Step 10: Package Lambda functions ─────────────────────────────────────────
step "Step 10: Package Lambda functions"

cd "$PROJECT_ROOT/src/lambda"
for fn in document-processor requirements-extractor expert-matcher compliance-checker; do
  info "Packaging $fn..."
  cd "$fn"
  zip -qr "../${fn}.zip" .
  cd ..
  success "Packaged: ${fn}.zip"
done

# ── Step 11: Upload Lambda packages to S3 ────────────────────────────────────
step "Step 11: Upload Lambda packages to S3"

DEPLOY_BUCKET="requirements-management-deployments-${AWS_REGION}"
aws s3 mb "s3://$DEPLOY_BUCKET" --region "$AWS_REGION" 2>/dev/null || true

for fn in document-processor requirements-extractor expert-matcher compliance-checker; do
  info "Uploading ${fn}.zip..."
  aws s3 cp "${fn}.zip" "s3://$DEPLOY_BUCKET/functions/${fn}.zip"
done
success "All Lambda packages uploaded to s3://$DEPLOY_BUCKET/functions/"

# ── Step 12: Initialize database schema ──────────────────────────────────────
step "Step 12: Initialize Aurora PostgreSQL schema (pgvector)"

cd "$PROJECT_ROOT"
info "Running init_database.py..."
"$PYTHON" scripts/init_database.py
success "Database schema initialized."

# ── Step 13: Load expert profiles ────────────────────────────────────────────
step "Step 13: Load expert profiles"

info "Running load_sample_data.py..."
"$PYTHON" scripts/load_sample_data.py
success "Expert profiles loaded."

# ── Step 14: Create Bedrock Agent ─────────────────────────────────────────────
step "Step 14: Create Bedrock AgentCore agent"

info "Running create_bedrock_agent.py..."
"$PYTHON" scripts/create_bedrock_agent.py
success "Bedrock Agent created."

# Read agent outputs written by create_bedrock_agent.py
if [[ -f "$PROJECT_ROOT/agent_id.txt" ]]; then
  export AGENT_ID=$(cat "$PROJECT_ROOT/agent_id.txt")
  info "Agent ID: $AGENT_ID"
fi
if [[ -f "$PROJECT_ROOT/agent_alias_id.txt" ]]; then
  export AGENT_ALIAS_ID=$(cat "$PROJECT_ROOT/agent_alias_id.txt")
  info "Agent Alias ID: $AGENT_ALIAS_ID"
fi

# ── Step 15: Run smoke tests ──────────────────────────────────────────────────
step "Step 15: Smoke tests"

cd "$PROJECT_ROOT"
"$PYTHON" scripts/test_deployment.py
success "All smoke tests passed."

# ── Done ──────────────────────────────────────────────────────────────────────
API_ENDPOINT=$(parse_output "ApiEndpoint")

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Deployment completed successfully!                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}API Endpoint:${NC}    $API_ENDPOINT"
echo -e "  ${CYAN}Agent ID:${NC}        ${AGENT_ID:-see agent_id.txt}"
echo -e "  ${CYAN}Agent Alias:${NC}     ${AGENT_ALIAS_ID:-see agent_alias_id.txt}"
echo -e "  ${CYAN}S3 Bucket:${NC}       $BUCKET_NAME"
echo -e "  ${CYAN}OpenSearch:${NC}      $OPENSEARCH_ENDPOINT"
echo -e "  ${CYAN}Redis Cache:${NC}     $REDIS_ENDPOINT"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Upload a bid PDF:  aws s3 cp your-bid.pdf s3://$BUCKET_NAME/bids/"
echo -e "  2. Invoke the agent via the API or AWS Console → Bedrock → Agents"
echo ""
