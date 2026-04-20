import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { RequirementsManagementStack } from '../lib/requirements-management-stack';

let template: Template;

beforeAll(() => {
  const app   = new cdk.App();
  const stack = new RequirementsManagementStack(app, 'TestStack', {
    env: { account: '123456789012', region: 'us-east-1' },
  });
  template = Template.fromStack(stack);
});

test('S3 bucket is created with versioning and SSL enforced', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    VersioningConfiguration: { Status: 'Enabled' },
  });
});

test('Aurora PostgreSQL cluster is created', () => {
  template.hasResourceProperties('AWS::RDS::DBCluster', {
    Engine: 'aurora-postgresql',
    StorageEncrypted: true,
  });
});

test('OpenSearch Serverless collection is VECTORSEARCH type', () => {
  template.hasResourceProperties('AWS::OpenSearchServerless::Collection', {
    Type: 'VECTORSEARCH',
  });
});

test('Four Lambda functions are created', () => {
  template.resourceCountIs('AWS::Lambda::Function', 4);
});

test('API Gateway REST API is created', () => {
  template.resourceCountIs('AWS::ApiGateway::RestApi', 1);
});

test('Secrets Manager secret exists for Cohere API key', () => {
  template.hasResourceProperties('AWS::SecretsManager::Secret', {
    Name: 'requirements-management/cohere-api-key',
  });
});

test('Lambda execution role has Bedrock invoke permissions', () => {
  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Action: Match.arrayWith(['bedrock:InvokeModel']),
          Effect: 'Allow',
        }),
      ]),
    },
  });
});
