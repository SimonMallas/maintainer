# Forced Alert Drill — 2026-03-10

## Purpose
Prove webhook alert path works under real non-OK condition during live runtime.

## Method
- Started local webhook receiver on `127.0.0.1:9998`
- Ran Maintainer with only `sentinel_probe` enabled
- Forced sentinel health failure using unreachable URL:
  - `SENTINEL_HEALTH_URL=http://127.0.0.1:65535/healthz`

## Result
- Maintainer emitted `critical` for `sentinel_probe`
- Webhook capture file recorded one alert payload with:
  - `event: alert`
  - `module: sentinel_probe`
  - `status: critical`
  - expected failure message

## Evidence files
- `forced_alert_run.log`
- `forced_alert_webhook.ndjson`

## Verdict
- Alert path verified end-to-end under forced fault condition.
