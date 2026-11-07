import json
import boto3
import uuid
import os
import time

workflows_table_name = os.environ['WORKFLOWS_TABLE_NAME']
aws_region = os.environ['DEPLOYMENT_REGION']

dynamodb = boto3.client("dynamodb", region_name=aws_region)


def handler(event, context):

    try:
        body = json.loads(event.get('body') or '{}')
        if not isinstance(body, dict) or not isinstance(body.get('name'), str) or not body['name'].strip():
            return build_response(400, {'error': 'A workflow name is required'})
        definition = body.get('definition', {'categories': []})
        if not isinstance(definition, dict) or not isinstance(definition.get('categories', []), list):
            return build_response(400, {'error': 'Invalid workflow definition'})
        for category in definition.get('categories', []):
            if not isinstance(category, dict) or not isinstance(category.get('rules', []), list) or any(not isinstance(rule, dict) for rule in category.get('rules', [])):
                return build_response(400, {'error': 'Invalid workflow category or rules'})
    except (ValueError, TypeError):
        return build_response(400, {'error': 'Invalid JSON body'})

    body_1 = body

    name = body_1['name']
    owner_id = body_1.get('owner-id', 'default')
    definition_in = body_1.get('definition', {"categories": []})


    categories_in = definition_in.get('categories', [])

    categories_dynamo = []
    for category in categories_in:
        category_id = category.get('category_id') or str(uuid.uuid4())
        category_name = str(category.get('name', ''))

        rules_in = category.get('rules', [])
        rules_dynamo = []
        for rule in rules_in:
            rule_id = rule.get('rule_id') or str(uuid.uuid4())
            rule_name = str(rule.get('name', ''))
            rule_config = rule.get('config', {})

            rules_dynamo.append({
                'M': {
                    'rule_id': {'S': rule_id},
                    'name': {'S': rule_name},
                    'config': {'S': json.dumps(rule_config)},
                }
            })

        categories_dynamo.append({
            'M': {
                'category_id': {'S': category_id},
                'name': {'S': category_name},
                'rules': {'L': rules_dynamo},
            }
        })

    workflow_id = str(uuid.uuid4())
    now = int(time.time())

    item = {
        'PK': {'S': f'WORKFLOW#{workflow_id}'},
        'SK': {'S': 'META'},
        'workflow_id': {'S': workflow_id},
        'name': {'S': name},
        'owner_id': {'S': owner_id},
        'version': {'N': '1'},
        'created_at': {'N': str(now)},
        'updated_at': {'N': str(now)},
        'GSI1PK': {'S': f'OWNER#{owner_id}'},
        'GSI1SK': {'S': f'WORKFLOW#{now}#{workflow_id}'},
        'definition': {
            'M': {
                'categories': {'L': categories_dynamo},
            }
        },
    }

    print("*************** -- item to put -- ********************* \n")
    print("************************************ \n")

    try:
        dynamodb.put_item(
            TableName=workflows_table_name,
            Item=item,
            ConditionExpression="attribute_not_exists(PK)",
        )
    except Exception as e:
        print(f"Error creating workflow: {str(e)}")
        return build_response(500, {"error": "Failed to create workflow"})

    print(f"Created workflow {workflow_id}")

    return build_response(201, {
        "workflow_id": workflow_id,
        "version": 1,
    })


def build_response(status_code, body):

    return {
        'statusCode': status_code,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }
