#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Reactor uvicorn health/readiness smoke.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--timeout-sec", type=float, default=15.0)
    args = parser.parse_args(argv)

    port = args.port or free_port(args.host)
    env = smoke_env(port)
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "reactor.main:app",
            "--host",
            args.host,
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    report: dict[str, Any] = {
        "ok": False,
        "host": args.host,
        "port": port,
        "checks": {},
        "terminated": False,
    }
    try:
        deadline = time.monotonic() + args.timeout_sec
        report["checks"]["healthz"] = wait_for_json(
            f"http://{args.host}:{port}/healthz",
            deadline=deadline,
            expected_status=200,
        )
        report["checks"]["readyz"] = wait_for_json(
            f"http://{args.host}:{port}/readyz",
            deadline=deadline,
            expected_status=200,
        )
        report["ok"] = True
        return 0
    except Exception as error:
        report["error"] = str(error)
        return 1
    finally:
        report["terminated"] = terminate(process)
        if not report["terminated"]:
            report["ok"] = False
        print(json.dumps(report, sort_keys=True))


def smoke_env(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["REACTOR_HOST"] = "127.0.0.1"
    env["REACTOR_PORT"] = str(port)
    env["REACTOR_DATABASE_REQUIRED"] = "false"
    env["REACTOR_REDIS_REQUIRED"] = "false"
    env["REACTOR_SCHEDULER_ENABLED"] = "false"
    env["REACTOR_ALERT_SCHEDULER_ENABLED"] = "false"
    env["REACTOR_PROMPT_LAB_SCHEDULER_ENABLED"] = "false"
    env["REACTOR_SLACK_SOCKET_MODE_ENABLED"] = "false"
    return env


def free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def wait_for_json(url: str, *, deadline: float, expected_status: int) -> dict[str, Any]:
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:  # noqa: S310
                status = response.status
                payload = json.loads(response.read().decode("utf-8"))
            if status == expected_status:
                return {"status": status, "body": payload}
            last_error = f"{url} returned {status}"
        except HTTPError as error:
            last_error = f"{url} returned {error.code}"
        except (OSError, URLError, json.JSONDecodeError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {url}: {last_error}")


def terminate(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return True
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    return process.poll() is not None


if __name__ == "__main__":
    raise SystemExit(main())
