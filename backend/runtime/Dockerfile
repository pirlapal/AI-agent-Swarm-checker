# Swarm AgentCore Dockerfile
#
# BedrockAgentCoreApp with @app.websocket + @app.ping for the swarm case
# runner. Each WebSocket connection creates a Deep Agent scoped to one
# (workflow_id, case_id, category_id).
#
# Platform: linux/arm64 (AgentCore Runtime requires ARM64).
# Build is done by CDK (`agentcore.AgentRuntimeArtifact.fromAsset(...)`),
# so no lock file is committed -- pip resolves deps at build time.

FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install \
      "deepagents>=0.5.3" \
      "langchain>=1.2.15,<2.0.0" \
      "langgraph>=1.0.6" \
      "langchain-aws>=0.2.0" \
      "langgraph-checkpoint-aws>=1.0.2" \
      "bedrock-agentcore>=0.1.0" \
      "boto3>=1.35.0" \
      "pydantic>=2.9.0" \
      "langsmith>=0.1.0" \
      "aws-opentelemetry-distro-genai-beta>=0.1.2" \
      "opentelemetry-instrumentation" \
      "websockets>=12.0" \
      "fastapi>=0.115.0" \
      "uvicorn[standard]>=0.32.0"

FROM public.ecr.aws/docker/library/python:3.12-slim AS development

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY ./agent /app/agent
COPY ./prompt /app/prompt
COPY ./checkpoint /app/checkpoint
COPY ./middleware /app/middleware
COPY ./services /app/services

RUN chmod -R 755 /app

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "agent.app"]

FROM development AS production

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

ENV CONTAINER_ENV=1
ENV PORT=8080

ENV OTEL_PYTHON_DISTRO="aws_opentelemetry_distro_genai_beta"
ENV OTEL_PYTHON_CONFIGURATOR="aws_configurator"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

CMD ["python", "-m", "agent.app"]
