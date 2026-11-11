"""Serves the quiet screen and builds state.json from Home Assistant.

Inside the add-on, Home Assistant supplies SUPERVISOR_TOKEN and the lines come
from the add-on's options. Without the token (running on a laptop) it serves
the sample app/state.json instead. Standard library only.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
TOKEN = os.environ.get("SUPERVISOR_TOKEN")
API = os.environ.get("QUIET_HA_API", "http://supervisor/core/api")
OPTIONS = os.environ.get("QUIET_OPTIONS", "/data/options.json")
PORT = int(os.environ.get("QUIET_PORT", "4796"))

MAX_LINES = 3  # the budget; see README
CACHE_SECONDS = 30
EMPTY = {"", "unknown", "unavailable", "none"}

_cache = {"at": 0.0, "body": b"{}"}


def render(template):
    """Ask Home Assistant to render a template. Any failure gives ''."""
    if not template:
        return ""
    request = urllib.request.Request(
        API + "/template",
        data=json.dumps({"template": template}).encode(),
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            text = response.read().decode().strip()
    except Exception as error:  # a broken line is dropped, never shown
        print("template failed:", error, flush=True)
        return ""
    return "" if text.lower() in EMPTY else text


def build_state():
    with open(OPTIONS) as handle:
        options = json.load(handle)
    lines = []
    for line in (options.get("lines") or [])[:MAX_LINES]:
        text = render(line.get("template"))
        if text:
            lines.append({"label": line.get("label", ""), "text": text})
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lines": lines,
        "alert": render(options.get("alert")),
    }


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if TOKEN and self.path.split("?")[0] == "/state.json":
            if time.time() - _cache["at"] > CACHE_SECONDS:
                _cache["body"] = json.dumps(build_state()).encode()
                _cache["at"] = time.time()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(_cache["body"])))
            self.end_headers()
            self.wfile.write(_cache["body"])
            return
        super().do_GET()

    def end_headers(self):
        # Screens pick up changes on their next load, with nothing cached.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("quiet: port %d, %s" % (PORT, "Home Assistant data" if TOKEN else "sample data"), flush=True)
    ThreadingHTTPServer(("", PORT), partial(Handler, directory=ROOT)).serve_forever()
