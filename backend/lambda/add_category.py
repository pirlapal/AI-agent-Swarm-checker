import json
import boto3
import uuid
import os
import time

workflows_table_name = os.environ['WORKFLOWS_TABLE_NAME']
aws_region = os.environ['DEPLOYMENT_REGION']

dynamodb = boto3.client("dynamodb", region_name=aws_region)


def handler(event, context):
    print(event)
    print(json.dumps(event))

    path_params = event.get('pathParameters') or {}
    workflow_id = path_params.get('id')
    print(f"workflow_id: {workflow_id}")

    if not workflow_id:
        return build_response(400, {"error": "workflow id is required in path"})

    body = json.loads(event['body'])
    body_1 = body
    print(body_1)

    expected_version = body_1.get('version')
    if expected_version is None:
        return build_response(400, {"error": "version is required in body for optimistic concurrency"})

    category_name = str(body_1.get('name', ''))
    if not category_name:
        return build_response(400, {"error": "category name is required"})

    rules_in = body_1.get('rules', [])

    category_id = body_1.get('category_id') or str(uuid.uuid4())

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

    category_item = {
        'M': {
            'category_id': {'S': category_id},
            'name': {'S': category_name},
            'rules': {'L': rules_dynamo},
        }
    }

    now = int(time.time())

    try:
        response = dynamodb.update_item(
            TableName=workflows_table_name,
            Key={
                'PK': {'S': f'WORKFLOW#{workflow_id}'},
                'SK': {'S': 'META'},
            },
            UpdateExpression=(
                "SET definition.categories = list_append(definition.categories, :c), "
                "version = version + :one, "
                "updated_at = :now"
            ),
            ConditionExpression='attribute_exists(PK) AND version = :v',
            ExpressionAttributeValues={
                ':c': {'L': [category_item]},
                ':one': {'N': '1'},
                ':now': {'N': str(now)},
                ':v': {'N': str(int(expected_version))},
            },
            ReturnValues='ALL_NEW',
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print("Version mismatch or workflow missing")
        return build_response(409, {"error": "version mismatch or workflow not found"})
    except Exception as e:
        print(f"Error adding category: {str(e)}")
        return build_response(500, {"error": f"Failed to add category: {str(e)}"})

    new_version = int(response['Attributes']['version']['N'])
    print(f"Added category {category_id} to workflow {workflow_id}, new version {new_version}")

    return build_response(201, {
        "workflow_id": workflow_id,
        "category_id": category_id,
        "version": new_version,
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
