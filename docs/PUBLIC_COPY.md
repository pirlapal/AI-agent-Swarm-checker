# Public-copy cleanup

The source repository is unchanged. This public edition uses fresh Git history and preserves joint project credit.

## Removed or replaced

- Vendored Lambda SDK packages and bytecode, __pycache__, .DS_Store, placeholder files, agent skill-installation metadata, and original Git history.
- 56 disconnected frontend template components and nine unused direct dependencies identified from route-rooted import traversal. The shadcn CLI dependency was also removed; its used stylesheet and license were retained locally.
- Cloud-only scratch test scripts dependent on missing private PDF fixtures.
- Template READMEs and a no-op infrastructure test.
- Unsupported landing-page claims of 90% time reduction, 1000+ agents, and measured execution speed.

## Retained and improved

- Workflow editor/run frontend, backend CRUD/upload/case handlers, AgentCore runtime, prompts, checkpoint/storage helpers, and CDK definitions.
- Flattened frontend and backend folders; runtime references updated.
- Self-hosted original fonts with licenses; production build uses webpack for compatibility with the validation environment.
- Updated frontend Next.js and compatible dependencies; documented remaining low/moderate dependency advisories.
- Base-stack data access grants scoped to its table and bucket, replacing service-wide wildcard policies. This does not finish production authorization hardening.
- AgentCore debug disabled; create/get workflow handlers omit whole-payload logging and genericize returned SDK failures. Other handlers still need a privacy/error-handling review.
- Workflow-create input validation and offline tests for real data serialization and failure paths.
- Recorded layer dependency versions and a script to regenerate packages rather than publish them.

The UI brand remains PlanAI. Public availability does not assert production readiness, successful cloud deployment, validated model quality, or individual ownership of all original code.
