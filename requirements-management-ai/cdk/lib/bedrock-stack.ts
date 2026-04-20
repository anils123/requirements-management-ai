import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as opensearch from 'aws-cdk-lib/aws-opensearchserverless';
import { CfnAgent, CfnAgentAlias, CfnKnowledgeBase } from 'aws-cdk-lib/aws-bedrock';
import { Construct } from 'constructs';

interface BedrockStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  documentBucket: s3.Bucket;
  opensearchCollection: opensearch.CfnCollection;
  documentProcessorFn: lambda.Function;
  requirementsExtractorFn: lambda.Function;
  expertMatcherFn: lambda.Function;
  complianceCheckerFn: lambda.Function;
}

export class BedrockStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: BedrockStackProps) {
    super(scope, id, props);

    // ── ElastiCache Redis for Semantic Cache ──────────────────────────────────
    const redisSubnetGroup = new elasticache.CfnSubnetGroup(this, 'RedisSubnetGroup', {
      description: 'Subnet group for Redis semantic cache',
      subnetIds: props.vpc.selectSubnets({
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      }).subnetIds,
    });

    const redisSg = new ec2.SecurityGroup(this, 'RedisSG', {
      vpc: props.vpc,
      description: 'Redis semantic cache security group',
    });

    const redisCluster = new elasticache.CfnReplicationGroup(this, 'SemanticCache', {
      replicationGroupDescription: 'Semantic cache for RAG query results',
      cacheNodeType:               'cache.t3.medium',
      engine:                      'redis',
      engineVersion:               '7.0',
      numCacheClusters:            2,
      automaticFailoverEnabled:    true,
      atRestEncryptionEnabled:     true,
      transitEncryptionEnabled:    true,
      cacheSubnetGroupName:        redisSubnetGroup.ref,
      securityGroupIds:            [redisSg.securityGroupId],
    });

    // ── Bedrock Agent IAM Role ────────────────────────────────────────────────
    const agentRole = new iam.Role(this, 'BedrockAgentRole', {
      roleName:  `BedrockAgentRole-${this.stackName}`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      inlinePolicies: {
        BedrockAccess: new iam.PolicyDocument({ statements: [
          new iam.PolicyStatement({
            actions:   [
              'bedrock:InvokeModel',
              'bedrock:InvokeModelWithResponseStream',
              'bedrock:Retrieve',
              'bedrock:RetrieveAndGenerate',
            ],
            resources: ['*'],
          }),
        ]}),
        S3Access: new iam.PolicyDocument({ statements: [
          new iam.PolicyStatement({
            actions:   ['s3:GetObject', 's3:ListBucket', 's3:PutObject'],
            resources: [
              props.documentBucket.bucketArn,
              `${props.documentBucket.bucketArn}/*`,
            ],
          }),
        ]}),
        OpenSearchAccess: new iam.PolicyDocument({ statements: [
          new iam.PolicyStatement({
            actions:   ['aoss:APIAccessAll'],
            resources: [props.opensearchCollection.attrArn],
          }),
        ]}),
        LambdaInvoke: new iam.PolicyDocument({ statements: [
          new iam.PolicyStatement({
            actions:   ['lambda:InvokeFunction'],
            resources: [
              props.documentProcessorFn.functionArn,
              props.requirementsExtractorFn.functionArn,
              props.expertMatcherFn.functionArn,
              props.complianceCheckerFn.functionArn,
            ],
          }),
        ]}),
      },
    });

    // ── Knowledge Base: Past Requirements ────────────────────────────────────
    const requirementsKb = new CfnKnowledgeBase(this, 'RequirementsKB', {
      name:        'requirements-knowledge-base',
      description: 'Past requirements and project data for compliance reference',
      roleArn:     agentRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn:   props.opensearchCollection.attrArn,
          vectorIndexName: 'requirements-index',
          fieldMapping: {
            vectorField:   'vector_field',
            textField:     'text',
            metadataField: 'metadata',
          },
        },
      },
    });

    // ── Knowledge Base: Regulatory Docs ──────────────────────────────────────
    const regulatoryKb = new CfnKnowledgeBase(this, 'RegulatoryKB', {
      name:        'regulatory-knowledge-base',
      description: 'Regulatory standards and compliance documents',
      roleArn:     agentRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn:   props.opensearchCollection.attrArn,
          vectorIndexName: 'regulatory-index',
          fieldMapping: {
            vectorField:   'vector_field',
            textField:     'text',
            metadataField: 'metadata',
          },
        },
      },
    });

    // ── Knowledge Base: Expert Profiles ──────────────────────────────────────
    const expertsKb = new CfnKnowledgeBase(this, 'ExpertsKB', {
      name:        'experts-knowledge-base',
      description: 'Domain expert profiles and skill descriptions',
      roleArn:     agentRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn:   props.opensearchCollection.attrArn,
          vectorIndexName: 'experts-index',
          fieldMapping: {
            vectorField:   'vector_field',
            textField:     'text',
            metadataField: 'metadata',
          },
        },
      },
    });

    // ── Bedrock Agent (AgentCore) ─────────────────────────────────────────────
    const agent = new CfnAgent(this, 'RequirementsAgent', {
      agentName:               'RequirementsManagementAgent',
      description:             'Agentic AI for automated requirements management from bid PDFs',
      foundationModel:         'anthropic.claude-3-5-sonnet-20241022-v2:0',
      agentResourceRoleArn:    agentRole.roleArn,
      idleSessionTtlInSeconds: 1800,
      instruction: [
        'You are an expert Requirements Management AI Assistant.',
        'Capabilities: document processing (200+ page PDFs), requirements extraction,',
        'expert assignment, and compliance analysis with grounded citations.',
        'Always cite sources with relevance scores. Flag low-confidence items for review.',
      ].join(' '),
      knowledgeBases: [
        {
          knowledgeBaseId:    requirementsKb.attrKnowledgeBaseId,
          description:        'Past requirements and project data',
          knowledgeBaseState: 'ENABLED',
        },
        {
          knowledgeBaseId:    regulatoryKb.attrKnowledgeBaseId,
          description:        'Regulatory standards',
          knowledgeBaseState: 'ENABLED',
        },
        {
          knowledgeBaseId:    expertsKb.attrKnowledgeBaseId,
          description:        'Expert profiles',
          knowledgeBaseState: 'ENABLED',
        },
      ],
      actionGroups: [
        {
          actionGroupName:     'DocumentProcessor',
          description:         'Process bid PDFs up to 200+ pages',
          actionGroupExecutor: { lambda: props.documentProcessorFn.functionArn },
          actionGroupState:    'ENABLED',
          apiSchema: {
            payload: JSON.stringify({
              openapi: '3.0.0',
              info: { title: 'Document Processing API', version: '1.0.0' },
              paths: {
                '/process-document': {
                  post: {
                    operationId: 'process_document',
                    summary:     'Process a bid PDF document',
                    requestBody: {
                      required: true,
                      content: { 'application/json': { schema: {
                        type: 'object',
                        required: ['document_path'],
                        properties: {
                          document_path: { type: 'string', description: 'S3 key of the PDF' },
                          document_type: { type: 'string', enum: ['pdf', 'docx'], default: 'pdf' },
                        },
                      }}},
                    },
                    responses: { '200': { description: 'Processing result' } },
                  },
                },
              },
            }),
          },
        },
        {
          actionGroupName:     'RequirementsExtractor',
          description:         'Extract structured requirements from processed documents',
          actionGroupExecutor: { lambda: props.requirementsExtractorFn.functionArn },
          actionGroupState:    'ENABLED',
          apiSchema: {
            payload: JSON.stringify({
              openapi: '3.0.0',
              info: { title: 'Requirements Extraction API', version: '1.0.0' },
              paths: {
                '/extract-requirements': {
                  post: {
                    operationId: 'extract_requirements',
                    summary:     'Extract requirements from a processed document',
                    requestBody: {
                      required: true,
                      content: { 'application/json': { schema: {
                        type: 'object',
                        required: ['document_id'],
                        properties: {
                          document_id:         { type: 'string' },
                          extraction_criteria: { type: 'object' },
                        },
                      }}},
                    },
                    responses: { '200': { description: 'Extracted requirements' } },
                  },
                },
              },
            }),
          },
        },
        {
          actionGroupName:     'ExpertMatcher',
          description:         'Assign domain experts to requirements',
          actionGroupExecutor: { lambda: props.expertMatcherFn.functionArn },
          actionGroupState:    'ENABLED',
          apiSchema: {
            payload: JSON.stringify({
              openapi: '3.0.0',
              info: { title: 'Expert Matching API', version: '1.0.0' },
              paths: {
                '/assign-experts': {
                  post: {
                    operationId: 'assign_experts',
                    summary:     'Assign experts to requirements',
                    requestBody: {
                      required: true,
                      content: { 'application/json': { schema: {
                        type: 'object',
                        required: ['requirements'],
                        properties: {
                          requirements:        { type: 'array', items: { type: 'object' } },
                          assignment_criteria: { type: 'object' },
                        },
                      }}},
                    },
                    responses: { '200': { description: 'Expert assignments' } },
                  },
                },
              },
            }),
          },
        },
        {
          actionGroupName:     'ComplianceChecker',
          description:         'Generate compliance suggestions with grounded citations',
          actionGroupExecutor: { lambda: props.complianceCheckerFn.functionArn },
          actionGroupState:    'ENABLED',
          apiSchema: {
            payload: JSON.stringify({
              openapi: '3.0.0',
              info: { title: 'Compliance Checker API', version: '1.0.0' },
              paths: {
                '/check-compliance': {
                  post: {
                    operationId: 'check_compliance',
                    summary:     'Generate compliance suggestions for a requirement',
                    requestBody: {
                      required: true,
                      content: { 'application/json': { schema: {
                        type: 'object',
                        required: ['requirement_id', 'requirement_text'],
                        properties: {
                          requirement_id:   { type: 'string' },
                          requirement_text: { type: 'string' },
                          domain:           { type: 'string' },
                        },
                      }}},
                    },
                    responses: { '200': { description: 'Compliance suggestions with citations' } },
                  },
                },
              },
            }),
          },
        },
      ],
    });

    // Grant Lambda functions permission to be invoked by Bedrock
    [
      props.documentProcessorFn,
      props.requirementsExtractorFn,
      props.expertMatcherFn,
      props.complianceCheckerFn,
    ].forEach(fn => {
      fn.addPermission('BedrockInvoke', {
        principal:   new iam.ServicePrincipal('bedrock.amazonaws.com'),
        sourceArn:   `arn:aws:bedrock:${this.region}:${this.account}:agent/*`,
      });
    });

    // ── Agent Alias ───────────────────────────────────────────────────────────
    const agentAlias = new CfnAgentAlias(this, 'AgentAlias', {
      agentId:        agent.attrAgentId,
      agentAliasName: 'production',
      description:    'Production alias for Requirements Management Agent',
    });

    // ── Outputs ───────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'AgentId',          { value: agent.attrAgentId });
    new cdk.CfnOutput(this, 'AgentAliasId',     { value: agentAlias.attrAgentAliasId });
    new cdk.CfnOutput(this, 'RequirementsKbId', { value: requirementsKb.attrKnowledgeBaseId });
    new cdk.CfnOutput(this, 'RegulatoryKbId',   { value: regulatoryKb.attrKnowledgeBaseId });
    new cdk.CfnOutput(this, 'ExpertsKbId',      { value: expertsKb.attrKnowledgeBaseId });
    new cdk.CfnOutput(this, 'RedisEndpoint',    { value: redisCluster.attrPrimaryEndPointAddress });
  }
}
