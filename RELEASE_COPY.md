# Maintainer Release Copy (Final)

## Version tag recommendation
`v0.1.0-rc1`

## Positioning line (approved)
Maintainer is the runtime reliability layer for self-hosted AI systems — an ops-first AI maintainer for health checks, safe remediation, and auditable alerts.

## Short description
Maintainer continuously monitors host/runtime health, applies guarded remediation policies, and emits structured, auditable alerts. It is designed to pair with Sentinel Control Plane: Sentinel handles routing/safety decisions, Maintainer handles reliability discipline.

## Launch blurb
Maintainer `v0.1.0-rc1` is ready for controlled release.

What it does:
- config-driven health monitoring across process/GPU/memory/disk/config drift/Sentinel probes
- safe remediation controls (dry-run, cooldown, retry caps)
- structured alert sink with cooldown dedupe and recovery events
- drill tooling + webhook E2E smoke verification
- launch docs, rollback guidance, and evidence-backed validation reports

Default profile:
- `desktop-local` (safer default for mixed local environments)
- `service-host` profile documented for systemd-first hosts

Scope boundary:
- reliability-first runtime guardian
- not positioned as a full autonomous repo-coding platform

## One-liner
Sentinel decides safely. Maintainer keeps it reliable.
