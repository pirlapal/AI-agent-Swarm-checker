const { test } = require('node:test');
const assert = require('node:assert/strict');
const cdk = require('aws-cdk-lib');
const { Template, Match } = require('aws-cdk-lib/assertions');
const { AiAgentBackendSwarmStack } = require('../build/lib/ai-agent-backend-swarm-stack');
const app = new cdk.App();
const stack = new AiAgentBackendSwarmStack(app, 'OfflineTest');
const template = Template.fromStack(stack);

test('creates workflow storage with partition and sort keys', () => {
  template.hasResourceProperties('AWS::DynamoDB::Table', {
    KeySchema: [{ AttributeName: 'PK', KeyType: 'HASH' }, { AttributeName: 'SK', KeyType: 'RANGE' }],
    BillingMode: 'PAY_PER_REQUEST',
  });
});
test('creates document storage and CRUD Lambda handlers', () => {
  template.resourceCountIs('AWS::S3::Bucket', 1);
  const functions = template.findResources('AWS::Lambda::Function');
  const handlers = Object.values(functions).map(f => f.Properties.Handler);
  for (const name of ['create_workflow', 'get_workflow', 'start_case', 's3_presigned_url']) {
    assert.ok(handlers.includes(`${name}.handler`), name);
  }
});
test('API routes include case creation', () => {
  template.hasResourceProperties('AWS::ApiGateway::Resource', { PathPart: 'cases' });
  template.hasResourceProperties('AWS::ApiGateway::Method', { HttpMethod: 'POST', Integration: Match.objectLike({ Type: 'AWS_PROXY' }) });
});
test('base-stack data policies avoid service-wide wildcard grants', () => {
  const policies = template.findResources('AWS::IAM::Policy');
  let checked = 0;
  for (const resource of Object.values(policies)) {
    for (const statement of resource.Properties.PolicyDocument.Statement) {
      const actions = [].concat(statement.Action || []);
      assert.ok(!actions.some(a => ['s3:*', 'dynamodb:*', 'apigateway:*', 'logs:*'].includes(a)), actions.join(','));
      if (actions.some(a => /^(s3|dynamodb):/.test(a))) {
        assert.notEqual(statement.Resource, '*');
        checked++;
      }
    }
  }
  assert.ok(checked > 0);
});
