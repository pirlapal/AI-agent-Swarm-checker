import json
import boto3
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

    query = event.get('queryStringParameters') or {}
    expected_version = query.get('version')
    if expected_version is None:
        return build_response(400, {"error": "version query param is required for optimistic concurrency"})

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
                "REMOVE definition.categories[" + str(category_index) + "] "
                "SET version = version + :one, updated_at = :now"
            ),
            ConditionExpression='attribute_exists(PK) AND version = :v',
            ExpressionAttributeValues={
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
        print(f"Error deleting category: {str(e)}")
        return build_response(500, {"error": f"Failed to delete category: {str(e)}"})

    new_version = int(response['Attributes']['version']['N'])
    print(f"Deleted category {category_id} in workflow {workflow_id}, new version {new_version}")

    return build_response(200, {
        "workflow_id": workflow_id,
        "category_id": category_id,
        "deleted": True,
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
