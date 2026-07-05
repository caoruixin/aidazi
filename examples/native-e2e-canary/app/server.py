#!/usr/bin/env python3
"""Phase-5 canary fixture web app — a REAL http.server product-under-test whose happy path is
FLIPPABLE by an in-envelope file a Dev "fix" writes.

The Phase-5 canary drives the framework's REAL managed `external_test_runner` path: the driver
starts THIS app (readiness poll), runs the real Node/Playwright runner (real chromium) against it,
captures real provenance, evaluates criteria, and — on a deterministic failure — dispatches an
autonomous in-envelope Dev fix, then RE-RUNS the real runner. To exercise fail -> fix -> pass with
a REAL browser, the `/result` page renders "OK" iff the fix flag file exists, else "BROKEN":

  * round 0 (flag absent)  -> `/result` shows BROKEN  -> the `result_ok` criterion FAILS
  * a Dev fix writes `--flag` (in approved_scope.modules_in_scope) -> the app RE-STARTS reading it
  * round 1 (flag present)  -> `/result` shows OK      -> `result_ok` PASSES

`/` (home) always renders OK (the `home_loads` criterion — a stable pass). NO clock/randomness in
any response body (deterministic). Config is purely the launch args (--port, --flag).
"""
import argparse
import http.server
import json
import os
import sys
import urllib.parse
from typing import Optional


def _fixed(flag_path: str) -> bool:
    return bool(flag_path) and os.path.isfile(flag_path)


def _page(title: str, body_id: str, text: str) -> str:
    return (f"<!doctype html><html><head><title>{title}</title></head><body>"
            f"<h1 id=\"{body_id}\">{text}</h1></body></html>")


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: A003 - silence per-request stderr (deterministic logs)
        return

    @property
    def flag_path(self) -> str:
        return getattr(self.server, "flag_path", "")

    def _html(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj) -> None:
        payload = json.dumps(obj, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802 - stdlib naming
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._html(200, _page("home", "home", "OK"))          # home_loads: always OK
        elif path == "/result":
            ok = _fixed(self.flag_path)
            self._html(200, _page("result", "result", "OK" if ok else "BROKEN"))
        elif path == "/__health":
            self._json(200, {"status": "ok", "fixed": _fixed(self.flag_path)})
        else:
            self._html(404, _page("nf", "status", "not found"))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="canary-app")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--flag", default="", help="path to the fix-flag file; present ⇒ /result OK")
    args = ap.parse_args(argv)
    httpd = http.server.HTTPServer(("127.0.0.1", args.port), Handler)
    httpd.flag_path = args.flag  # type: ignore[attr-defined]
    sys.stdout.write(f"CANARY_APP_READY port={httpd.server_address[1]}\n")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
