import * as cdk from 'aws-cdk-lib';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as opensearch from 'aws-cdk-lib/aws-opensearchserverless';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import { BedrockStack } from './bedrock-stack';

export class RequirementsManagementStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Unique suffix based on account+region to avoid name collisions
    const suffix = `${this.account}-${this.region}`;

    // ── VPC ───────────────────────────────────────────────────────────────────
    const vpc = new ec2.Vpc(this, 'RequirementsVPC', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        { cidrMask: 24, name: 'Public',   subnetType: ec2.SubnetType.PUBLIC },
        { cidrMask: 24, name: 'Private',  subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        { cidrMask: 24, name: 'Database', subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      ],
    });

    // ── S3 Document Bucket ────────────────────────────────────────────────────
    // No hardcoded bucketName — CDK generates a unique name to avoid conflicts
    const documentBucket = new s3.Bucket(this, 'DocumentBucket', {
      versioned:         true,
      encryption:        s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL:        true,
      lifecycleRules: [{
        id: 'DeleteOldVersions',
        noncurrentVersionExpiration: cdk.Duration.days(90),
      }],
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── Aurora PostgreSQL Serverless v2 with pgvector ─────────────────────────
    const dbSg = new ec2.SecurityGroup(this, 'DatabaseSG', {
      vpc,
      description: 'Aurora PostgreSQL security group',
    });

    const dbCluster = new rds.DatabaseCluster(this, 'VectorDatabase', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_4,
      }),
      writer: rds.ClusterInstance.serverlessV2('writer'),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 16,
      vpc,
      vpcSubnets:          { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups:      [dbSg],
      defaultDatabaseName: 'requirements_db',
      credentials:         rds.Credentials.fromGeneratedSecret('postgres'),
      storageEncrypted:    true,
      removalPolicy:       cdk.RemovalPolicy.SNAPSHOT,
    });

    // Enable RDS Data API
    const cfnDbCluster = dbCluster.node.defaultChild as rds.CfnDBCluster;
    cfnDbCluster.enableHttpEndpoint = true;

    const dbClusterArn = cdk.Stack.of(this).formatArn({
      service:      'rds',
      resource:     'cluster',
      resourceName: dbCluster.clusterIdentifier,
      arnFormat:    cdk.ArnFormat.COLON_RESOURCE_NAME,
    });

    // ── OpenSearch Serverless ─────────────────────────────────────────────────
    // Use suffix in names to avoid conflicts with orphaned resources
    const osCollectionName  = 'req-search';
    const osEncryptionName  = `req-enc-${this.account}`.substring(0, 32);
    const osNetworkName     = `req-net-${this.account}`.substring(0, 32);
    const osAccessName      = `req-acc-${this.account}`.substring(0, 32);

    const encryptionPolicy = new opensearch.CfnSecurityPolicy(this, 'SearchEncryptionPolicy', {
      name:   osEncryptionName,
      type:   'encryption',
      policy: JSON.stringify({
        Rules: [{ ResourceType: 'collection', Resource: [`collection/${osCollectionName}`] }],
        AWSOwnedKey: true,
      }),
    });

    const networkPolicy = new opensearch.CfnSecurityPolicy(this, 'SearchNetworkPolicy', {
      name:   osNetworkName,
      type:   'network',
      policy: JSON.stringify([{
        Rules: [
          { ResourceType: 'collection', Resource: [`collection/${osCollectionName}`] },
          { ResourceType: 'dashboard',  Resource: [`collection/${osCollectionName}`] },
        ],
        AllowFromPublic: true,
      }]),
    });

    const opensearchCollection = new opensearch.CfnCollection(this, 'SearchCollection', {
      name:        osCollectionName,
      type:        'VECTORSEARCH',
      description: 'Vector + full-text search for requirements management',
    });

    // Policies MUST be created before the collection
    opensearchCollection.addDependency(encryptionPolicy);
    opensearchCollection.addDependency(networkPolicy);

    new opensearch.CfnAccessPolicy(this, 'SearchAccessPolicy', {
      name:   osAccessName,
      type:   'data',
      policy: JSON.stringify([{
        Rules: [
          {
            ResourceType: 'collection',
            Resource:     [`collection/${osCollectionName}`],
            Permission:   [
              'aoss:CreateCollectionItems', 'aoss:DeleteCollectionItems',
              'aoss:UpdateCollectionItems', 'aoss:DescribeCollectionItems',
            ],
          },
          {
            ResourceType: 'index',
            Resource:     [`index/${osCollectionName}/*`],
            Permission:   [
              'aoss:CreateIndex', 'aoss:DeleteIndex', 'aoss:UpdateIndex',
              'aoss:DescribeIndex', 'aoss:ReadDocument', 'aoss:WriteDocument',
            ],
          },
        ],
        Principal: [`arn:aws:iam::${this.account}:root`],
      }]),
    });

    // ── Cohere API Key Secret ─────────────────────────────────────────────────
    // No hardcoded secretName to avoid conflicts
    const cohereSecret = new secretsmanager.Secret(this, 'CohereApiKey', {
      description: 'Cohere API key for re-ranking',
    });

    // ── Shared Lambda environment ─────────────────────────────────────────────
    const sharedEnv: Record<string, string> = {
      BUCKET_NAME:           documentBucket.bucketName,
      DB_CLUSTER_ARN:        dbClusterArn,
      DB_SECRET_ARN:         dbCluster.secret!.secretArn,
      OPENSEARCH_ENDPOINT:   opensearchCollection.attrCollectionEndpoint,
      COHERE_API_KEY_SECRET: cohereSecret.secretName,
      ENVIRONMENT:           'production',
      AWS_ACCOUNT_REGION:    this.region,
    };

    // ── Lambda Layer ──────────────────────────────────────────────────────────
    const depsLayer = new lambda.LayerVersion(this, 'DependenciesLayer', {
      code:               lambda.Code.fromAsset('../layers/dependencies'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
      description:        'Shared Python dependencies for Requirements Management',
    });

    // ── Lambda IAM Role ───────────────────────────────────────────────────────
    const lambdaRole = new iam.Role(this, 'LambdaExecutionRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AWSXRayDaemonWriteAccess'),
      ],
      inlinePolicies: {
        ServiceAccess: new iam.PolicyDocument({ statements: [
          new iam.PolicyStatement({
            actions:   ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
            resources: ['*'],
          }),
          new iam.PolicyStatement({
            actions:   ['s3:GetObject', 's3:PutObject', 's3:ListBucket'],
            resources: [documentBucket.bucketArn, `${documentBucket.bucketArn}/*`],
          }),
          new iam.PolicyStatement({
            actions:   ['rds-data:ExecuteStatement', 'rds-data:BatchExecuteStatement'],
            resources: [dbClusterArn],
          }),
          new iam.PolicyStatement({
            actions:   ['secretsmanager:GetSecretValue'],
            resources: [dbCluster.secret!.secretArn, cohereSecret.secretArn],
          }),
          new iam.PolicyStatement({
            actions:   [
              'textract:StartDocumentTextDetection',
              'textract:GetDocumentTextDetection',
            ],
            resources: ['*'],
          }),
          new iam.PolicyStatement({
            actions:   ['comprehend:DetectEntities', 'comprehend:DetectKeyPhrases'],
            resources: ['*'],
          }),
          new iam.PolicyStatement({
            actions:   ['aoss:APIAccessAll'],
            resources: [opensearchCollection.attrArn],
          }),
          new iam.PolicyStatement({
            actions:   ['lambda:InvokeFunction'],
            resources: ['*'],
          }),
        ]}),
      },
    });

    const lambdaDefaults = {
      runtime:      lambda.Runtime.PYTHON_3_11,
      role:         lambdaRole,
      layers:       [depsLayer],
      environment:  sharedEnv,
      timeout:      cdk.Duration.minutes(15),
      memorySize:   1024,
      tracing:      lambda.Tracing.ACTIVE,
      logRetention: logs.RetentionDays.ONE_MONTH,
      vpc,
      vpcSubnets:   { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
    };

    // ── Lambda Functions ──────────────────────────────────────────────────────
    // No hardcoded functionNames to avoid conflicts with previous failed deploy
    const documentProcessorFn = new lambda.Function(this, 'DocumentProcessor', {
      ...lambdaDefaults,
      handler:     'document_processor.handler',
      code:        lambda.Code.fromAsset('../src/lambda/document-processor'),
      description: 'Process bid PDFs with async Textract (200+ pages)',
    });

    const requirementsExtractorFn = new lambda.Function(this, 'RequirementsExtractor', {
      ...lambdaDefaults,
      handler:     'requirements_extractor.handler',
      code:        lambda.Code.fromAsset('../src/lambda/requirements-extractor'),
      description: 'Extract structured requirements using Claude 3.5 Sonnet',
    });

    const expertMatcherFn = new lambda.Function(this, 'ExpertMatcher', {
      ...lambdaDefaults,
      handler:     'expert_matcher.handler',
      code:        lambda.Code.fromAsset('../src/lambda/expert-matcher'),
      description: 'Match requirements to domain experts via embedding similarity',
    });

    const complianceCheckerFn = new lambda.Function(this, 'ComplianceChecker', {
      ...lambdaDefaults,
      handler:     'compliance_checker.handler',
      code:        lambda.Code.fromAsset('../src/lambda/compliance-checker'),
      description: 'Generate compliance suggestions with CRAG + grounded citations',
      environment: { ...sharedEnv, REDIS_ENDPOINT: 'PLACEHOLDER' },
    });

    // ── Bedrock Stack (nested) ────────────────────────────────────────────────
    new BedrockStack(this, 'BedrockStack', {
      env: props?.env,
      vpc,
      documentBucket,
      opensearchCollection,
      documentProcessorFn,
      requirementsExtractorFn,
      expertMatcherFn,
      complianceCheckerFn,
    });

    // ── API Gateway CloudWatch Logs Role (account-level requirement) ──────────
    const apiGwLogsRole = new iam.Role(this, 'ApiGatewayLogsRole', {
      assumedBy: new iam.ServicePrincipal('apigateway.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AmazonAPIGatewayPushToCloudWatchLogs'
        ),
      ],
    });

    // Must be set at account level before any API stage can enable logging
    const apiGwAccount = new apigateway.CfnAccount(this, 'ApiGatewayAccount', {
      cloudWatchRoleArn: apiGwLogsRole.roleArn,
    });

    // ── API Gateway ───────────────────────────────────────────────────────────
    const api = new apigateway.RestApi(this, 'RequirementsApi', {
      restApiName:  'Requirements Management API',
      description:  'API for Requirements Management AI system',
      deployOptions: {
        stageName:            'v1',
        tracingEnabled:       true,
        loggingLevel:         apigateway.MethodLoggingLevel.INFO,
        metricsEnabled:       true,
        throttlingRateLimit:  100,
        throttlingBurstLimit: 200,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    // API stage must be created after the account-level role is registered
    api.node.addDependency(apiGwAccount);

    const docs       = api.root.addResource('documents');
    const reqs       = api.root.addResource('requirements');
    const experts    = api.root.addResource('experts');
    const compliance = api.root.addResource('compliance');

    docs.addMethod('POST',       new apigateway.LambdaIntegration(documentProcessorFn));
    reqs.addMethod('POST',       new apigateway.LambdaIntegration(requirementsExtractorFn));
    experts.addMethod('POST',    new apigateway.LambdaIntegration(expertMatcherFn));
    compliance.addMethod('POST', new apigateway.LambdaIntegration(complianceCheckerFn));

    // ── Outputs ───────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'ApiEndpoint',              { value: api.url });
    new cdk.CfnOutput(this, 'DocumentBucketName',       { value: documentBucket.bucketName });
    new cdk.CfnOutput(this, 'DbClusterArn',             { value: dbClusterArn });
    new cdk.CfnOutput(this, 'DbSecretArn',              { value: dbCluster.secret!.secretArn });
    new cdk.CfnOutput(this, 'OpenSearchEndpoint',       { value: opensearchCollection.attrCollectionEndpoint });
    new cdk.CfnOutput(this, 'DocumentProcessorArn',     { value: documentProcessorFn.functionArn });
    new cdk.CfnOutput(this, 'RequirementsExtractorArn', { value: requirementsExtractorFn.functionArn });
    new cdk.CfnOutput(this, 'ExpertMatcherArn',         { value: expertMatcherFn.functionArn });
    new cdk.CfnOutput(this, 'ComplianceCheckerArn',     { value: complianceCheckerFn.functionArn });
  }
}
