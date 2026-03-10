# Maintainer Launch Readiness Checklist — 2026-03-10

## Pre-launch config
- [x] Confirm host profile (`desktop-local` controlled profile selected)
- [x] Set `alert_sink.webhook_url` (validated in smoke/drill runs)
- [x] Confirm `sentinel_probe.health_url`
- [x] Confirm `sentinel_probe.prom_url` + `prom_match`
- [x] Confirm remediation policy (`dry_run` true for controlled launch stage)

## Service setup
- [x] Adjust `maintainer/deploy/maintainer.service` placeholders documented and ready for target host
  - [x] User/Group (placeholder documented)
  - [x] WorkingDirectory (placeholder documented)
  - [x] ExecStart path (placeholder documented)
- [ ] Install + daemon-reload + enable service (deferred to target-host launch step)
- [ ] Confirm service status healthy (deferred to target-host launch step)

## Validation gates
- [x] Drill script pass (`drill_sentinel_checks.py`)
- [x] Webhook smoke pass (`tools/webhook_smoke.py`)
- [x] Extended live run pass (no unexplained warn/critical)
- [x] Forced-alert drill pass (alert captured end-to-end)
- [x] 10-minute sign-off soak pass (`SIGNOFF_SOAK_REPORT_2026-03-10.md`)

## Go/No-Go
- [x] GO (controlled launch profile)
- [ ] NO-GO (with blocker list)

## Blockers (if any)
- No blockers for controlled launch profile.
- Target-host systemd install/enable remains an execution step, not a design blocker.
