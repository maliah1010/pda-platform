"""Demo health-check script.

Verifies that all PDA Platform API endpoints return data for a sample project.
Run with the API server already running on http://localhost:8000.

Usage::

    python scripts/check_demo.py
    python scripts/check_demo.py --base-url http://localhost:8000 --project PROJ-001

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

try:
    import urllib.request
    import json as _json

    def _get(url: str) -> tuple[int, Any]:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status, _json.loads(resp.read())
        except Exception as exc:
            return 0, {"error": str(exc)}

except ImportError:
    print("ERROR: urllib not available", file=sys.stderr)
    sys.exit(1)


CHECKS: list[tuple[str, str, str | None]] = [
    # (label, path_template, expected_key)
    ("Health", "/api/health", "status"),
    ("Projects list", "/api/projects", "projects"),
    ("Portfolio overview", "/api/portfolio", "items"),
    ("Project detail", "/api/projects/{project_id}", "id"),
    ("Compliance trend", "/api/compliance/{project_id}", "project_id"),
    ("Schedule recommendation", "/api/schedule/{project_id}", "project_id"),
    ("Override decisions", "/api/overrides/{project_id}", "project_id"),
    ("Lessons summary", "/api/lessons/summary", "total_lessons"),
    ("Overhead history", "/api/overhead/{project_id}", "project_id"),
    ("Workflow history", "/api/workflows/{project_id}/history", "project_id"),
    ("Domain classification", "/api/classifier/{project_id}", None),
    ("Currency check", "/api/currency/{project_id}", "project_id"),
    ("Actions list", "/api/actions/{project_id}", "project_id"),
    ("Assumptions", "/api/assumptions/{project_id}", "project_id"),
    ("Assumption health", "/api/assumptions/{project_id}/health", "project_id"),
    ("ARMM report", "/api/armm/{project_id}", "project_id"),
    ("ARMM dimensions", "/api/armm/{project_id}/dimensions", "project_id"),
    ("ARMM criteria", "/api/armm/{project_id}/criteria", "project_id"),
    ("ARMM history", "/api/armm/{project_id}/history", "project_id"),
    ("ARMM portfolio", "/api/armm/portfolio", "count"),
]


def run_checks(base_url: str, project_id: str) -> int:
    """Run all checks and return the number of failures."""
    failures = 0
    max_label = max(len(label) for label, _, _ in CHECKS)

    print(f"\nPDA Platform Demo Health Check")
    print(f"API: {base_url}   Project: {project_id}")
    print("-" * 72)

    for label, path_template, expected_key in CHECKS:
        path = path_template.replace("{project_id}", project_id)
        url = base_url.rstrip("/") + path
        status, body = _get(url)

        if status == 0:
            result = "FAIL  (connection error)"
            failures += 1
        elif status >= 400:
            result = f"FAIL  (HTTP {status})"
            failures += 1
        elif expected_key and expected_key not in body:
            result = f"FAIL  (missing '{expected_key}' in response)"
            failures += 1
        else:
            # Show a concise summary of the response
            summary = ""
            if isinstance(body, dict):
                if "count" in body:
                    summary = f"{body['count']} items"
                elif "items" in body:
                    summary = f"{len(body['items'])} items"
                elif "overall_level" in body:
                    summary = f"level={body['overall_level']}"
                elif "status" in body:
                    summary = str(body["status"])
            result = f"OK    {summary}"

        padded = label.ljust(max_label)
        print(f"  {padded}  {result}")

    print("-" * 72)
    if failures == 0:
        print(f"  All {len(CHECKS)} checks passed.\n")
    else:
        print(f"  {failures} of {len(CHECKS)} checks FAILED.\n")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="PDA Platform demo health check")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--project", default="PROJ-001")
    args = parser.parse_args()

    failures = run_checks(args.base_url, args.project)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
