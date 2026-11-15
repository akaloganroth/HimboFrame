"""Serves the quiet screen and builds state.json from Home Assistant.

Inside the add-on, Home Assistant supplies SUPERVISOR_TOKEN and the lines come
from the add-on's options. Without the token (running on a laptop) it serves
the sample app/state.json instead. Standard library only.

It also feeds an e-ink screen (a Kindle running the Quiet KOReader plugin). The
Mac pushes a picture of what it is doing, with the positions of any buttons
drawn on it; while that picture is fresh the Kindle shows it, and otherwise it
shows the TRMNL screen. Taps on a button come back here and wait for the Mac
to collect them.
"""
import hashlib
import json
import os
import tempfile
import threading
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

# ---- e-ink screen
DATA = os.environ.get("QUIET_DATA", "/data")
if not os.access(DATA, os.W_OK):
    DATA = tempfile.gettempdir()
PUSHED = os.path.join(DATA, "kindle.png")
BUTTONS = os.path.join(DATA, "kindle-buttons.json")
TRMNL_PICTURE = os.path.join(DATA, "trmnl.png")
SHARE = "/share/quiet"       # Home Assistant's shared folder, for other uses of the picture
MAC_REFRESH_SECONDS = 15     # how often the Kindle asks while the Mac is awake
TAP_WAIT_SECONDS = 20        # how long the Mac's request for taps is held open
TAP_KEEP_SECONDS = 30        # an uncollected tap older than this is dropped
_taps = []
_screen = {}                 # the Kindle's width and height, as it last reported them
_taps_ready = threading.Condition()
FALLBACK = os.path.join(ROOT, "art", "ink.png")
FRESH_SECONDS = 120          # a Mac picture older than this means the Mac is asleep
MAX_PUSH_BYTES = 5 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# /api/display hands out the next screen in the TRMNL playlist each time it is
# asked, the way a real device gets them. Adding /current only repeats what the
# physical device last showed.
TRMNL_API = os.environ.get("QUIET_TRMNL_API", "https://trmnl.com/api/display")
_trmnl = {"at": 0.0, "data": None, "every": 240}


def options():
    try:
        with open(OPTIONS) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def mac_is_awake():
    try:
        return time.time() - os.path.getmtime(PUSHED) < FRESH_SECONDS
    except OSError:
        return False


def buttons():
    try:
        with open(BUTTONS) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return []


def allowed(headers):
    token = options().get("kindle_token")
    return not token or headers.get("X-Quiet-Token") == token


def trmnl_fetch(url, headers=None):
    # TRMNL's servers refuse Python's default client name, so give our own.
    request = urllib.request.Request(url, headers=dict(headers or {}, **{"User-Agent": "quiet-screens"}))
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read()


def trmnl_screen():
    """The TRMNL screen to show, as {"filename": ...}, or None.

    By default this steps through the playlist, asking for the next screen as
    often as TRMNL says to. With trmnl_advance off it mirrors the physical
    device instead. The picture is copied here, because TRMNL's own link to it
    stops working after five minutes."""
    key = (options().get("trmnl_api_key") or "").strip()
    if not key:
        return None
    advance = options().get("trmnl_advance", True)
    if time.time() - _trmnl["at"] > _trmnl["every"]:
        _trmnl["at"] = time.time()
        try:
            data = json.loads(trmnl_fetch(TRMNL_API + ("" if advance else "/current"), {"access-token": key}))
            # When stepping through the playlist, wait as long as TRMNL asks
            # (never less than four minutes); a mirror just checks back.
            _trmnl["every"] = max(240, int(data.get("refresh_rate") or 900)) if advance else 240
            if not data.get("image_url"):   # TRMNL answered, but not with a screen
                raise ValueError(json.dumps(data)[:200])
            name = data.get("filename") or hashlib.sha1(data["image_url"].encode()).hexdigest()[:16]
            current = _trmnl["data"] or {}
            if name != current.get("filename") or not os.path.exists(TRMNL_PICTURE):
                picture = trmnl_fetch(data["image_url"])
                with open(TRMNL_PICTURE + ".tmp", "wb") as handle:
                    handle.write(picture)
                os.replace(TRMNL_PICTURE + ".tmp", TRMNL_PICTURE)
                if os.path.isdir("/share"):
                    os.makedirs(SHARE, exist_ok=True)
                    with open(os.path.join(SHARE, "trmnl.png.tmp"), "wb") as handle:
                        handle.write(picture)
                    os.replace(os.path.join(SHARE, "trmnl.png.tmp"), os.path.join(SHARE, "trmnl.png"))
            _trmnl["data"] = {"filename": name}
        except Exception as error:
            print("trmnl failed:", error, flush=True)
            _trmnl["data"] = None
            _trmnl["every"] = 240
    return _trmnl["data"]


def display(host):
    """What the e-ink screen should show, in TRMNL's device format. It always
    carries the TRMNL screen too, as `sleep`, for the Kindle's sleep screen."""
    answer = showing(host)
    screen = trmnl_screen()
    if screen:
        answer["sleep"] = {"image_url": "http://%s/trmnl.png?v=%s" % (host, screen["filename"]),
                           "filename": screen["filename"]}
    return answer


def showing(host):
    if mac_is_awake():
        # Named by content, so an unchanged picture is not a new screen.
        with open(PUSHED, "rb") as handle:
            name = hashlib.sha1(handle.read()).hexdigest()[:16]
        return {"status": 0, "image_url": "http://%s/kindle.png?v=%s" % (host, name),
                "filename": "mac-" + name, "refresh_rate": MAC_REFRESH_SECONDS, "buttons": buttons()}
    screen = trmnl_screen()
    if screen:
        return {"status": 0, "image_url": "http://%s/trmnl.png?v=%s" % (host, screen["filename"]),
                "filename": screen["filename"], "refresh_rate": 300}
    return {"status": 0, "image_url": "http://%s/art/ink.png" % host, "filename": "quiet-art", "refresh_rate": 300}


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
    def send_bytes(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """The Mac sends its picture here: a PNG as the request body."""
        path = self.path.split("?")[0]
        if path not in ("/kindle/push", "/kindle/tap"):
            return self.send_bytes(404, b"{}")
        if not allowed(self.headers):
            return self.send_bytes(403, b'{"error": "wrong token"}')
        length = int(self.headers.get("Content-Length") or 0)
        if path == "/kindle/tap":
            # The Kindle says which button was touched. Only buttons that are
            # on the current picture count.
            try:
                tapped = json.loads(self.rfile.read(min(length, 1000)) or b"{}").get("id")
            except ValueError:
                tapped = None
            if not mac_is_awake() or tapped not in [b.get("id") for b in buttons()]:
                return self.send_bytes(409, b'{"error": "no such button now"}')
            with _taps_ready:
                _taps.append({"id": tapped, "at": time.time()})
                _taps_ready.notify_all()
            return self.send_bytes(200, b'{"ok": true}')
        if not 0 < length <= MAX_PUSH_BYTES:
            return self.send_bytes(413, b'{"error": "bad size"}')
        body = self.rfile.read(length)
        if not body.startswith(PNG_MAGIC):
            return self.send_bytes(400, b'{"error": "not a PNG"}')
        with open(PUSHED + ".tmp", "wb") as handle:
            handle.write(body)
        try:
            drawn = json.loads(self.headers.get("X-Quiet-Buttons") or "[]")
        except ValueError:
            drawn = []
        with open(BUTTONS, "w") as handle:
            json.dump(drawn if isinstance(drawn, list) else [], handle)
        os.replace(PUSHED + ".tmp", PUSHED)
        self.send_bytes(200, json.dumps({"ok": True, "screen": _screen}).encode())

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/display":
            try:
                _screen.update(width=int(self.headers["png-width"]), height=int(self.headers["png-height"]))
            except (KeyError, TypeError, ValueError):
                pass
            host = self.headers.get("Host") or "localhost:%d" % PORT
            return self.send_bytes(200, json.dumps(display(host)).encode())
        if path == "/kindle/taps":
            # The Mac waits here; the answer comes as soon as a button is touched.
            if not allowed(self.headers):
                return self.send_bytes(403, b'{"error": "wrong token"}')
            with _taps_ready:
                if not _taps:
                    _taps_ready.wait(TAP_WAIT_SECONDS)
                recent = [t["id"] for t in _taps if time.time() - t["at"] < TAP_KEEP_SECONDS]
                del _taps[:]
            return self.send_bytes(200, json.dumps({"taps": recent}).encode())
        if path == "/trmnl.png":
            trmnl_screen()   # make sure the copy is current, even if no Kindle is asking
            try:
                with open(TRMNL_PICTURE, "rb") as handle:
                    return self.send_bytes(200, handle.read(), "image/png")
            except OSError:
                return self.send_bytes(404, b"{}")
        if path == "/kindle.png":
            try:
                with open(PUSHED if os.path.exists(PUSHED) else FALLBACK, "rb") as handle:
                    return self.send_bytes(200, handle.read(), "image/png")
            except OSError:
                return self.send_bytes(404, b"{}")
        if TOKEN and path == "/state.json":
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
