# Maintainer Handoff Map — 2026-03-13

## Purpose
Operator handoff map for Phase 0 controlled release support.

## Ownership
- Primary owner: Maintainer operator on duty
- Backup owner: Sentinel operator on duty

## Inputs required from Sentinel
- Current release gate status (G1-G7)
- Guardrail/routing regressions impacting probes
- Launch plan status changes

## Outputs provided to Sentinel
- Soak health summary (status counts + stability signal)
- Drill and launch closeout deltas
- Alert channel state (critical/warn/open)

## Escalation path
1. Soak/drill instability -> fail affected gate + block release
2. Evidence gap on required artifact -> fail gate immediately
3. Unresolved >30m -> stop cycle and handoff as blocker
