# Case orchestrator runtime

One WebSocket connection represents a case. Its Deep Agent orchestrator delegates category checks to evaluators and streams progress and rule/category findings. The runtime reads configured workflows from DynamoDB, documents from S3, and uses Bedrock-backed tools.

See ../../docs/SETUP.md and .env.example. Docker Compose is a live AWS development configuration, not an offline fixture demo. No cloud credentials are bundled. Python package versions are not fully locked; live runtime compatibility was not exercised during public-copy preparation.
