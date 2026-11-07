import json
import boto3
import os
import base64

workflows_table_name = os.environ['WORKFLOWS_TABLE_NAME']
aws_region = os.environ['DEPLOYMENT_REGION']

dynamodb = boto3.client("dynamodb", region_name=aws_region)


def handler(event, context):
    print(event)
    print(json.dumps(event))

    query = event.get('queryStringParameters') or {}
    owner_id = query.get('owner-id', 'default')
    limit = int(query.get('limit', '25'))
    next_token = query.get('next-token')

    print(f"owner_id: {owner_id}")
    print(f"limit: {limit}")
    print(f"next_token: {next_token}")

    query_kwargs = {
        'TableName': workflows_table_name,
        'IndexName': 'GSI1',
        'KeyConditionExpression': 'GSI1PK = :pk',
        'ExpressionAttributeValues': {
            ':pk': {'S': f'OWNER#{owner_id}'},
        },
        'Limit': limit,
        'ScanIndexForward': False,
    }

    if next_token:
        try:
            exclusive_start = json.loads(base64.b64decode(next_token.encode('utf-8')).decode('utf-8'))
            query_kwargs['ExclusiveStartKey'] = exclusive_start
        except Exception as e:
            print(f"Bad next-token: {str(e)}")
            return build_response(400, {"error": "invalid next-token"})

    try:
        response = dynamodb.query(**query_kwargs)
    except Exception as e:
        print(f"Error listing workflows: {str(e)}")
        return build_response(500, {"error": f"Failed to list workflows: {str(e)}"})

    print("*************** -- query response -- ********************* \n")
    print(response)
    print("************************************ \n")

    items = [ddb_item_to_plain(i) for i in response.get('Items', [])]

    last_evaluated_key = response.get('LastEvaluatedKey')
    out_next_token = None
    if last_evaluated_key:
        out_next_token = base64.b64encode(
            json.dumps(last_evaluated_key).encode('utf-8')
        ).decode('utf-8')

    return build_response(200, {
        "items": items,
        "count": len(items),
        "next_token": out_next_token,
    })


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
