from __future__ import annotations

import json
import subprocess
import sys


def test_uvicorn_health_smoke_exits_cleanly() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/dev/smoke-health.py",
            "--timeout-sec",
            "20",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["ok"] is True
    assert report["terminated"] is True
    assert report["checks"]["healthz"]["status"] == 200
    assert report["checks"]["healthz"]["body"] == {"status": "ok"}
    assert report["checks"]["readyz"]["status"] == 200
    assert report["checks"]["readyz"]["body"]["status"] == "ready"
