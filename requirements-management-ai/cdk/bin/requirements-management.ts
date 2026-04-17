

import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { RequirementsManagementStack } from '../lib/requirements-management-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
};

new RequirementsManagementStack(app, 'RequirementsManagementStack', {
  env,
  description: 'Requirements Management AI System Infrastructure',
});
