import json
import boto3
import os

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

    try:
        dynamodb.delete_item(
            TableName=workflows_table_name,
            Key={
                'PK': {'S': f'WORKFLOW#{workflow_id}'},
                'SK': {'S': 'META'},
            },
            ConditionExpression='attribute_exists(PK)',
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print(f"Workflow {workflow_id} does not exist")
        return build_response(404, {"error": f"workflow {workflow_id} not found"})
    except Exception as e:
        print(f"Error deleting workflow: {str(e)}")
        return build_response(500, {"error": f"Failed to delete workflow: {str(e)}"})

    print(f"Deleted workflow {workflow_id}")

    return build_response(200, {
        "workflow_id": workflow_id,
        "deleted": True,
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
