// cdk/requirements-management-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as opensearch from 'aws-cdk-lib/aws-opensearchserverless';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export class RequirementsManagementStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPC for secure networking
    const vpc = new ec2.Vpc(this, 'RequirementsVPC', {
      maxAzs: 3,
      natGateways: 2,
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
      bucketName: `requirements-documents-${this.account}`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [{
        id: 'DeleteOldVersions',
        noncurrentVersionExpiration: cdk.Duration.days(90),
      }],
    });

    // Aurora PostgreSQL with pgvector
    const dbCluster = new rds.DatabaseCluster(this, 'VectorDatabase', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_15_4,
      }),
      instanceProps: {
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.R6G, ec2.InstanceSize.LARGE),
        vpcSubnets: {
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        },
        vpc,
      },
      defaultDatabaseName: 'requirements_db',
      credentials: rds.Credentials.fromGeneratedSecret('postgres'),
      storageEncrypted: true,
      parameterGroup: new rds.ParameterGroup(this, 'DbParameterGroup', {
        engine: rds.DatabaseClusterEngine.auroraPostgres({
          version: rds.AuroraPostgresEngineVersion.VER_15_4,
        }),
        parameters: {
          'shared_preload_libraries': 'vector',
          'max_connections': '1000',
        },
      }),
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
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonBedrockFullAccess'),
      ],
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
      },
    });

    // Lambda Layer for dependencies
    const dependenciesLayer = new lambda.LayerVersion(this, 'DependenciesLayer', {
      code: lambda.Code.fromAsset('layers/dependencies'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
      description: 'Dependencies for requirements management functions',
    });

    // Document Processing Lambda
    const documentProcessor = new lambda.Function(this, 'DocumentProcessor', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'document_processor.handler',
      code: lambda.Code.fromAsset('src/lambda/document-processor'),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.minutes(15),
      memorySize: 3008,
      environment: {
        BUCKET_NAME: documentBucket.bucketName,
        DB_CLUSTER_ARN: dbCluster.clusterArn,
        DB_SECRET_ARN: dbCluster.secret!.secretArn,
      },
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
    });

    // Requirements Extractor Lambda
    const requirementsExtractor = new lambda.Function(this, 'RequirementsExtractor', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'requirements_extractor.handler',
      code: lambda.Code.fromAsset('src/lambda/requirements-extractor'),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.minutes(10),
      memorySize: 2048,
      environment: {
        BUCKET_NAME: documentBucket.bucketName,
        OPENSEARCH_ENDPOINT: opensearchCollection.attrCollectionEndpoint,
      },
      vpc,
    });

    // Expert Matcher Lambda
    const expertMatcher = new lambda.Function(this, 'ExpertMatcher', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'expert_matcher.handler',
      code: lambda.Code.fromAsset('src/lambda/expert-matcher'),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        DB_CLUSTER_ARN: dbCluster.clusterArn,
        DB_SECRET_ARN: dbCluster.secret!.secretArn,
      },
      vpc,
    });

    // Compliance Checker Lambda
    const complianceChecker = new lambda.Function(this, 'ComplianceChecker', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'compliance_checker.handler',
      code: lambda.Code.fromAsset('src/lambda/compliance-checker'),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.minutes(8),
      memorySize: 1536,
      environment: {
        OPENSEARCH_ENDPOINT: opensearchCollection.attrCollectionEndpoint,
      },
      vpc,
    });

    // Grant permissions
    documentBucket.grantReadWrite(documentProcessor);
    documentBucket.grantRead(requirementsExtractor);
    dbCluster.grantDataApiAccess(documentProcessor);
    dbCluster.grantDataApiAccess(expertMatcher);

    // API Gateway
    const api = new apigateway.RestApi(this, 'RequirementsAPI', {
      restApiName: 'Requirements Management API',
      description: 'API for requirements management system',
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    // API Resources
    const documentsResource = api.root.addResource('documents');
    documentsResource.addMethod('POST', new apigateway.LambdaIntegration(documentProcessor));

    const requirementsResource = api.root.addResource('requirements');
    requirementsResource.addMethod('POST', new apigateway.LambdaIntegration(requirementsExtractor));

    const expertsResource = api.root.addResource('experts');
    expertsResource.addMethod('POST', new apigateway.LambdaIntegration(expertMatcher));

    const complianceResource = api.root.addResource('compliance');
    complianceResource.addMethod('POST', new apigateway.LambdaIntegration(complianceChecker));

    // Outputs
    new cdk.CfnOutput(this, 'DocumentBucketName', {
      value: documentBucket.bucketName,
      description: 'S3 bucket for document storage',
    });

    new cdk.CfnOutput(this, 'DatabaseClusterArn', {
      value: dbCluster.clusterArn,
      description: 'Aurora PostgreSQL cluster ARN',
    });

    new cdk.CfnOutput(this, 'APIEndpoint', {
      value: api.url,
      description: 'API Gateway endpoint URL',
    });
  }
}
