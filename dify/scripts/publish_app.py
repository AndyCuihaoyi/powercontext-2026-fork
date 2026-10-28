#!/usr/bin/env python3
"""Import the Memory Pawnshop DSL into Dify, publish it, and issue an API key.

Requires a reachable Dify console account. Credentials come from CLI flags or
environment variables; nothing secret is written into the repository.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


class ConsoleError(RuntimeError):
    pass


class Console:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def _csrf_from_jar(self) -> str:
        for cookie in self.jar:
            if cookie.name == "csrf_token":
                return cookie.value
        return ""

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        csrf = self._csrf_from_jar()
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ConsoleError(f"{method} {path} -> HTTP {exc.code}: {body[:500]}") from exc
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ConsoleError(f"{method} {path} returned non-JSON: {body[:300]}") from exc

    def login(self, email: str, password: str) -> None:
        token = base64.b64encode(password.encode("utf-8")).decode("ascii")
        self.request("POST", "/console/api/login", {"email": email, "password": token, "remember_me": True})

    def find_app(self, name: str) -> str | None:
        page = 1
        while True:
            data = self.request("GET", f"/console/api/apps?page={page}&limit=100")
            for app in data.get("data", []):
                if app.get("name") == name:
                    return app["id"]
            if not data.get("has_more"):
                return None
            page += 1

    def import_dsl(self, yaml_content: str) -> str:
        data = self.request("POST", "/console/api/apps/imports", {"mode": "yaml-content", "yaml_content": yaml_content})
        if not data.get("app_id"):
            raise ConsoleError(f"import did not return an app_id: {data}")
        if data.get("status") not in ("completed", "completed-with-warnings"):
            raise ConsoleError(f"import failed: {data}")
        return data["app_id"]

    def publish(self, app_id: str) -> None:
        self.request("POST", f"/console/api/apps/{app_id}/workflows/publish", {"marked_name": "", "marked_comment": ""})

    def create_key(self, app_id: str) -> str:
        data = self.request("POST", f"/console/api/apps/{app_id}/api-keys", {})
        if not data.get("token"):
            raise ConsoleError(f"api key creation returned no token: {data}")
        return data["token"]

    def delete_app(self, app_id: str) -> None:
        self.request("DELETE", f"/console/api/apps/{app_id}")


APP_NAME = "记忆当铺 · Memory Pawnshop"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dify-base", default=os.environ.get("DIFY_BASE", "http://127.0.0.1:5001"))
    parser.add_argument("--email", default=os.environ.get("DIFY_ADMIN_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("DIFY_ADMIN_PASSWORD", ""))
    parser.add_argument("--password-file", default="")
    parser.add_argument("--dsl", default=str(Path(__file__).resolve().parent.parent / "dsl" / "memory-pawnshop.yml"))
    parser.add_argument("--key-out", default="", help="optional file to write the issued API key")
    parser.add_argument("--keep-existing", action="store_true", help="do not delete an app with the same name")
    args = parser.parse_args()

    password = args.password
    if not password and args.password_file:
        password = Path(args.password_file).read_text(encoding="utf-8").strip()
    if not args.email or not password:
        print("admin email/password required (--email/--password/--password-file or env)", file=sys.stderr)
        return 2

    dsl = Path(args.dsl).read_text(encoding="utf-8")
    console = Console(args.dify_base)
    console.login(args.email, password)

    existing = console.find_app(APP_NAME)
    if existing and not args.keep_existing:
        console.delete_app(existing)
        existing = None

    app_id = existing
    if app_id is None:
        app_id = console.import_dsl(dsl)
    console.publish(app_id)
    api_key = console.create_key(app_id)

    result = {"app_id": app_id, "api_key": api_key, "dify_base": args.dify_base}
    if args.key_out:
        Path(args.key_out).write_text(api_key + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
