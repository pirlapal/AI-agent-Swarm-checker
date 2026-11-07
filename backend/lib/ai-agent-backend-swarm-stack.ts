import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Duration } from "aws-cdk-lib";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import { RemovalPolicy } from "aws-cdk-lib";
import * as api_gateway from "aws-cdk-lib/aws-apigateway";
import * as logs from "aws-cdk-lib/aws-logs";

export class AiAgentBackendSwarmStack extends cdk.Stack {
  public readonly apiUrl: string;
  public readonly workflowsTable: dynamodb.Table;
  public readonly assetsBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    //  ------------------- S3 assets bucket -------------------
    const s3_ai_agent_swarm_assets_source = new s3.Bucket(
      this,
      "s3_ai_agent_swarm_assets_source",
      {
        removalPolicy: RemovalPolicy.DESTROY,
      }
    );

    s3_ai_agent_swarm_assets_source.addCorsRule({
      allowedOrigins: ["*"],
      allowedMethods: [
        s3.HttpMethods.POST,
        s3.HttpMethods.PUT,
        s3.HttpMethods.GET,
        s3.HttpMethods.HEAD,
        s3.HttpMethods.DELETE,
      ],
      allowedHeaders: ["*"],
      exposedHeaders: ["ETag"],
      maxAge: 3600,
    });

    //  ------------------- DynamoDB workflows table -------------------
    const ddb_ai_agent_swarm_workflows_source = new dynamodb.Table(
      this,
      "ddb_ai_agent_swarm_workflows_source",
      {
        partitionKey: {
          name: "PK",
          type: dynamodb.AttributeType.STRING,
        },
        sortKey: {
          name: "SK",
          type: dynamodb.AttributeType.STRING,
        },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        pointInTimeRecovery: true,
        removalPolicy: RemovalPolicy.DESTROY,
      }
    );

    ddb_ai_agent_swarm_workflows_source.addGlobalSecondaryIndex({
      indexName: "GSI1",
      partitionKey: {
        name: "GSI1PK",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "GSI1SK",
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    this.workflowsTable = ddb_ai_agent_swarm_workflows_source;
    this.assetsBucket = s3_ai_agent_swarm_assets_source;

    //  ------------------- shared env for all lambdas -------------------
    const common_env = {
      WORKFLOWS_TABLE_NAME: ddb_ai_agent_swarm_workflows_source.tableName,
      ASSETS_BUCKET_NAME: s3_ai_agent_swarm_assets_source.bucketName,
      DEPLOYMENT_REGION: this.region,
    };

    //  ------------------- lambda: s3 presigned url -------------------
    const s3_presigned_url = new lambda.Function(this, "s3-presigned-url", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "s3_presigned_url.handler",
      timeout: Duration.minutes(1),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(s3_presigned_url);
    s3_ai_agent_swarm_assets_source.grantReadWrite(s3_presigned_url);

    //  ------------------- lambdas: workflow CRUD -------------------
    const create_workflow = new lambda.Function(this, "create-workflow", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "create_workflow.handler",
      timeout: Duration.minutes(1),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(create_workflow);
    s3_ai_agent_swarm_assets_source.grantReadWrite(create_workflow);

    const get_workflow = new lambda.Function(this, "get-workflow", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "get_workflow.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(get_workflow);
    s3_ai_agent_swarm_assets_source.grantReadWrite(get_workflow);

    const list_workflows = new lambda.Function(this, "list-workflows", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "list_workflows.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(list_workflows);
    s3_ai_agent_swarm_assets_source.grantReadWrite(list_workflows);

    const update_workflow = new lambda.Function(this, "update-workflow", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "update_workflow.handler",
      timeout: Duration.minutes(1),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(update_workflow);
    s3_ai_agent_swarm_assets_source.grantReadWrite(update_workflow);

    const delete_workflow = new lambda.Function(this, "delete-workflow", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "delete_workflow.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(delete_workflow);
    s3_ai_agent_swarm_assets_source.grantReadWrite(delete_workflow);

    //  ------------------- lambdas: category CRUD -------------------
    const add_category = new lambda.Function(this, "add-category", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "add_category.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(add_category);
    s3_ai_agent_swarm_assets_source.grantReadWrite(add_category);

    const update_category = new lambda.Function(this, "update-category", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "update_category.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(update_category);
    s3_ai_agent_swarm_assets_source.grantReadWrite(update_category);

    const delete_category = new lambda.Function(this, "delete-category", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "delete_category.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(delete_category);
    s3_ai_agent_swarm_assets_source.grantReadWrite(delete_category);

    //  ------------------- lambdas: rule CRUD -------------------
    const add_rule = new lambda.Function(this, "add-rule", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "add_rule.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(add_rule);
    s3_ai_agent_swarm_assets_source.grantReadWrite(add_rule);

    const update_rule = new lambda.Function(this, "update-rule", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "update_rule.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(update_rule);
    s3_ai_agent_swarm_assets_source.grantReadWrite(update_rule);

    const delete_rule = new lambda.Function(this, "delete-rule", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "delete_rule.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(delete_rule);
    s3_ai_agent_swarm_assets_source.grantReadWrite(delete_rule);

    //  ------------------- lambda: start case -------------------
    const start_case = new lambda.Function(this, "start-case", {
      runtime: lambda.Runtime.PYTHON_3_10,
      code: lambda.Code.fromAsset("lambda"),
      handler: "start_case.handler",
      timeout: Duration.seconds(30),
      environment: common_env,
    });
    ddb_ai_agent_swarm_workflows_source.grantReadWriteData(start_case);
    s3_ai_agent_swarm_assets_source.grantReadWrite(start_case);

    //  ------------------- api gateway -------------------
    const ai_agent_swarm_api = new api_gateway.RestApi(
      this,
      "ai_agent_swarm_api",
      {
        cloudWatchRole: true,
        deployOptions: {
          accessLogDestination: new api_gateway.LogGroupLogDestination(
            new logs.LogGroup(this, "ai_agent_swarm_api_log_group", {
              logGroupName: "ai_agent_swarm_api_log_group",
              retention: RetentionDays.ONE_MONTH,
              removalPolicy: RemovalPolicy.DESTROY,
            })
          ),
        },
        defaultCorsPreflightOptions: {
          allowHeaders: ["*"],
          allowOrigins: api_gateway.Cors.ALL_ORIGINS,
          allowMethods: api_gateway.Cors.ALL_METHODS,
        },
      }
    );
    this.apiUrl = ai_agent_swarm_api.url;

    //  ------------------- /uploads/presign -------------------
    const uploads_resource = ai_agent_swarm_api.root.addResource("uploads");
    const uploads_presign_resource = uploads_resource.addResource("presign");
    uploads_presign_resource.addMethod(
      "POST",
      new api_gateway.LambdaIntegration(s3_presigned_url)
    );

    //  ------------------- /workflows -------------------
    const workflows_resource = ai_agent_swarm_api.root.addResource("workflows");
    workflows_resource.addMethod(
      "POST",
      new api_gateway.LambdaIntegration(create_workflow)
    );
    workflows_resource.addMethod(
      "GET",
      new api_gateway.LambdaIntegration(list_workflows)
    );

    //  ------------------- /workflows/{id} -------------------
    const workflow_id_resource = workflows_resource.addResource("{id}");
    workflow_id_resource.addMethod(
      "GET",
      new api_gateway.LambdaIntegration(get_workflow)
    );
    workflow_id_resource.addMethod(
      "PUT",
      new api_gateway.LambdaIntegration(update_workflow)
    );
    workflow_id_resource.addMethod(
      "DELETE",
      new api_gateway.LambdaIntegration(delete_workflow)
    );

    //  ------------------- /workflows/{id}/categories -------------------
    const categories_resource = workflow_id_resource.addResource("categories");
    categories_resource.addMethod(
      "POST",
      new api_gateway.LambdaIntegration(add_category)
    );

    //  ------------------- /workflows/{id}/cases -------------------
    const cases_resource = workflow_id_resource.addResource("cases");
    cases_resource.addMethod(
      "POST",
      new api_gateway.LambdaIntegration(start_case)
    );

    //  ------------------- /workflows/{id}/categories/{catId} -------------------
    const category_id_resource = categories_resource.addResource("{catId}");
    category_id_resource.addMethod(
      "PUT",
      new api_gateway.LambdaIntegration(update_category)
    );
    category_id_resource.addMethod(
      "DELETE",
      new api_gateway.LambdaIntegration(delete_category)
    );

    //  ------------------- /workflows/{id}/categories/{catId}/rules -------------------
    const rules_resource = category_id_resource.addResource("rules");
    rules_resource.addMethod(
      "POST",
      new api_gateway.LambdaIntegration(add_rule)
    );

    //  ------------------- /workflows/{id}/categories/{catId}/rules/{ruleId} -------------------
    const rule_id_resource = rules_resource.addResource("{ruleId}");
    rule_id_resource.addMethod(
      "PUT",
      new api_gateway.LambdaIntegration(update_rule)
    );
    rule_id_resource.addMethod(
      "DELETE",
      new api_gateway.LambdaIntegration(delete_rule)
    );

    //  ------------------- outputs -------------------
    new cdk.CfnOutput(this, "S3BucketName", {
      value: s3_ai_agent_swarm_assets_source.bucketName,
      description: "S3 bucket name for workflow assets (cases/ and refs/)",
      exportName: "S3BucketName",
    });

    new cdk.CfnOutput(this, "WorkflowsTableName", {
      value: ddb_ai_agent_swarm_workflows_source.tableName,
      description: "DynamoDB table name for workflows",
      exportName: "WorkflowsTableName",
    });

    new cdk.CfnOutput(this, "ApiUrl", {
      value: this.apiUrl,
      description: "API Gateway URL",
    });
  }
}
