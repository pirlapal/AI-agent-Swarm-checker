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

    new_name = body_1.get('name')
    new_definition = body_1.get('definition')

    if new_name is None and new_definition is None:
        return build_response(400, {"error": "at least one of name or definition must be provided"})

    now = int(time.time())

    update_expr_parts = [
        "version = version + :one",
        "updated_at = :now",
    ]
    expr_attr_values = {
        ':one': {'N': '1'},
        ':now': {'N': str(now)},
        ':v': {'N': str(int(expected_version))},
    }
    expr_attr_names = {}

    if new_name is not None:
        update_expr_parts.append("#n = :name")
        expr_attr_names['#n'] = 'name'
        expr_attr_values[':name'] = {'S': str(new_name)}

    if new_definition is not None:
        categories_in = new_definition.get('categories', [])
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

        update_expr_parts.append("definition = :def")
        expr_attr_values[':def'] = {
            'M': {
                'categories': {'L': categories_dynamo},
            }
        }

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
        print(f"Error updating workflow: {str(e)}")
        return build_response(500, {"error": f"Failed to update workflow: {str(e)}"})

    new_version = int(response['Attributes']['version']['N'])
    print(f"Updated workflow {workflow_id} to version {new_version}")

    return build_response(200, {
        "workflow_id": workflow_id,
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
