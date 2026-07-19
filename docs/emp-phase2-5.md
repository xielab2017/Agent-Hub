# EMP Phase 2-5

Agent Hub v5.0.6 extends the local EMP MVP with configured remote services,
typed multi-workflow planning, persistent joint projects, and an optional R
Direct fallback. The original local 16S route remains compatible.

## Remote EMP

Remote endpoints must be configured before use and must be HTTPS origins.
Request-time URLs are rejected. Tokens are resolved from the named environment
secret and are not returned to the browser.

```json
{
  "emp": {
    "enabled": true,
    "remote_enabled": true,
    "endpoints": [
      {
        "id": "lab-prod",
        "base_url": "https://emp.example.edu",
        "token_env": "EMP_LAB_TOKEN"
      }
    ],
    "allow_restricted_remote": false
  }
}
```

Every transfer requires a short-lived signed approval bound to the endpoint
origin, Hub session, manifest fingerprint, file count, byte count, and data
policy. Files stream from configured allowed roots. Downloads require expected
SHA-256 values. Redirects are not followed.

## Typed Plans

`POST /api/emp/plans/compile` supports capability-gated templates for:

- `microbiome_16s`
- `transcriptomics`
- `metabolomics`
- `metagenomics`
- `clinical`

Scientific parameters are validated against local JSON schemas and metadata.
Plans preserve critical parameters and input fingerprints, require explicit
confirmation, and persist per-step state. `POST /api/emp/jobs/<id>/retry`
reuses the EMP session and reruns the failed node plus its descendants.

Local and remote execution consume the same `AnalysisPlan`. Remote execution
uses `POST /api/emp/plans/<id>/run-remote` after an approved import has returned
an EMP session ID.

## Joint Projects

Projects persist multiple manifests and endpoint-scoped EMP sessions. Sample
identifiers are stored as hashes; the sample-map API reports overlap without
returning raw identifiers. Project reports contain only runs and artifacts
linked to project manifests, including checksums and interpretation boundaries.

Key routes:

- `GET|POST /api/emp/projects`
- `POST /api/emp/projects/<id>/manifests`
- `POST /api/emp/projects/<id>/sessions`
- `GET /api/emp/projects/<id>/sample-map`
- `POST /api/emp/projects/<id>/report`

This release implements result-level multi-omics integration and provenance.
It does not invent a new statistical cross-omics algorithm inside Agent Hub.

## R Direct

R Direct is disabled by default. Enable `emp.allow_r_direct` only for a trusted
local installation. The runner accepts JSON and three fixed operation IDs:

- `preflight`
- `summarize_table`
- `preview_dataset`

The preview result mirrors the local path-preview contract for dimensions,
orientation, and sample overlap. Paths must remain inside allowed roots. The
runner never calls `eval`, `parse`, `source`, or model-generated R expressions.

## Rollback

Set `emp.enabled=false` to disable all EMP integration, or independently turn
off `emp.remote_enabled` and `emp.allow_r_direct`. Existing manifests, plans,
jobs, projects, and artifacts remain on disk and are not deleted.
