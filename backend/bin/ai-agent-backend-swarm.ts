#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AiAgentBackendSwarmStack } from "../lib/ai-agent-backend-swarm-stack";
import { SwarmAgentCoreStack } from "../lib/swarm-agentcore-stack";


require("dotenv").config({ override: true });

if (!process.env.AWS_REGION) {
  throw new Error(
    "AWS_REGION is not set in .env file. Deployment cannot proceed.",
  );
}
if (!process.env.AWS_ACCOUNT) {
  throw new Error(
    "AWS_ACCOUNT is not set in .env file. Deployment cannot proceed.",
  );
}

const envDev = {
  account: process.env.AWS_ACCOUNT,
  region: process.env.AWS_REGION,
};


const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

const baseStack = new AiAgentBackendSwarmStack(app, "AiAgentBackendSwarmStack", {
  env: envDev,
});

new SwarmAgentCoreStack(app, "SwarmAgentCoreStack", {
  env: envDev,
  workflowsTable: baseStack.workflowsTable,
  assetsBucket: baseStack.assetsBucket,
  bedrockModelId: process.env.BEDROCK_MODEL_ID,
});
