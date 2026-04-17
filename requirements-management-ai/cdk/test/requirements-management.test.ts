import { expect as expectCDK, haveResource } from '@aws-cdk/assert';
import * as cdk from 'aws-cdk-lib';
import { RequirementsManagementStack } from '../lib/requirements-management-stack';

test('Stack synthesizes', () => {
  const app = new cdk.App();
  const stack = new RequirementsManagementStack(app, 'TestStack');
  expect(stack).toBeDefined();
});
