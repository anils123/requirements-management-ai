#!/bin/bash
# deploy.sh - Complete deployment script

set -e

# Configuration
AWS_REGION="us-east-1"
STACK_NAME="requirements-management"
ENVIRONMENT="production"

echo "Starting Requirements Management System Deployment..."

# 1. Deploy infrastructure
echo "Deploying infrastructure with CDK..."
cd cdk
npm install
npx cdk bootstrap
npx cdk deploy --require-approval never

# 2. Build and package Lambda functions
echo "Building Lambda functions..."
cd ../src/lambda

# Build dependencies layer
echo "Building dependencies layer..."
mkdir -p layers/dependencies/python
pip install -r requirements.txt -t layers/dependencies/python/
cd layers/dependencies && zip -r ../../dependencies-layer.zip . && cd ../..

# Package Lambda functions
for function in document-processor requirements-extractor expert-matcher compliance-checker; do
    echo "Packaging $function..."
    cd $function
    zip -r ../${function}.zip .
    cd ..
done

# 3. Upload Lambda packages to S3
echo "Uploading Lambda packages..."
aws s3 mb s3://requirements-management-deployments-${AWS_REGION} || true

aws s3 cp dependencies-layer.zip s3://requirements-management-deployments-${AWS_REGION}/layers/
for function in document-processor requirements-extractor expert-matcher compliance-checker; do
    aws s3 cp ${function}.zip s3://requirements-management-deployments-${AWS_REGION}/functions/
done

# 4. Deploy Bedrock Knowledge Bases
echo "Deploying Bedrock Knowledge Bases..."
cd ../../cloudformation
aws cloudformation deploy \
    --template-file bedrock-knowledge-bases.yaml \
    --stack-name ${STACK_NAME}-knowledge-bases \
    --parameter-overrides \
        DocumentBucketName=requirements-documents-$(aws sts get-caller-identity --query Account --output text) \
        OpenSearchCollectionArn=$(aws cloudformation describe-stacks --stack-name ${STACK_NAME} --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchCollectionArn`].OutputValue' --output text) \
        KnowledgeBaseRoleArn=$(aws cloudformation describe-stacks --stack-name ${STACK_NAME} --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseRoleArn`].OutputValue' --output text) \
    --capabilities CAPABILITY_IAM

# 5. Create Bedrock Agent
echo "Creating Bedrock Agent..."
cd ../scripts
python create_bedrock_agent.py

# 6. Initialize database schema
echo "Initializing database schema..."
python init_database.py

# 7. Load sample data
echo "Loading sample expert data..."
python load_sample_data.py

# 8. Run tests
echo "Running deployment tests..."
python test_deployment.py

echo "Deployment completed successfully!"
echo "API Endpoint: $(aws cloudformation describe-stacks --stack-name ${STACK_NAME} --query 'Stacks[0].Outputs[?OutputKey==`APIEndpoint`].OutputValue' --output text)"
echo "Agent ID: $(cat agent_id.txt)"
