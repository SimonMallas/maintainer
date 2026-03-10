# Extended Live Report — 2026-03-10

## Run summary
- Target window: 30 minutes
- Profile: `gpu,memory,disk,config_drift,sentinel_probe`
- Mode: controlled live run, remediation path not active in this profile
- Log file: `extended_live_2026-03-10.jsonl`

## Results snapshot
- Total module log lines: 255
- Status counts: `ok=255` (no `warn`, no `critical`, no `error`)
- Module counts:
  - gpu: 90
  - memory: 60
  - disk: 30
  - config_drift: 15
  - sentinel_probe: 60

## Sentinel probe result
- `/healthz` checks remained healthy (HTTP 200 in sampled entries)
- Prom metrics check remained healthy (`process_start_time_seconds` matched and above threshold)

## Webhook capture
- Captured lines: 0
- Expected in this window because no alert statuses were produced.

## Verdict
- **GO (controlled profile)**
- Maintainer is stable for this host profile under extended live run.

## Remaining optional hardening
1) Add process-check host profile for non-systemd environments (or disable process module by profile default).
2) Add one forced alert drill during live run to verify webhook path under non-OK condition in the same window.
