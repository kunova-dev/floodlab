"""Run a saved pair plan via interactive OIDC; never store tokens or passwords."""

import argparse
import json
import logging
from pathlib import Path

from floodlab.eo_core.pair_jobs import diagnose_plan, execute_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Read saved job errors only; never submit/start processing",
    )
    args = parser.parse_args()
    # Device verification URL/code is printed by the client; HTTP/auth debug logs are disabled.
    for name in ("openeo", "requests", "urllib3"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    print(
        "Complete the CDSE device login shown below in your browser. Do not paste tokens or passwords into FloodLab."
    )
    print(
        "Read-only diagnostics: no processing jobs will be submitted or restarted."
        if args.diagnose
        else "After login, this command submits/resumes the two reviewed processing jobs; CDSE credits may be consumed."
    )
    try:
        root = Path(__file__).resolve().parents[1]
        if args.diagnose:
            try:
                report = diagnose_plan(args.plan, root)
            except Exception as exc:  # noqa: BLE001 -- do not print raw auth/HTTP errors
                print(
                    f"Diagnostics could not be retrieved ({type(exc).__name__}). Complete a fresh device login and retry --diagnose."
                )
                return 1
            print(json.dumps(report, indent=2))
            print(
                "Saved redacted diagnostics beside the plan as job-errors.json when jobs were found."
            )
            return 0
        state = execute_plan(args.plan, root)
    except FileExistsError:
        print(
            "A worker lock already exists. Do not start a second worker. After confirming no worker runs, inspect/remove only the stale worker.lock in this plan directory."
        )
        return 1
    except (ValueError, OSError, KeyError, TypeError):
        print("Invalid or unreadable plan; create a fresh plan in Flood Lab.")
        return 1
    print(state["state"] + ": " + state["message"])
    return 1 if state["state"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
