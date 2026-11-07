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
    category_id = path_params.get('catId')
    print(f"workflow_id: {workflow_id}")
    print(f"category_id: {category_id}")

    if not workflow_id or not category_id:
        return build_response(400, {"error": "workflow id and category id are required in path"})

    body = json.loads(event['body'])
    body_1 = body
    print(body_1)

    expected_version = body_1.get('version')
    if expected_version is None:
        return build_response(400, {"error": "version is required in body for optimistic concurrency"})

    rule_name = str(body_1.get('name', ''))
    if not rule_name:
        return build_response(400, {"error": "rule name is required"})

    rule_config = body_1.get('config', {})
    rule_id = body_1.get('rule_id') or str(uuid.uuid4())

    rule_item = {
        'M': {
            'rule_id': {'S': rule_id},
            'name': {'S': rule_name},
            'config': {'S': json.dumps(rule_config)},
        }
    }

    category_index, current_version = find_category_index(workflow_id, category_id)
    if category_index is None:
        return build_response(404, {"error": f"category {category_id} not found in workflow {workflow_id}"})

    if int(expected_version) != current_version:
        return build_response(409, {"error": "version mismatch"})

    now = int(time.time())

    try:
        response = dynamodb.update_item(
            TableName=workflows_table_name,
            Key={
                'PK': {'S': f'WORKFLOW#{workflow_id}'},
                'SK': {'S': 'META'},
            },
            UpdateExpression=(
                "SET definition.categories[" + str(category_index) + "].rules = "
                "list_append(definition.categories[" + str(category_index) + "].rules, :r), "
                "version = version + :one, "
                "updated_at = :now"
            ),
            ConditionExpression='attribute_exists(PK) AND version = :v',
            ExpressionAttributeValues={
                ':r': {'L': [rule_item]},
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
        print(f"Error adding rule: {str(e)}")
        return build_response(500, {"error": f"Failed to add rule: {str(e)}"})

    new_version = int(response['Attributes']['version']['N'])
    print(f"Added rule {rule_id} to category {category_id} in workflow {workflow_id}, new version {new_version}")

    return build_response(201, {
        "workflow_id": workflow_id,
        "category_id": category_id,
        "rule_id": rule_id,
        "version": new_version,
    })


def find_category_index(workflow_id, category_id):
    response = dynamodb.get_item(
        TableName=workflows_table_name,
        Key={
            'PK': {'S': f'WORKFLOW#{workflow_id}'},
            'SK': {'S': 'META'},
        },
    )
    item = response.get('Item')
    if not item:
        return None, None

    current_version = int(item['version']['N'])

    categories = item.get('definition', {}).get('M', {}).get('categories', {}).get('L', [])
    for i, cat in enumerate(categories):
        cat_m = cat.get('M', {})
        if cat_m.get('category_id', {}).get('S') == category_id:
            return i, current_version

    return None, current_version


def build_response(status_code, body):

    return {
        'statusCode': status_code,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }
