"""Offline Lambda contract tests: boto3 is replaced before importing handlers."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

def load_handler(name):
    client = Mock()
    sdk = types.ModuleType('boto3')
    sdk.client = Mock(return_value=client)
    spec = importlib.util.spec_from_file_location(name, ROOT / 'backend' / 'lambda' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'boto3': sdk}), patch.dict(os.environ, {'WORKFLOWS_TABLE_NAME': 'fictional-test-table', 'DEPLOYMENT_REGION': 'us-east-1'}):
        spec.loader.exec_module(module)
    return module, client

class WorkflowContracts(unittest.TestCase):
    def test_create_preserves_categories_and_rule_config(self):
        handler, client = load_handler('create_workflow')
        response = handler.handler({'body': json.dumps({'name': 'Synthetic review', 'definition': {'categories': [{'name': 'Documents', 'rules': [{'name': 'Required document', 'config': {'required': True}}]}]}})}, None)
        self.assertEqual(response['statusCode'], 201)
        item = client.put_item.call_args.kwargs['Item']
        category = item['definition']['M']['categories']['L'][0]['M']
        self.assertEqual(category['name']['S'], 'Documents')
        self.assertEqual(json.loads(category['rules']['L'][0]['M']['config']['S']), {'required': True})
        self.assertEqual(item['version']['N'], '1')

    def test_invalid_create_requests_do_not_write(self):
        for payload in ['broken', '[]', '{}', '{"name":""}', '{"name":"x","definition":null}', '{"name":"x","definition":{"categories":[null]}}']:
            with self.subTest(payload=payload):
                handler, client = load_handler('create_workflow')
                self.assertEqual(handler.handler({'body': payload}, None)['statusCode'], 400)
                client.put_item.assert_not_called()

    def test_create_error_does_not_return_sdk_detail(self):
        handler, client = load_handler('create_workflow')
        client.put_item.side_effect = Exception('internal-service-detail')
        result = handler.handler({'body': '{"name":"test"}'}, None)
        self.assertEqual(result['statusCode'], 500)
        self.assertNotIn('internal-service-detail', result['body'])

    def test_get_requires_id(self):
        handler, client = load_handler('get_workflow')
        self.assertEqual(handler.handler({}, None)['statusCode'], 400)
        client.get_item.assert_not_called()

    def test_get_missing_record(self):
        handler, client = load_handler('get_workflow'); client.get_item.return_value = {}
        self.assertEqual(handler.handler({'pathParameters': {'id': 'missing'}}, None)['statusCode'], 404)

    def test_get_deserializes_nested_dynamodb_data(self):
        handler, client = load_handler('get_workflow')
        client.get_item.return_value = {'Item': {'name': {'S': 'Synthetic'}, 'version': {'N': '2'}, 'definition': {'M': {'categories': {'L': []}}}}}
        result = handler.handler({'pathParameters': {'id': 'test'}}, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(json.loads(result['body']), {'name': 'Synthetic', 'version': 2, 'definition': {'categories': []}})

    def test_case_requires_parent(self):
        handler, client = load_handler('start_case'); client.get_item.return_value = {}
        result = handler.handler({'pathParameters': {'id': 'missing'}, 'body': '{}'}, None)
        self.assertEqual(result['statusCode'], 404)
        client.put_item.assert_not_called()

    def test_case_creation_returns_file_upload_keys(self):
        handler, client = load_handler('start_case'); client.get_item.return_value = {'Item': {'PK': {'S': 'WORKFLOW#test'}}}
        result = handler.handler({'pathParameters': {'id': 'test'}, 'body': '{"case_file_names":["synthetic.pdf"]}'}, None)
        self.assertEqual(result['statusCode'], 201)
        case = json.loads(result['body'])
        self.assertEqual(case['case_files'][0]['s3_key'], f"cases/test/{case['case_id']}/synthetic.pdf")
        client.put_item.assert_called_once()

if __name__ == '__main__':
    unittest.main()
