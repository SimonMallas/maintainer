# Maintainer Roadmap

Status: **Maintainer v1 foundation complete** (2026-03-10).

Reference plan and execution evidence:
- `LAUNCH_PLAN_2026-03-09.md`
- `DRILL_REPORT_2026-03-10.md`
- `LIVE_TEST_2026-03-10.md`
- `EXTENDED_LIVE_REPORT_2026-03-10.md`

## Why this sequence
Running Sentinel burn-in and Maintainer hardening simultaneously would blur root cause and reduce signal quality.

## Phase 1 — Baseline hardening
- Externalize config (thresholds, service names, intervals)
- Add structured alert sinks (webhook/Telegram/Discord)
- Add remediation safeguards (cooldown, retry caps, dry-run mode)

## Phase 2 — Integration with Sentinel Control Plane
- Add Sentinel-aware health probes and metrics checks
- Add burn-in compatible alert profiles
- Add minimal runbook docs for operator handoff

## Phase 3 — Production readiness
- systemd unit + startup docs
- test plan (module checks + failure simulations)
- release checklist + rollback plan

## Definition of done (v1)
- deterministic config-driven behavior
- alerting + remediation evidence
- documented deployment + operator runbook
