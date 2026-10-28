#!/usr/bin/env python3
"""Seed a few demo tickets through the published Dify application."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


MEMORIES = [
    "小学春游时我捡到一块像星星的石头，藏在抽屉最里面，后来搬家弄丢了。",
    "高考前一晚偷偷看完一本漫画，第二天数学考砸了，但我一点也不后悔。",
    "第一次出远门，在火车站和妈妈挥手，她一直站在原地没走。",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-base", default=os.environ.get("GATEWAY_BASE", "http://127.0.0.1:8099"))
    parser.add_argument("--player", default="示范客人")
    parser.add_argument("--reset", action="store_true", help="reset this player before seeding")
    args = parser.parse_args()
    base = args.gateway_base.rstrip("/")

    if args.reset:
        data = urllib.request.urlopen(
            urllib.request.Request(
                base + "/api/reset",
                data=("player=" + urllib.parse.quote(args.player)).encode(),
                method="POST",
            ),
            timeout=30,
        ).read().decode()
        print(data)

    tickets = []
    for memory in MEMORIES:
        body = json.dumps({"player": args.player, "action": "典当", "content": memory}).encode()
        req = urllib.request.Request(base + "/api/run", data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            answer = urllib.request.urlopen(req, timeout=180).read().decode()
        except urllib.error.HTTPError as exc:
            print(f"seed failed: HTTP {exc.code}: {exc.read().decode()[:300]}", file=sys.stderr)
            return 1
        match = re.search(r"P\d{3,}-\d{3}", answer)
        ticket = match.group(0) if match else "?"
        tickets.append(ticket)
        print(f"seeded {ticket}: {memory}")
    print(json.dumps({"player": args.player, "tickets": tickets}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
