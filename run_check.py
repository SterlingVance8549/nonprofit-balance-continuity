from __future__ import annotations

import argparse
import json

from continuity_service import ContinuityCheck, build_gateway, run_continuity_check


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one nonprofit continuity check")
    parser.add_argument("request_file", help="JSON file containing a ContinuityCheck request")
    args = parser.parse_args()

    with open(args.request_file, encoding="utf-8") as request_file:
        request = ContinuityCheck.model_validate(json.load(request_file))

    gateway = build_gateway()
    try:
        result = run_continuity_check(request, gateway)
    finally:
        gateway.close()
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
