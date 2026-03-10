# Maintainer Launch Plan (Draft) — 2026-03-09

Status: drafted, then put on hold pending agent-plans review.

## Objective
Take Maintainer from prototype (~40% readiness) to launch-ready MVP with safe operations behavior.

## Day 1 (build core launch blockers)

### Block A — Config externalization (2-3h)
- Add `maintainer/config.yaml` (service names, intervals, thresholds, enabled modules)
- Add env overrides for sensitive/runtime fields
- Remove hardcoded constants from `main.py`
- Validation: startup fails fast on invalid config

### Block B — Alerting sink (2h)
- Add webhook notifier (primary) with severity + module metadata
- Add dedupe/cooldown for repeated alerts
- Validation: simulated warn/critical sends structured alert payloads

### Block C — Remediation guardrails (1.5-2h)
- Add cooldown + max retry counters for restart actions
- Add `dry_run` mode (default true for first deploy)
- Validation: process failure does not loop restart indefinitely

### Block D — Sentinel-aware probes (1.5h)
- Add checks for Sentinel `/healthz`, scrape-up signal, and optional p95/p99 threshold breach
- Validation: synthetic failure triggers warn/critical correctly

## Day 2 (production packaging + confidence)

### Block E — Tests + failure drills (2-3h)
- Unit tests for config parsing, thresholds, dedupe, remediation cooldowns
- Failure simulation scripts for process down, high RAM/swap, scrape down

### Block F — Service packaging (1.5h)
- systemd unit file
- startup/shutdown docs
- state/log file paths + permissions

### Block G — Runbook + rollback (1-1.5h)
- operator quickstart
- alert interpretation table
- rollback checklist (disable remediation, revert config, restart service)

## Definition of Done (MVP)
- Config-driven behavior, no critical hardcoded knobs
- At least one alert sink with dedupe
- Remediation has cooldown/retry/dry-run controls
- Sentinel-aware checks active
- Test evidence + failure drill evidence recorded
- systemd deploy docs + rollback steps present

## Hold state
This plan is intentionally paused after drafting. Next execution begins only after explicit go-ahead following agent-plans review.
