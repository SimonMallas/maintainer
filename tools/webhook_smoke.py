#!/usr/bin/env python3
"""End-to-end smoke test for Maintainer alert webhook sink."""

from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def load_maintainer_main(main_path: Path):
    spec = importlib.util.spec_from_file_location("maintainer_main", main_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {main_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Maintainer webhook alert sink")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Receiver port (0 = auto)")
    parser.add_argument(
        "--payload-file",
        default="tools/webhook_payloads.ndjson",
        help="Where receiver writes captured payload(s)",
    )
    parser.add_argument("--timeout", type=float, default=8.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    receiver_path = root / "tools" / "webhook_receiver.py"
    maintainer_main_path = root / "main.py"

    payload_file = Path(args.payload_file).expanduser().resolve()
    payload_file.parent.mkdir(parents=True, exist_ok=True)
    if payload_file.exists():
        payload_file.unlink()

    port = args.port or free_port()
    receiver_cmd = [
        sys.executable,
        str(receiver_path),
        "--host",
        args.host,
        "--port",
        str(port),
        "--output",
        str(payload_file),
        "--once",
    ]

    receiver = subprocess.Popen(receiver_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(0.5)

        module = load_maintainer_main(maintainer_main_path)
        config = module.load_config()
        config["runtime"]["state_file"] = str((root / "maintainer_state_smoke.json").resolve())
        config["alert_sink"]["webhook_url"] = f"http://{args.host}:{port}/maintainer-alert"
        config["alert_sink"]["cooldown_sec"] = 1
        config["alert_sink"]["http_timeout_sec"] = 3
        module.apply_config(config)

        result = {
            "status": "critical",
            "message": "smoke-test critical alert",
            "data": {"source": "webhook_smoke.py"},
        }
        import asyncio as _asyncio
        _asyncio.run(module.dispatch_alert("smoke_module", result))

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            if payload_file.exists() and payload_file.stat().st_size > 0:
                break
            time.sleep(0.2)

        if not payload_file.exists() or payload_file.stat().st_size == 0:
            print("FAIL: no payload captured by local receiver")
            if receiver.stdout:
                print(receiver.stdout.read().strip())
            return 1

        line = payload_file.read_text(encoding="utf-8").strip().splitlines()[0]
        captured = json.loads(line)
        body = captured.get("body", {})

        checks = [
            body.get("event") == "alert",
            body.get("module") == "smoke_module",
            body.get("status") == "critical",
            body.get("message") == "smoke-test critical alert",
        ]
        if not all(checks):
            print("FAIL: payload shape/content mismatch")
            print(json.dumps(captured, indent=2))
            return 2

        print("PASS: maintainer alert sink delivered webhook payload")
        print(f"Receiver URL: http://{args.host}:{port}/maintainer-alert")
        print(f"Captured file: {payload_file}")
        print(f"Captured event: {body.get('event')} module={body.get('module')} status={body.get('status')}")
        return 0
    finally:
        receiver.terminate()
        try:
            receiver.wait(timeout=2)
        except subprocess.TimeoutExpired:
            receiver.kill()


if __name__ == "__main__":
    raise SystemExit(main())
