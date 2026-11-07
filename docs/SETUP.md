# Configuration and architecture

The frontend calls two API Gateway base URLs: workflow/case CRUD and uploads, plus the AgentCore WebSocket pre-sign endpoint. Files are stored in S3, workflow/case metadata in DynamoDB, and agent checkpoints in a separate S3 bucket. A case-level orchestrator creates category evaluator subagents and streams structured progress/findings to the browser.

## Configuration templates

- `frontend/.env.local.example`: public API base URLs only. Never put AWS keys in `NEXT_PUBLIC_*` variables.
- `backend/.env.example`: your account, region, and desired Bedrock model ID for the CDK app.
- `backend/runtime/.env.example`: runtime table/bucket names, model, limits, and optional tracing configuration.

Use your usual local AWS credential provider. No account configuration or credential is supplied by this repository. The runtime's Docker Compose file mounts the user's local AWS configuration read-only; running it can access real AWS APIs and incur model charges.

## Regenerating the Lambda layer

The repository omits the original vendored SDK tree. From the root, run `python3 scripts/build_layer.py` to install the recorded SDK versions into the ignored `backend/lambda-layer-agentcore/python/` folder. The script targets Python 3.12 x86_64, matching the pre-sign Lambda's default architecture. It requires network access and an empty output folder. Generated packages are not committed.

The AgentCore runtime container itself targets ARM64; its Dockerfile installs its own dependencies. These are different artifacts.

## Preparing infrastructure

From `backend/`, `npm ci` and `npm run build` validate TypeScript without deploying. Full CDK synthesis can build the AgentCore container and needs Docker and the generated layer. Review the templates and your AWS environment before any manual `cdk bootstrap`/`cdk deploy`. Those cloud actions were not performed during public-copy preparation.

The base-stack offline tests synthesize only workflow/storage/API resources using local CDK assertions; they do not instantiate the AgentCore container or contact AWS.

## Prototype limits

- REST endpoints currently lack application authentication and tenant authorization. User/owner IDs in payloads are not an access-control boundary.
- CORS permits broad origins, AgentCore/model permissions still include broad scopes, and some CDK resources retain destructive removal policies.
- Model output may be wrong or influenced by uploaded documents. Treat findings as review assistance, not automatic compliance decisions.
- Full live integration and runtime Python dependency compatibility require testing in your own configured environment. Python runtime dependencies are not fully locked.
- Local frontend preview does not fake successful agent execution when AWS is absent.
