# Sign-off Soak Report — 2026-03-10

## Run
- Duration: 10 minutes (`timeout 600s`)
- Profile: `gpu,memory,disk,config_drift,sentinel_probe`
- Alert sink enabled to local receiver (`127.0.0.1:9997`)

## Results
- Module log lines: 85
- Status counts: `ok=85` (no warn/critical/error during soak)
- Module counts:
  - gpu: 30
  - memory: 20
  - disk: 10
  - config_drift: 5
  - sentinel_probe: 20

## Webhook observation
- Captured entries: 1
- Event type captured: `recovery` for `sentinel_probe`
- Interpretation: confirms webhook path and state transition handling were active; no new critical alerts during soak.

## Verdict
- **SIGN-OFF PASS (controlled launch profile)**
