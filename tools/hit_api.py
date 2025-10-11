#!/usr/bin/env python3
"""Helper to invoke the local backend API from the host shell."""

import argparse
import json
import sys
from typing import Any, Dict, Optional

import requests

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hit the running backend API")
    parser.add_argument("path", help="API path, e.g. /api/health")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Hostname (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (default 5000)")
    parser.add_argument("--method", default="GET", help="HTTP method (GET, POST, etc.)")
    parser.add_argument(
        "--json",
        dest="json_payload",
        help="JSON payload for POST/PUT requests",
    )
    parser.add_argument(
        "--headers",
        help="Optional JSON object of headers to include",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    url = f"http://{args.host}:{args.port}{args.path}"
    method = args.method.upper()

    data: Optional[Dict[str, Any]] = None
    if args.json_payload:
        try:
            data = json.loads(args.json_payload)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON payload: {exc}", file=sys.stderr)
            return 2

    headers: Optional[Dict[str, str]] = None
    if args.headers:
        try:
            headers = json.loads(args.headers)
        except json.JSONDecodeError as exc:
            print(f"Invalid headers JSON: {exc}", file=sys.stderr)
            return 2

    try:
        response = requests.request(method, url, json=data, headers=headers)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    print(f"{response.status_code} {response.reason}")
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            parsed = response.json()
            print(json.dumps(parsed, indent=2, sort_keys=True))
            return 0
        except json.JSONDecodeError:
            pass
    print(response.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
