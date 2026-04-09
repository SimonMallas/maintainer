# Maintainer

A host reliability daemon for OpenClaw runtime operations. Maintainer continuously checks host and service health, enforces safe remediation guardrails, and emits actionable alerts with evidence.

It works alongside Sentinel Control Plane: **Sentinel** handles capability routing/intelligence decisions, while **Maintainer** handles runtime stability, safety checks, and recovery discipline.

Current scope in `main.py`:
- service liveness checks (`systemctl is-active`)
- GPU temperature/VRAM checks (`nvidia-smi`)
- RAM/swap pressure checks (`psutil`)
- disk usage checks
- config drift hashing for selected files
- basic remediation hook (restart service on critical process failure)

## Status
All core modules are live: process, GPU, memory, disk, config drift, and Sentinel probe. Webhook alert sink with deduplication is integrated.

## Quick start
```bash
cd maintainer
python3 -m venv .venv
source .venv/bin/activate
pip install psutil
python main.py
```

## Configuration
Maintainer now loads runtime/module config from `config.json` at startup.

- Default config path: `maintainer/config.json`
- Override config path: `MAINTAINER_CONFIG_PATH=/path/to/config.json`
- Validation is fail-fast: invalid/missing fields stop startup with a clear error and exit code `2`.

### Config fields
- `runtime.state_file`: path for state JSON
- `runtime.loop_sleep_seconds`: scheduler loop sleep
- `enabled_modules`: ordered list of module names to run
- `process.service_name`, `process.interval`
- `gpu.interval`, `gpu.temp_warn`, `gpu.temp_crit`
- `memory.interval`, `memory.ram_warn`, `memory.swap_crit`
- `disk.interval`, `disk.path`, `disk.warn_pct`, `disk.crit_pct`
- `config_drift.interval`, `config_drift.files`
- `remediation.dry_run` (default `true`)
- `remediation.process_restart_cooldown_sec`
- `remediation.process_restart_max_retries`
- `remediation.process_restart_retry_window_sec`
- `alert_sink.webhook_url` (empty disables alert dispatch)
- `alert_sink.cooldown_sec` (dedupe window for repeated identical alerts)
- `alert_sink.http_timeout_sec`

### Environment overrides (key runtime fields)
- `MAINTAINER_CONFIG_PATH` — alternative config file
- `MAINTAINER_STATE_FILE` — override `runtime.state_file`
- `MAINTAINER_LOOP_SLEEP_SECONDS` — override `runtime.loop_sleep_seconds`
- `MAINTAINER_SERVICE_NAME` — override `process.service_name`
- `MAINTAINER_ENABLED_MODULES` — comma-separated module list, e.g. `process,memory,disk`
- `SENTINEL_HEALTH_URL` — Sentinel `/healthz` endpoint (empty disables check)
- `SENTINEL_PROM_URL` — Prometheus metrics endpoint for scrape-up signal
- `SENTINEL_PROM_MATCH` — metrics line substring to match (default `up{job="sentinel-control-plane"}`)
- `SENTINEL_PROM_MIN_VALUE` — minimum acceptable value for matched metric (default `1`)
- `SENTINEL_LATENCY_WARN_MS` — optional RTT warning threshold in ms (`0` disables)
- `SENTINEL_HTTP_TIMEOUT_SEC` — HTTP timeout for probe calls (default `3`)
- `MAINTAINER_ALERT_WEBHOOK_URL` — override `alert_sink.webhook_url`
- `MAINTAINER_ALERT_COOLDOWN_SEC` — override `alert_sink.cooldown_sec`
- `MAINTAINER_ALERT_HTTP_TIMEOUT_SEC` — override `alert_sink.http_timeout_sec`

## Current architecture
- `MaintainerModule` base class with `interval` + async `run()`
- scheduler loop runs modules by interval and records JSON state
- state file default: `maintainer_state.json` (configurable)
- module output: JSON lines to stdout for easy piping/indexing

## Modules (current)
- `process` — checks configured systemd service name
- `gpu` — checks temp + VRAM usage if NVIDIA GPU present
- `memory` — checks RAM and swap usage
- `disk` — checks configured disk path usage
- `config_drift` — hashes tracked config files and flags drift
- `sentinel_probe` — probes Sentinel `/healthz` and Prometheus scrape-up signal

## Remediation guardrails (Block C)
Process restart remediation now has guardrails to prevent runaway loops:
- **Dry-run by default** (`remediation.dry_run=true`) so restart actions are logged, not executed.
- **Cooldown** between attempts (`remediation.process_restart_cooldown_sec`).
- **Retry cap** within a time window (`remediation.process_restart_max_retries` in `remediation.process_restart_retry_window_sec`).
- Remediation counters and timestamps are persisted in `maintainer_state.json` under `remediation.process_restart`.

## Risks / limitations (current)
- webhook sink is single-destination only (no built-in fan-out to Telegram/Discord yet)
- remediation policy is process-only (other modules do not remediate yet)

## Webhook sink E2E smoke test
This validates end-to-end delivery from Maintainer's alert sink (`dispatch_alert`) to a local webhook receiver.

### One-command smoke test
```bash
cd maintainer
python3 tools/webhook_smoke.py
```

Expected output:
```text
PASS: maintainer alert sink delivered webhook payload
Receiver URL: http://127.0.0.1:<auto-port>/maintainer-alert
Captured file: /.../maintainer/tools/webhook_payloads.ndjson
Captured event: alert module=smoke_module status=critical
```

### Manual receiver + trigger (optional)
Terminal A:
```bash
cd maintainer
python3 tools/webhook_receiver.py --port 8787 --output tools/webhook_payloads.ndjson
```

Terminal B:
```bash
cd maintainer
python3 tools/webhook_smoke.py --port 8787 --payload-file tools/webhook_payloads.ndjson
```

Inspect latest payload:
```bash
tail -n 1 tools/webhook_payloads.ndjson
```

## Next milestones
1. Add tests for alert dedupe + recovery event behavior

## Production packaging (v1)
Systemd unit file is provided at `deploy/maintainer.service`.

### Install/start
```bash
cd /path/to/maintainer
sudo install -D -m 0644 deploy/maintainer.service /etc/systemd/system/maintainer.service

# Edit placeholders before first start:
# - User=maintainer
# - Group=maintainer
# - WorkingDirectory=/opt/maintainer
# - ExecStart=/usr/bin/python3 main.py
sudo systemctl daemon-reload
sudo systemctl enable --now maintainer.service
sudo systemctl status maintainer.service --no-pager
```

### Stop/restart
```bash
sudo systemctl stop maintainer.service
sudo systemctl start maintainer.service
sudo systemctl restart maintainer.service
sudo journalctl -u maintainer.service -f
```

### Rollback (last-known-good unit/code)
If a deployment fails or the daemon flaps:

1. Stop the service:
   - `sudo systemctl stop maintainer.service`
2. Restore previous unit or package snapshot:
   - `sudo cp /etc/systemd/system/maintainer.service.bak /etc/systemd/system/maintainer.service`
   - restore previous code directory (for example from tarball/symlinked release).
3. Reload systemd and start known-good version:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl start maintainer.service`
4. Verify health:
   - `sudo systemctl status maintainer.service --no-pager`
   - `sudo journalctl -u maintainer.service -n 100 --no-pager`

Suggested release hygiene:
- Keep `/etc/systemd/system/maintainer.service.bak` before replacing unit files.
- Deploy code as versioned directories (`/opt/maintainer/releases/<version>`) with a `current` symlink for quick rollback.

## Sentinel probe runbook (Block D)
1. **Set probe targets**
   - `export SENTINEL_HEALTH_URL="http://127.0.0.1:8085/healthz"`
   - `export SENTINEL_PROM_URL="http://127.0.0.1:9090/metrics"`
   - Optional: `export SENTINEL_LATENCY_WARN_MS="250"`
2. **Start Maintainer**
   - `python main.py`
   - Watch JSON logs for module `sentinel_probe`.
3. **Interpret status**
   - `ok`: health endpoint reachable and matched Prom signal value is above threshold.
   - `warn`: probes passed but latency exceeded `SENTINEL_LATENCY_WARN_MS`.
   - `critical`: health endpoint failed, Prom scrape failed/missing, or signal below threshold.
4. **Run drill script for evidence**
   - Pass case:
     - `./drill_sentinel_checks.py --health-url "$SENTINEL_HEALTH_URL" --prom-url "$SENTINEL_PROM_URL"`
   - Simulated failure cases:
     - `./drill_sentinel_checks.py --simulate health-fail`
     - `./drill_sentinel_checks.py --simulate prom-fail`
     - `./drill_sentinel_checks.py --simulate prom-low`
     - `./drill_sentinel_checks.py --simulate latency-warn`
   - Exit codes: `0=ok`, `1=warn`, `2=critical`.
5. **Capture evidence**
   - Keep drill JSON output and maintainer JSON log lines for the incident record/change ticket.

## Competitor / similar project scan
See `COMPETITOR_SCAN_2026-03-09.md`.
