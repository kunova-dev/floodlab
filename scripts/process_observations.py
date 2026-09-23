"""Run a reviewed temporal observation plan through interactive CDSE OIDC."""

import argparse
import logging
from pathlib import Path

from floodlab.eo_core.observation_jobs import execute_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    for name in ("openeo", "requests", "urllib3"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    print(
        "Complete the CDSE device login shown below in your browser. Do not paste tokens or passwords into FloodLab."
    )
    print(
        "After login, this command submits/resumes the reviewed observation jobs; CDSE credits may be consumed."
    )
    state = execute_plan(args.plan, Path(__file__).resolve().parents[1])
    print(state["state"] + ": " + state["message"])
    return 1 if state["state"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
