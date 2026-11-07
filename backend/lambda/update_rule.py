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
    rule_id = path_params.get('ruleId')
    print(f"workflow_id: {workflow_id}")
    print(f"category_id: {category_id}")
    print(f"rule_id: {rule_id}")

    if not workflow_id or not category_id or not rule_id:
        return build_response(400, {"error": "workflow id, category id, and rule id are required in path"})

    body = json.loads(event['body'])
    body_1 = body
    print(body_1)

    expected_version = body_1.get('version')
    if expected_version is None:
        return build_response(400, {"error": "version is required in body for optimistic concurrency"})

    new_name = body_1.get('name')
    new_config = body_1.get('config')

    if new_name is None and new_config is None:
        return build_response(400, {"error": "at least one of name or config must be provided"})

    indexes, current_version = find_rule_indexes(workflow_id, category_id, rule_id)
    if indexes is None:
        return build_response(404, {"error": f"rule {rule_id} not found in category {category_id}"})

    if int(expected_version) != current_version:
        return build_response(409, {"error": "version mismatch"})

    category_index, rule_index = indexes

    rule_path = f"definition.categories[{category_index}].rules[{rule_index}]"

    update_expr_parts = [
        "version = version + :one",
        "updated_at = :now",
    ]
    expr_attr_values = {
        ':one': {'N': '1'},
        ':now': {'N': str(int(time.time()))},
        ':v': {'N': str(int(expected_version))},
    }
    expr_attr_names = {}

    if new_name is not None:
        update_expr_parts.append(f"{rule_path}.#n = :name")
        expr_attr_names['#n'] = 'name'
        expr_attr_values[':name'] = {'S': str(new_name)}

    if new_config is not None:
        update_expr_parts.append(f"{rule_path}.config = :cfg")
        expr_attr_values[':cfg'] = {'S': json.dumps(new_config)}

    update_expression = "SET " + ", ".join(update_expr_parts)

    update_kwargs = {
        'TableName': workflows_table_name,
        'Key': {
            'PK': {'S': f'WORKFLOW#{workflow_id}'},
            'SK': {'S': 'META'},
        },
        'UpdateExpression': update_expression,
        'ConditionExpression': 'attribute_exists(PK) AND version = :v',
        'ExpressionAttributeValues': expr_attr_values,
        'ReturnValues': 'ALL_NEW',
    }
    if expr_attr_names:
        update_kwargs['ExpressionAttributeNames'] = expr_attr_names

    print("*************** -- update_kwargs -- ********************* \n")
    print(update_kwargs)
    print("************************************ \n")

    try:
        response = dynamodb.update_item(**update_kwargs)
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print("Version mismatch or workflow missing")
        return build_response(409, {"error": "version mismatch or workflow not found"})
    except Exception as e:
        print(f"Error updating rule: {str(e)}")
        return build_response(500, {"error": f"Failed to update rule: {str(e)}"})

    new_version = int(response['Attributes']['version']['N'])
    print(f"Updated rule {rule_id} in workflow {workflow_id}, new version {new_version}")

    return build_response(200, {
        "workflow_id": workflow_id,
        "category_id": category_id,
        "rule_id": rule_id,
        "version": new_version,
    })


def find_rule_indexes(workflow_id, category_id, rule_id):
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
        if cat_m.get('category_id', {}).get('S') != category_id:
            continue
        rules = cat_m.get('rules', {}).get('L', [])
        for j, r in enumerate(rules):
            r_m = r.get('M', {})
            if r_m.get('rule_id', {}).get('S') == rule_id:
                return (i, j), current_version
        return None, current_version

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
