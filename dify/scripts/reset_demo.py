#!/usr/bin/env python3
"""Reset a demo player: clear tickets and rotate the PowerContext scope."""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-base", default=os.environ.get("GATEWAY_BASE", "http://127.0.0.1:8099"))
    parser.add_argument("--player", default="示范客人")
    args = parser.parse_args()
    data = urllib.parse.urlencode({"player": args.player}).encode()
    req = urllib.request.Request(args.gateway_base.rstrip("/") + "/api/reset", data=data, method="POST")
    try:
        print(urllib.request.urlopen(req, timeout=30).read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode()[:400], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
