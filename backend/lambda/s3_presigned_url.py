import json
import boto3
import os
import time

workflows_table_name = os.environ['WORKFLOWS_TABLE_NAME']
assets_bucket_name = os.environ['ASSETS_BUCKET_NAME']
aws_region = os.environ['DEPLOYMENT_REGION']

print(f"AWS Region: {aws_region}")

s3_client = boto3.client(
    's3',
    region_name=aws_region,
    endpoint_url=f'https://s3.{aws_region}.amazonaws.com'
)
dynamodb = boto3.client("dynamodb", region_name=aws_region)


def handler(event, context):
    print(event)
    print(json.dumps(event))

    body = json.loads(event['body'])

    body_1 = body
    print(body_1)

    workflow_id = body_1['workflow-id']
    print(workflow_id)

    kind = body_1.get('kind', 'ref')
    print(f"kind: {kind}")

    if kind not in ('case', 'ref'):
        return build_response(400, {"error": f"invalid kind '{kind}', must be 'case' or 'ref'"})

    name_of_files = body_1['name-of-files']
    print(name_of_files)

    case_id = body_1.get('case-id')
    category_id = body_1.get('category-id')
    print(f"case_id: {case_id}")
    print(f"category_id: {category_id}")

    prefix = 'cases' if kind == 'case' else 'refs'

    urls_list = []

    for i in range(len(name_of_files)):

        if kind == 'case' and case_id:
            object_Id = f"cases/{workflow_id}/{case_id}/{name_of_files[i]}"
        elif kind == 'ref' and category_id:
            object_Id = f"refs/{workflow_id}/{category_id}/{name_of_files[i]}"
        else:
            object_Id = f"{prefix}/{workflow_id}/{name_of_files[i]}"

        pre_response_val = s3_client.generate_presigned_post(
            Bucket=assets_bucket_name,
            Key=object_Id,
            ExpiresIn=600
        )
        print("************************************")
        print(pre_response_val)
        print("presigned URL Generated")
        print("************************************")

        urls_list.append(
            {
                "object_Id": object_Id,
                "url": pre_response_val
            }
        )

    print("************************************\n")
    print(urls_list)
    print("************************************\n")

    try:
        dynamodb.update_item(
            TableName=workflows_table_name,
            Key={
                'PK': {'S': f'WORKFLOW#{workflow_id}'},
                'SK': {'S': 'META'},
            },
            UpdateExpression=(
                "SET last_upload_kind = :k, "
                "last_upload_ts = :now, "
                "last_upload_count = :n"
            ),
            ExpressionAttributeValues={
                ':k': {'S': kind},
                ':now': {'N': str(int(time.time()))},
                ':n': {'N': str(len(name_of_files))},
            },
        )
        print("Registered upload intent on workflow item")
    except Exception as e:
        print(f"Error registering upload intent in DynamoDB: {str(e)}")

    return build_response(200, urls_list)


def build_response(status_code, body):

    return {
        'statusCode': status_code,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }
