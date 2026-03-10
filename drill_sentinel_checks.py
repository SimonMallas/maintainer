#!/usr/bin/env python3
"""Lightweight Sentinel probe drill helper.

Runs the same style of checks as Maintainer's sentinel_probe module and can
simulate pass/fail modes for runbook drills/evidence capture.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch_url(url: str, timeout_sec: float) -> dict:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status_code": getattr(resp, "status", 200),
                "body": body,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
    except urllib.error.HTTPError as err:
        return {
            "ok": False,
            "status_code": err.code,
            "error": f"HTTP {err.code}",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as err:  # noqa: BLE001
        return {
            "ok": False,
            "status_code": None,
            "error": str(err),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def parse_prom_metric_value(prom_text: str, match: str) -> float | None:
    for raw_line in prom_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if match not in line:
            continue
        try:
            return float(line.split()[-1])
        except ValueError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel probe drill")
    parser.add_argument("--health-url", default="", help="Sentinel healthz URL")
    parser.add_argument("--prom-url", default="", help="Prometheus metrics URL")
    parser.add_argument("--prom-match", default='up{job="sentinel"}', help="Metric line substring to match")
    parser.add_argument("--prom-min", type=float, default=1.0, help="Minimum acceptable metric value")
    parser.add_argument("--latency-warn-ms", type=float, default=0.0, help="Warn if fetch latency exceeds this")
    parser.add_argument("--timeout-sec", type=float, default=3.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--simulate",
        choices=["none", "health-fail", "prom-fail", "prom-low", "latency-warn"],
        default="none",
        help="Inject synthetic failure/warn for drills",
    )
    args = parser.parse_args()

    report = {"status": "ok", "failures": [], "warnings": [], "checks": {}}

    if args.health_url:
        health = fetch_url(args.health_url, args.timeout_sec)
        report["checks"]["healthz"] = {
            "url": args.health_url,
            "ok": health["ok"],
            "status_code": health.get("status_code"),
            "latency_ms": health.get("latency_ms"),
        }
        if not health["ok"]:
            report["failures"].append(f"healthz failed ({health.get('error', 'unknown')})")
        if args.latency_warn_ms > 0 and health.get("latency_ms", 0) > args.latency_warn_ms:
            report["warnings"].append(
                f"healthz latency {health['latency_ms']}ms > {args.latency_warn_ms}ms"
            )

    if args.prom_url:
        prom = fetch_url(args.prom_url, args.timeout_sec)
        prom_value = parse_prom_metric_value(prom.get("body", ""), args.prom_match) if prom["ok"] else None
        report["checks"]["prom_up"] = {
            "url": args.prom_url,
            "match": args.prom_match,
            "value": prom_value,
            "min_value": args.prom_min,
            "status_code": prom.get("status_code"),
            "latency_ms": prom.get("latency_ms"),
        }
        if not prom["ok"]:
            report["failures"].append(f"prom scrape failed ({prom.get('error', 'unknown')})")
        elif prom_value is None:
            report["failures"].append(f"prom signal not found: {args.prom_match}")
        elif prom_value < args.prom_min:
            report["failures"].append(f"prom signal below threshold: {prom_value} < {args.prom_min}")
        if args.latency_warn_ms > 0 and prom.get("latency_ms", 0) > args.latency_warn_ms:
            report["warnings"].append(f"prom latency {prom['latency_ms']}ms > {args.latency_warn_ms}ms")

    if args.simulate == "health-fail":
        report["failures"].append("simulated: healthz failed")
    elif args.simulate == "prom-fail":
        report["failures"].append("simulated: prom scrape failed")
    elif args.simulate == "prom-low":
        report["failures"].append("simulated: prom signal below threshold")
    elif args.simulate == "latency-warn":
        report["warnings"].append("simulated: latency warning")

    if report["failures"]:
        report["status"] = "critical"
    elif report["warnings"]:
        report["status"] = "warn"

    print(json.dumps(report, indent=2))
    return 2 if report["status"] == "critical" else 1 if report["status"] == "warn" else 0


if __name__ == "__main__":
    raise SystemExit(main())
