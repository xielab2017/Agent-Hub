# EMP R Direct

R Direct is an optional offline adapter and is disabled by default. It executes
only fixed operation IDs through `scripts/emp_r_runner.R`; chat text and model
output are never interpreted as R code.

The first operations are `preflight`, bounded table summarization, and
`preview_dataset`, whose result mirrors the local API path-preview contract
(shape, orientation, sample-ID overlap, and warnings). Inputs are
JSON, file paths must resolve inside configured allowed roots, execution occurs
in an isolated temporary directory, and Agent Hub terminates the process group
on timeout. Statistical EMP operations should be added only as reviewed
allowlist entries with local-api parity fixtures.
