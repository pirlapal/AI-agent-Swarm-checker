import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as api_gateway from "aws-cdk-lib/aws-apigateway";
import * as logs from "aws-cdk-lib/aws-logs";
import { Duration, RemovalPolicy } from "aws-cdk-lib";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha";
import * as path from "path";

/**
 * Props for SwarmAgentCoreStack.
 *
 * Receives references to the existing swarm backend's workflows table and
 * assets bucket so the AgentCore execution role can be scoped to them.
 */
export interface SwarmAgentCoreStackProps extends cdk.StackProps {
  /** Workflows DynamoDB table from the base swarm stack */
  workflowsTable: dynamodb.ITable;
  /** Assets S3 bucket from the base swarm stack (cases/ and refs/) */
  assetsBucket: s3.IBucket;
  /** Bedrock model ID (inference profile ARN recommended) */
  bedrockModelId?: string;
}

/**
 * Sibling stack that runs one Deep Agent per workflow category via
 * AWS Bedrock AgentCore Runtime + WebSocket.
 *
 * Frontend opens N WebSocket connections (one per category). Each
 * connection's `start` message includes `category_id`, so the runtime
 * creates a Deep Agent scoped to only that category's rules + refs.
 *
 * Resources:
 *  - Dedicated S3 checkpoint bucket for the AgentCore Runtime
 *  - AgentCore Lambda layer (for SigV4 pre-signing)
 *  - AgentCore execution IAM role
 *  - AgentCore Runtime built from ./runtime/
 *  - Pre-sign Lambda that returns SigV4 WebSocket URLs
 *  - Dedicated API Gateway exposing POST /caseWsPresign
 */
export class SwarmAgentCoreStack extends cdk.Stack {
  public readonly agentCoreRuntimeArn: string;
  public readonly agentCoreWebSocketEndpoint: string;
  public readonly caseWsPresignUrl: string;
  public readonly checkpointBucketName: string;

  constructor(scope: Construct, id: string, props: SwarmAgentCoreStackProps) {
    super(scope, id, props);

    const backendRoot = path.join(__dirname, "..");

    const checkpoint_bucket = new s3.Bucket(
      this,
      "SwarmAgentCoreCheckpointBucket",
      {
        removalPolicy: RemovalPolicy.DESTROY,
        autoDeleteObjects: true,
        cors: [
          {
            allowedOrigins: ["*"],
            allowedMethods: [
              s3.HttpMethods.GET,
              s3.HttpMethods.PUT,
              s3.HttpMethods.POST,
              s3.HttpMethods.DELETE,
            ],
            allowedHeaders: ["*"],
            exposedHeaders: ["ETag"],
            maxAge: 3000,
          },
        ],
      },
    );
    this.checkpointBucketName = checkpoint_bucket.bucketName;

    const agentcore_layer = new lambda.LayerVersion(
      this,
      "swarm_agentcore_layer",
      {
        compatibleRuntimes: [
          lambda.Runtime.PYTHON_3_10,
          lambda.Runtime.PYTHON_3_11,
          lambda.Runtime.PYTHON_3_12,
        ],
        code: lambda.Code.fromAsset(
          path.join(backendRoot, "lambda-layer-agentcore"),
        ),
        description: "Bedrock AgentCore SDK layer (for pre-sign Lambda)",
      },
    );

    const agentCoreExecutionRole = new iam.Role(
      this,
      "SwarmAgentCoreExecutionRole",
      {
        assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        description:
          "Execution role for Swarm AgentCore Runtime (per-category Deep Agents)",
      },
    );

    agentCoreExecutionRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ],
        resources: [
          checkpoint_bucket.bucketArn,
          `${checkpoint_bucket.bucketArn}/*`,
          props.assetsBucket.bucketArn,
          `${props.assetsBucket.bucketArn}/*`,
        ],
      }),
    );

    agentCoreExecutionRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
        ],
        resources: [
          props.workflowsTable.tableArn,
          `${props.workflowsTable.tableArn}/index/*`,
        ],
      }),
    );

    agentCoreExecutionRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
          "bedrock-agentcore:*",
        ],
        resources: ["*"],
      }),
    );

    const swarmAgentArtifact = agentcore.AgentRuntimeArtifact.fromAsset(
      path.join(backendRoot, "runtime"),
      {
        platform: Platform.LINUX_ARM64,
      },
    );

    const swarmAgentCoreRuntime = new agentcore.Runtime(
      this,
      "SwarmAgentCoreRuntime",
      {
        runtimeName: "swarmCaseAgent",
        agentRuntimeArtifact: swarmAgentArtifact,
        executionRole: agentCoreExecutionRole,
        environmentVariables: {
          AWS_DEFAULT_REGION: this.region,
          CHECKPOINT_S3_BUCKET_NAME: checkpoint_bucket.bucketName,
          ASSETS_BUCKET_NAME: props.assetsBucket.bucketName,
          WORKFLOWS_TABLE_NAME: props.workflowsTable.tableName,
          AGENT_STEP_LIMIT: process.env.AGENT_STEP_LIMIT || "25",
          AGENT_RECURSION_LIMIT: process.env.AGENT_RECURSION_LIMIT || "250",
          BEDROCK_MODEL_ID:
            props.bedrockModelId ||
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
          LANGSMITH_TRACING: process.env.LANGSMITH_TRACING || "false",
          LANGSMITH_API_KEY: process.env.LANGSMITH_API_KEY || "",
          LANGSMITH_PROJECT:
            process.env.LANGSMITH_PROJECT || "swarm-case-agentcore",
        },
      },
    );

    this.agentCoreRuntimeArn = swarmAgentCoreRuntime.agentRuntimeArn;
    this.agentCoreWebSocketEndpoint = `wss://bedrock-agentcore.${this.region}.amazonaws.com/runtimes/${swarmAgentCoreRuntime.agentRuntimeArn}/ws`;

    new cdk.CfnOutput(this, "SwarmAgentCoreRuntimeARN", {
      value: swarmAgentCoreRuntime.agentRuntimeArn,
      description:
        "Swarm AgentCore Runtime ARN (one Deep Agent per category per connection)",
    });

    new cdk.CfnOutput(this, "SwarmAgentCoreWebSocketEndpoint", {
      value: this.agentCoreWebSocketEndpoint,
      description:
        "Swarm AgentCore WebSocket endpoint (IAM auth via pre-signed URLs)",
    });

    new cdk.CfnOutput(this, "SwarmAgentCoreCheckpointBucketName", {
      value: checkpoint_bucket.bucketName,
      description: "S3 bucket for AgentCore checkpoint storage",
    });

    const generate_case_ws_presigned_url_function = new lambda.Function(
      this,
      "generate_case_ws_presigned_url_function",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "generate_case_ws_presigned_url.handler",
        timeout: Duration.minutes(1),
        memorySize: 256,
        code: lambda.Code.fromAsset(path.join(backendRoot, "lambda"), {
          exclude: ["*.pyc", "__pycache__"],
        }),
        layers: [agentcore_layer],
        environment: {
          AGENT_RUNTIME_ARN: swarmAgentCoreRuntime.agentRuntimeArn,
          PRESIGNED_URL_EXPIRY_SECONDS: "300",
        },
      },
    );

    generate_case_ws_presigned_url_function.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock-agentcore:*"],
        resources: ["*"],
      }),
    );

    generate_case_ws_presigned_url_function.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        resources: ["*"],
      }),
    );

    const swarm_agentcore_api = new api_gateway.RestApi(
      this,
      "swarm_agentcore_api",
      {
        cloudWatchRole: false,
        deployOptions: {
          accessLogDestination: new api_gateway.LogGroupLogDestination(
            new logs.LogGroup(this, "swarm_agentcore_api_log_group", {
              logGroupName: "swarm_agentcore_api_log_group",
              retention: RetentionDays.ONE_MONTH,
              removalPolicy: RemovalPolicy.DESTROY,
            }),
          ),
        },
        defaultCorsPreflightOptions: {
          allowHeaders: ["*"],
          allowOrigins: api_gateway.Cors.ALL_ORIGINS,
          allowMethods: api_gateway.Cors.ALL_METHODS,
        },
      },
    );

    const case_ws_presign_integration = new api_gateway.LambdaIntegration(
      generate_case_ws_presigned_url_function,
    );
    const case_ws_presign_path =
      swarm_agentcore_api.root.addResource("caseWsPresign");
    case_ws_presign_path.addMethod("POST", case_ws_presign_integration);

    this.caseWsPresignUrl = `${swarm_agentcore_api.url}caseWsPresign`;

    new cdk.CfnOutput(this, "SwarmAgentCoreApiGatewayUrl", {
      value: swarm_agentcore_api.url,
      description: "API Gateway URL for the swarm AgentCore API",
      exportName: "SwarmAgentCoreApiUrl",
    });

    new cdk.CfnOutput(this, "CaseWsPresignEndpoint", {
      value: this.caseWsPresignUrl,
      description:
        "POST endpoint that returns a SigV4 pre-signed WebSocket URL per (workflow_id, case_id, category_id)",
    });
  }
}
