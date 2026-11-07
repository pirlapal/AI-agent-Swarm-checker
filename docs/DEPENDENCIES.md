# Dependency review

Compatible npm updates and removal of unused tooling eliminated the high/critical advisories found during this cleanup. The final frontend audit still reports low/moderate advisories in Markdown/math/diagram rendering and lint-tool dependencies; the backend reports moderate advisories in CDK's bundled minimatch and packages depending on it.

No forced downgrade or untested override was used to conceal those remaining findings. Run `npm audit` in both frontend/ and backend/ for the current report. Review and update these dependencies before exposing the app to untrusted document/model output. This is not a full security assessment.

Python runtime dependency resolution is not fully locked or audited in this edition. The layer requirements record versions found in the original bundle, not a guarantee that they are current or vulnerability-free. Offline Python tests replace boto3 and do not import or invoke the model runtime.
