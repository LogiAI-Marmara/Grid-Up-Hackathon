"""Run the integration smoke test in an isolated Docker Compose project.

The runner owns its temporary project and database. It never accepts a DSN and
never truncates an existing database. Track B owns the scenario assertions.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
COMPOSE = ROOT / "deploy" / "docker-compose.yml"


def main() -> int:
    project = f"gridup-smoke-{uuid.uuid4().hex[:12]}"
    env = os.environ.copy()
    env.update({
        "GRIDUP_DB_NAME": "gridup_smoke",
        "GRIDUP_API_PORT": "0",
        "GRIDUP_TOPLAMA_PORT": "0",
        "GRIDUP_WEB_PORT": "0",
        "GRIDUP_MODBUS_PORT": "0",
    })
    compose = ["docker", "compose", "-p", project, "-f", str(COMPOSE)]

    def run(*args: str) -> None:
        subprocess.run([*compose, *args], cwd=ROOT, env=env, check=True)

    try:
        print(f"Smoke project: {project}", flush=True)
        run("build")
        run("up", "-d", "--wait", "veritabani", "analiz_api", "toplama", "arayuz", "modbus_server", "alarm_service")
        run("run", "--rm", "--no-deps", "-e", "GRIDUP_SMOKE=1", "simulator", "python", "/app/smoke_probe.py")
        run("exec", "-T", "-e", "GRIDUP_SMOKE=1", "analiz_api", "python", "/app/repo/deploy/smoke_seed.py")
        run(
            "exec", "-T", "analiz_api", "python", "-m", "analiz.duman",
            "--api", "http://127.0.0.1:8080",
            "--senaryolar", "/app/repo/deploy/smoke_scenarios.json",
            "--azami-imlec-gecikme-sn", "7200",
        )
        print("Smoke test passed: simulator -> collector, known scenarios -> detector -> API -> Track B checks.")
        return 0
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"Smoke test failed: {error}", file=sys.stderr)
        return 1
    finally:
        # Only the uniquely named project created above is removed.
        subprocess.run([*compose, "down", "--volumes", "--remove-orphans"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
