import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { RequirementsManagementStack } from '../lib/requirements-management-stack';

const app = new cdk.App();
new RequirementsManagementStack(app, 'RequirementsManagementStack');
