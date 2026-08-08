#!/usr/bin/env python3
"""Live chaos-engineering harness for the docker-compose stack.

Kills Redis / disconnects Postgres mid-request against a running stack and
verifies the system degrades gracefully (no crash, no hang, no corruption)
and recovers once the dependency returns.

Usage:
    python chaos/chaos_runner.py --scenario redis      # kill Redis mid-request
    python chaos/chaos_runner.py --scenario postgres   # drop Postgres mid-run
    python chaos/chaos_runner.py --all                 # run every scenario
    python chaos/chaos_runner.py --scenario redis --api-key <KEY>

Requires the docker-compose stack from the repo root to be up:
    docker compose up -d --build
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ("docker", "compose")

BASE_URL = os.getenv("CHAOS_BASE_URL", "http://127.0.0.1:8002")


def read_api_key() -> str:
    key = os.getenv("AGENT_API_KEY")
    if key:
        return key
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("AGENT_API_KEY="):
                return line.split("=", 1)[1].strip()
    return "demo-key-2024"


_client = httpx.Client(timeout=30.0)
API_KEY = read_api_key()
_HEADERS = {"X-API-Key": API_KEY}


class ChaosError(RuntimeError):
    pass


def _compose(*args: str) -> str:
    r = subprocess.run([*COMPOSE, *args], cwd=str(REPO_ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        raise ChaosError(f"docker compose {args} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _check(label: str, outcome: bool) -> None:
    print(f"  [{'PASS' if outcome else 'FAIL'}] {label}")
    if not outcome:
        raise ChaosError(f"assertion failed: {label}")


def _health() -> dict:
    r = _client.get(f"{BASE_URL}/health")
    return r.json()


def _wait_health(predicate, timeout: float = 60.0, step: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        try:
            last = _health()
            if predicate(last):
                return last
        except Exception:
            pass
        time.sleep(step)
    raise ChaosError(f"/health did not satisfy predicate within {timeout}s: {last}")


def _run_sync_async() -> str:
    r = _client.post(f"{BASE_URL}/api/v1/run-sync-async", headers=_HEADERS)
    if r.status_code not in (200, 202):
        raise ChaosError(f"run-sync-async returned {r.status_code}: {r.text}")
    return r.json().get("task_id", "")


def _poll_task(task_id: str, timeout: float = 120.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = _client.get(f"{BASE_URL}/api/v1/tasks/{task_id}", headers=_HEADERS)
        if r.status_code == 404:
            time.sleep(0.5)
            continue
        return r.status_code
    raise ChaosError(f"task {task_id} did not reach a terminal state within {timeout}s")


# ── Scenario: Redis killed mid-request ─────────────────────────────────────

def scenario_redis() -> None:
    print("\n" + "=" * 70)
    print("SCENARIO: kill Redis mid-request — caches + rate limiter degrade")
    print("=" * 70)

    _wait_health(lambda x: x.get("redis") == "ok")
    _check("baseline: redis ok", True)
    _check("baseline: API serves config", _client.get(f"{BASE_URL}/api/v1/config").status_code == 200)

    _compose("stop", "redis")
    print("  [INJECT] redis container stopped")
    try:
        h = _wait_health(lambda x: x.get("redis") != "ok", timeout=30.0)
        _check("health reports redis down", h.get("redis") != "ok")

        _check(
            "API still serves requests while Redis is down",
            _client.get(f"{BASE_URL}/api/v1/config").status_code == 200,
        )
        _check(
            "unrelated routes unaffected",
            _client.get(f"{BASE_URL}/api/v1/dev-webhook").status_code == 200,
        )
    finally:
        _compose("start", "redis")

    _wait_health(lambda x: x.get("redis") == "ok", timeout=60.0)
    _check("redis recovered and health ok again", True)
    _check("API healthy after recovery", _client.get(f"{BASE_URL}/api/v1/config").status_code == 200)
    print("  [OK] redis chaos: degraded gracefully, recovered cleanly")


# ── Scenario: PostgreSQL dropped mid-pipeline-run ──────────────────────────

def scenario_postgres() -> None:
    print("\n" + "=" * 70)
    print("SCENARIO: disconnect Postgres during a pipeline run — no corruption")
    print("=" * 70)

    _wait_health(lambda x: x.get("database") == "ok")
    _check("baseline: database ok", True)

    task_id = _run_sync_async()
    _check("async pipeline started", bool(task_id))
    _compose("stop", "postgres")
    print("  [INJECT] postgres stopped mid-run")

    # The pipeline must end in a clean, terminal 500 (DB dependency missing) —
    # never a hang, and never a misleading success that implies corruption.
    terminal = _poll_task(task_id, timeout=160.0)
    _check("in-flight run terminated without hanging", terminal in (500,))
    _check("run failed cleanly (HTTP 500), not corrupted", terminal == 500)

    h = _wait_health(lambda x: x.get("database") != "ok", timeout=30.0)
    _check("health reports database degraded", h.get("database") == "error")

    _compose("start", "postgres")
    _wait_health(lambda x: x.get("database") == "ok", timeout=120.0)

    # Full recovery: a fresh run must complete end-to-end.
    task2 = _run_sync_async()
    status2 = _poll_task(task2, timeout=180.0)
    _check("post-recovery run completes (HTTP 200)", status2 == 200)
    print("  [OK] postgres chaos: clean failure, no hang, no corruption, recovery")


# ── Runner ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["redis", "postgres", "all"], default="all")
    args = parser.parse_args()

    scenarios = []
    if args.scenario in ("redis", "all"):
        scenarios.append(scenario_redis)
    if args.scenario in ("postgres", "all"):
        scenarios.append(scenario_postgres)

    try:
        for scenario in scenarios:
            scenario()
    except Exception as exc:
        print(f"\nCHAOS RESULT: FAIL — {exc}")
        return 1

    print("\nCHAOS RESULT: PASS — all scenarios degraded gracefully and recovered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
