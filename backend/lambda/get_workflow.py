import json
import boto3
import os

workflows_table_name = os.environ['WORKFLOWS_TABLE_NAME']
aws_region = os.environ['DEPLOYMENT_REGION']

dynamodb = boto3.client("dynamodb", region_name=aws_region)


def handler(event, context):

    path_params = event.get('pathParameters') or {}
    workflow_id = path_params.get('id')
    print(f"workflow_id: {workflow_id}")

    if not workflow_id:
        return build_response(400, {"error": "workflow id is required in path"})

    try:
        dynamo_get_item_response = dynamodb.get_item(
            TableName=workflows_table_name,
            Key={
                'PK': {'S': f'WORKFLOW#{workflow_id}'},
                'SK': {'S': 'META'},
            }
        )
    except Exception as e:
        print(f"Error getting workflow: {str(e)}")
        return build_response(500, {"error": "Failed to get workflow"})

    print("*************** -- dynamo_get_item_response -- ********************* \n")
    print("************************************ \n")

    item = dynamo_get_item_response.get('Item')

    if not item:
        return build_response(404, {"error": f"workflow {workflow_id} not found"})

    return build_response(200, ddb_item_to_plain(item))


def ddb_item_to_plain(item):
    out = {}
    for k, v in item.items():
        out[k] = ddb_value_to_plain(v)
    return out


def ddb_value_to_plain(v):
    if 'S' in v:
        return v['S']
    if 'N' in v:
        n = v['N']
        try:
            if '.' in n:
                return float(n)
            return int(n)
        except Exception:
            return n
    if 'BOOL' in v:
        return v['BOOL']
    if 'NULL' in v:
        return None
    if 'L' in v:
        return [ddb_value_to_plain(x) for x in v['L']]
    if 'M' in v:
        return {mk: ddb_value_to_plain(mv) for mk, mv in v['M'].items()}
    if 'SS' in v:
        return list(v['SS'])
    if 'NS' in v:
        return [float(x) if '.' in x else int(x) for x in v['NS']]
    return v


def build_response(status_code, body):

    return {
        'statusCode': status_code,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }
