#!/usr/bin/env python3
"""Tiny local webhook receiver for Maintainer alert sink smoke tests."""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ReceiverHandler(BaseHTTPRequestHandler):
    output_path: Path
    once: bool

    def _write_entry(self, payload: dict) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        text = raw.decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"_raw": text}

        entry = {
            "received_at": int(time.time()),
            "path": self.path,
            "body": body,
        }
        self._write_entry(entry)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

        if self.once:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local webhook receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--output", default="tools/webhook_payloads.ndjson")
    parser.add_argument("--once", action="store_true", help="Exit after first successful POST")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()

    ReceiverHandler.output_path = output_path
    ReceiverHandler.once = args.once

    server = ThreadingHTTPServer((args.host, args.port), ReceiverHandler)
    print(f"[receiver] listening on http://{args.host}:{args.port} -> {output_path}")
    if args.once:
        print("[receiver] once mode enabled; will exit after first POST")
    server.serve_forever()


if __name__ == "__main__":
    main()
