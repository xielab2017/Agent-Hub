# Design

## Boundaries

Agent Hub owns endpoint configuration, secrets, approvals, manifests, plans, project mappings, orchestration and artifacts. EMP owns authenticated project/session/job state and scientific computation. R Direct is a separate adapter implementing the same constrained operation interface.

## Contracts

- `EmpEndpoint`: stable endpoint ID, mode, configured origin, token environment name and TLS policy.
- `UploadApproval`: endpoint, manifest fingerprint, file count/bytes, data policy, approver and expiry.
- `AnalysisPlan 1.1`: workflow, manifest fingerprints, typed steps, dependencies and adapter mode.
- `EmpProject`: Hub project/session links, endpoint-scoped EMP sessions, runs and provenance.
- `RunnerResult`: status, structured data, artifacts, logs and version metadata shared by HTTP and R Direct adapters.

## Security

Remote URLs come only from settings, production remote HTTP is rejected, redirects are disabled, tokens stay in secrets/environment, uploads are streamed from allowed roots, restricted policy is denied, and all remote records bind endpoint + Hub session. R Direct accepts operation IDs and JSON only.

## Rollout

Feature flags remain independent: remote, multi-workflow and R Direct default off. Existing local 16S remains usable. Each adapter can be disabled without invalidating stored manifests/artifacts.
