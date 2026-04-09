from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


CONTROLLED_PREFIXES = (
    "backend/src/tradingbot/api/routers/settings.py",
    "backend/src/tradingbot/api/routers/trading.py",
    "backend/src/tradingbot/schemas/settings.py",
    "backend/src/tradingbot/services/agents.py",
    "backend/src/tradingbot/services/committee.py",
    "backend/src/tradingbot/services/execution.py",
    "backend/src/tradingbot/services/prompt_registry.py",
    "backend/src/tradingbot/services/risk.py",
    "backend/src/tradingbot/services/store.py",
    "backend/src/tradingbot/worker/",
    "contracts/committee-decision.schema.json",
)
RELEASE_LOG_PATH = "docs/strategy-change-log.md"
REQUIRED_FIELDS = (
    "Release ID",
    "Independent Reviewer",
    "Release Evidence",
    "Rollback Plan",
    "Risk Change Summary",
)
PLACEHOLDER_VALUES = {
    "",
    "required",
    "[required]",
    "_required_",
    "tbd",
    "todo",
    "n/a",
    "na",
    "-",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate release-evidence requirements for controlled PRs.")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--event-path", default=os.getenv("GITHUB_EVENT_PATH"))
    return parser.parse_args()


def _changed_files(base_sha: str, head_sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_release_controlled(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in CONTROLLED_PREFIXES)


def _load_pr_body(event_path: str | None) -> str:
    if not event_path:
        return ""
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request") or {}
    body = pull_request.get("body")
    return body if isinstance(body, str) else ""


def _field_value(body: str, label: str) -> str | None:
    match = re.search(rf"(?im)^{re.escape(label)}\s*:\s*(.+)$", body)
    if not match:
        return None
    return match.group(1).strip()


def _is_missing(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized in PLACEHOLDER_VALUES


def main() -> int:
    args = _parse_args()
    changed_files = _changed_files(args.base_sha, args.head_sha)
    controlled_files = [path for path in changed_files if _is_release_controlled(path)]

    if not controlled_files:
        print("release-guard: no release-controlled files changed")
        return 0

    print("release-guard: controlled files changed:")
    for path in controlled_files:
        print(f"  - {path}")

    errors: list[str] = []
    if RELEASE_LOG_PATH not in changed_files:
        errors.append(f"{RELEASE_LOG_PATH} must be updated for release-controlled changes.")

    body = _load_pr_body(args.event_path)
    for label in REQUIRED_FIELDS:
        if _is_missing(_field_value(body, label)):
            errors.append(f"PR body field '{label}' is required for release-controlled changes.")

    if errors:
        print("release-guard failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("release-guard: release evidence requirements satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
