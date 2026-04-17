cat > cdk/lib/requirements-management-stack.ts << 'EOF'
import * as cdk from 'aws-cdk-lib';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as opensearch from 'aws-cdk-lib/aws-opensearchserverless';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export class RequirementsManagementStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPC Configuration for secure networking
    const vpc = new ec2.Vpc(this, 'RequirementsVPC', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: 24,
          name: 'Database',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
      ],
    });

    // S3 Bucket for document storage
    const documentBucket = new s3.Bucket(this, 'DocumentBucket', {
      bucketName: `requirements-documents-${this.account}-${this.region}`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [{
        id: 'DeleteOldVersions',
        noncurrentVersionExpiration: cdk.Duration.days(90),
      }],
      removalPolicy: cdk.RemovalPolicy.DESTROY, // For development
    });

    // Aurora PostgreSQL Cluster with pgvector
    const dbCluster = new rds.DatabaseCluster(this, 'VectorDatabase', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_15_4,
      }),
      instanceProps: {
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
        vpcSubnets: {
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
        vpc,
      },
      defaultDatabaseName: 'requirements_db',
      credentials: rds.Credentials.fromGeneratedSecret('postgres'),
      storageEncrypted: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // For development
    });

    // OpenSearch Serverless Collection
    const opensearchCollection = new opensearch.CfnCollection(this, 'SearchCollection', {
      name: 'requirements-search',
      type: 'VECTORSEARCH',
      description: 'Vector search collection for requirements management',
    });

    // OpenSearch Security Policy
    new opensearch.CfnSecurityPolicy(this, 'SearchSecurityPolicy', {
      name: 'requirements-search-security-policy',
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [{
          ResourceType: 'collection',
          Resource: [`collection/requirements-search`],
        }],
        AWSOwnedKey: true,
      }),
    });

    // IAM Role for Bedrock Knowledge Base
    const knowledgeBaseRole = new iam.Role(this, 'KnowledgeBaseRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      inlinePolicies: {
        S3Access: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ['s3:GetObject', 's3:ListBucket'],
              resources: [
                documentBucket.bucketArn,
                `${documentBucket.bucketArn}/*`,
              ],
            }),
          ],
        }),
        OpenSearchAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'aoss:APIAccessAll',
                'aoss:DashboardsAccessAll',
              ],
              resources: [opensearchCollection.attrArn],
            }),
          ],
        }),
        BedrockAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeModel',
                'bedrock:InvokeModelWithResponseStream',
              ],
              resources: ['*'],
            }),
          ],
