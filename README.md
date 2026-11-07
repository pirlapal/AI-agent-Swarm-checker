# PlanAI — AI Agent Swarm Checker

A **Kiro Spark Challenge** hackathon prototype co-created by **Pranav Kishor Irlapale ([@pirlapal](https://github.com/pirlapal))** and **[@loveneetsingh7](https://github.com/loveneetsingh7)**.

PlanAI connects a configurable document-review UI to an AWS-backed case orchestrator. Define categories and rules, attach case/reference documents, and follow agent progress and structured findings in a WebSocket-driven interface.

This public edition is derived from [the original shared repository](https://github.com/loveneetsingh7/AI-agent-Swarm-checker), which may require access. Both collaborators retain credit. The public-copy commit records publication and cleanup under Pranav's GitHub identity; it does not reconstruct or reassign historical commits.

## Implemented parts

- **Next.js / React / TypeScript frontend:** workflow creation/editing, rule/category configuration, case document inputs, run history, and streamed progress views.
- **AWS CDK infrastructure:** Lambda/API Gateway endpoints, DynamoDB workflow/case records, S3 assets, and a Bedrock AgentCore runtime definition.
- **Python agent runtime:** a case orchestrator with category-focused evaluators, document analysis/cataloging tools, checkpoint storage, and streamed findings such as `PASS`, `FAIL`, and `NEEDS_REVIEW`.

The current protocol uses **one WebSocket per case**; the orchestrator delegates category work internally. Earlier per-category connection descriptions were stale. The code includes model-backed execution; it has not been validated for accuracy, throughput, cost, or a particular number of concurrent agents.

## Local UI preview

Use Node.js 22+ (the frontend build was also exercised locally with Node 20.19.6).

```sh
git clone https://github.com/pirlapal/AI-agent-Swarm-checker.git
cd AI-agent-Swarm-checker/frontend
npm ci
npm run dev
```

Open **http://localhost:3000**. The landing page and editors can be explored locally. **This is not an offline agent demo:** saving workflows and running reviews require the AWS APIs and configured environment URLs. Missing configuration produces an explicit error. No production endpoints or account credentials are included.

```sh
cp .env.local.example .env.local
# Configure NEXT_PUBLIC_API_BASE_URL and NEXT_PUBLIC_WS_PRESIGN_API_BASE_URL
# from your own deployment outputs, then restart the frontend.
```

Fonts are self-hosted with their licenses, so production builds do not fetch Google Fonts.

## Local checks

```sh
# All commands from the repository root
npm --prefix frontend ci
npm --prefix frontend run build
python3 -m unittest discover -s tests -v
python3 -m compileall -q backend/lambda backend/runtime
npm --prefix backend ci
npm --prefix backend test
```

Eight Python Lambda contract tests and four infrastructure tests were added for this edition. The old infrastructure test contained only a commented-out assertion and did not validate a queue. Cloud-dependent scripts referencing missing private PDF fixtures are excluded. No live AWS/Bedrock test or hosted CI pass is claimed.

## Optional AWS setup

See [configuration and architecture](docs/SETUP.md). Cloud execution needs your own AWS account, Bedrock model access, storage, and deployment configuration. The full AgentCore stack builds an ARM64 container and may incur cloud charges if deployed. Nothing is deployed by cloning, installing dependencies, building TypeScript, or running the offline checks.

This remains a hackathon prototype. The API does not implement user authentication or tenant authorization. Restrict access before using real documents; review the remaining IAM scope, CORS, deletion policies, model output handling, and cost limits. Do not expose it as a public document-review service in its current form. Findings require human review and are not compliance guarantees.

## Structure

```text
frontend/                  Next.js app and its used UI components
backend/bin, backend/lib/  CDK application and stacks
backend/lambda/            Workflow, category, rule, upload, case APIs
backend/runtime/           Python orchestrator, tools, prompts, storage
backend/lambda-layer-agentcore/  Requirements for generated presigner SDK layer
tests/                     Offline Lambda contract tests
scripts/build_layer.py     Rebuild the ignored SDK layer
docs/                     Setup, cleanup inventory, dependency limitations
```

See [AUTHORS.md](AUTHORS.md), [NOTICE](NOTICE), [cleanup notes](docs/PUBLIC_COPY.md), and [dependency review](docs/DEPENDENCIES.md). No blanket software license was present upstream, so none is invented here.
