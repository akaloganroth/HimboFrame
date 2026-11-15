#!/usr/bin/python3
"""Draws what this Mac is doing as a black-and-white picture and sends it to
the Quiet Screens add-on, which shows it on the Kindle. Buttons drawn on the
picture can be tapped on the Kindle; the taps come back here and run a command.

While this runs, the Kindle shows the Mac. When the Mac sleeps this stops, the
picture goes stale, and the add-on switches the Kindle back to TRMNL. Nothing
here needs to detect sleep.

Standard library only; rendering uses Google Chrome in headless mode.

    kindle.py                 loop forever (what the login item runs)
    kindle.py --once          draw and send once
    kindle.py --save out.png  draw to a file, send nothing
    kindle.py --art out.png   draw the art-only fallback picture
"""
import base64
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
EVERY_SECONDS = 30      # how often the picture is re-sent, so it stays fresh
WATCH_SECONDS = 3       # how often the app in front is checked in between
MAX_LINES = 3           # the budget; see README
MAX_BUTTONS = 3

# Where the row of buttons sits, as fractions of the page.
ROW_LEFT, ROW_RIGHT, ROW_TOP, ROW_HEIGHT, ROW_GAP = 0.08, 0.92, 0.87, 0.075, 0.03


def load_config():
    with open(os.path.join(HERE, "kindle.json")) as handle:
        return json.load(handle)


def shell(command, timeout=5):
    """Run a command; returns (succeeded, first line of output)."""
    try:
        done = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        out = done.stdout.strip()
        return done.returncode == 0, (out.splitlines()[0].strip() if out else "")
    except Exception:
        return False, ""


def front_app():
    """Name of the app in front. Needs no special permission."""
    try:
        front = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=5).stdout.strip()
        info = subprocess.run(["lsappinfo", "info", "-only", "name", front],
                              capture_output=True, text=True, timeout=5).stdout
        match = re.search(r'"LSDisplayName"="([^"]+)"', info) or re.match(r'\s*"([^"]+)"', info)
        return match.group(1) if match else ""
    except Exception:
        return ""


def house_lines(config):
    """The same lines every other screen shows, from the add-on."""
    try:
        with urllib.request.urlopen(config["addon"] + "/state.json", timeout=5) as response:
            state = json.load(response)
        # Only real data carries a timestamp; the sample file does not.
        return (state.get("lines") or []) if state.get("updated") else []
    except Exception:
        return []


def pick_art(config, now):
    """Which drawing to show: "daily" (default), "hourly", or a fixed number."""
    choice = config.get("art", "daily")
    if isinstance(choice, int):
        return choice
    return now.toordinal() * 24 + now.hour if choice == "hourly" else now.toordinal()


def trmnl_picture(config):
    """The TRMNL screen from the add-on, ready to place in the page, or ''."""
    try:
        with urllib.request.urlopen(config["addon"] + "/trmnl.png", timeout=10) as response:
            return "data:image/png;base64," + base64.b64encode(response.read()).decode()
    except Exception:
        return ""


def gather(config):
    """Returns (what to draw, {button id: command})."""
    app = front_app()
    title, lines, wanted, picture = app, [], [], ""
    # The first activity that matches wins. An activity matches when its
    # `when` command succeeds, or when the app in front is in its `apps`
    # ("*" means any app).
    for activity in config.get("activities", []):
        apps = activity.get("apps", [])
        if "when" in activity:
            matched = shell(activity["when"])[0]
        else:
            matched = app in apps or "*" in apps
        if not matched:
            continue
        title = activity.get("title") or app
        if "title_command" in activity:
            title = shell(activity["title_command"])[1] or title
        for line in activity.get("lines", []):
            text = line["text"] if "text" in line else shell(line["command"])[1]
            if text and len(lines) < MAX_LINES:   # empty lines are skipped, so list spares
                lines.append({"label": line.get("label", ""), "text": text})
        wanted += activity.get("buttons", [])
        if activity.get("layout") == "trmnl":   # the drawing plus the TRMNL screen, in place of lines
            picture = trmnl_picture(config)
        break
    if not lines:
        lines = house_lines(config)[:MAX_LINES]

    # Buttons for this activity first, then the ones that apply everywhere.
    wanted += config.get("buttons", [])
    shown = [b for b in wanted if "show_if" not in b or shell(b["show_if"])[0]][:MAX_BUTTONS]
    buttons, commands = [], {}
    if shown:
        width = (ROW_RIGHT - ROW_LEFT - ROW_GAP * (len(shown) - 1)) / len(shown)
        for i, button in enumerate(shown):
            ident = hashlib.sha1((button["label"] + button["command"]).encode()).hexdigest()[:10]
            commands[ident] = button["command"]
            buttons.append({"id": ident, "label": button["label"],
                            "x": round(ROW_LEFT + i * (width + ROW_GAP), 4), "y": ROW_TOP,
                            "w": round(width, 4), "h": ROW_HEIGHT})

    now = datetime.datetime.now()
    data = {
        "art": pick_art(config, now),
        "date": now.strftime("%A, %B ") + str(now.day),
        "title": title,
        "lines": lines,
        "buttons": buttons,
        "picture": picture,
    }
    return data, commands


def draw(data, config, out_path):
    with open(os.path.join(HERE, "ink.html")) as handle:
        page = handle.read()
    page = re.sub(r"/\*DATA\*/.*?/\*END\*/", lambda _: json.dumps(data).replace("</", "<\\/"), page, flags=re.S)
    with tempfile.TemporaryDirectory() as work:
        html = os.path.join(work, "page.html")
        with open(html, "w") as handle:
            handle.write(page)
        subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--force-device-scale-factor=2",
            "--window-size=%d,%d" % (config["width"] // 2, config["height"] // 2),
            "--user-data-dir=" + os.path.join(work, "profile"),
            "--screenshot=" + out_path, "file://" + html,
        ], capture_output=True, timeout=60, check=True)


def headers(config, extra=None):
    out = dict(extra or {})
    if config.get("token"):
        out["X-Quiet-Token"] = config["token"]
    return out


def send(png_path, data, config):
    with open(png_path, "rb") as handle:
        body = handle.read()
    request = urllib.request.Request(config["addon"] + "/kindle/push", data=body, headers=headers(config, {
        "Content-Type": "image/png",
        "X-Quiet-Buttons": json.dumps(data.get("buttons", [])),
    }))
    with urllib.request.urlopen(request, timeout=10) as response:
        screen = json.load(response).get("screen") or {}
    # True when the Kindle has been turned and the picture must be redrawn.
    if screen.get("width") and (screen["width"], screen["height"]) != (config["width"], config["height"]):
        config["width"], config["height"] = screen["width"], screen["height"]
        return True
    return False


class Taps(threading.Thread):
    """Waits for taps from the Kindle and runs the matching command."""

    def __init__(self, config):
        super().__init__(daemon=True)
        self.config = config
        self.commands = {}
        self.tapped = threading.Event()   # tells the main loop to redraw now

    def run(self):
        while True:
            try:
                request = urllib.request.Request(self.config["addon"] + "/kindle/taps", headers=headers(self.config))
                with urllib.request.urlopen(request, timeout=40) as response:
                    taps = json.load(response).get("taps", [])
            except Exception:
                time.sleep(5)
                continue
            for ident in taps:
                command = self.commands.get(ident)   # only commands from the config, never from the network
                if command:
                    ok, _ = shell(command, timeout=30)
                    print("button %s: %s" % (ident, "done" if ok else "failed"), flush=True)
            if taps:
                self.tapped.set()


def main():
    config = load_config()
    args = sys.argv[1:]
    if args[:1] == ["--art"]:
        return draw({"art": 0, "artOnly": True}, config, os.path.abspath(args[1]))
    if args[:1] == ["--save"]:
        return draw(gather(config)[0], config, os.path.abspath(args[1]))

    once = args[:1] == ["--once"]
    taps = Taps(config)
    if not once:
        taps.start()
    png = os.path.join(tempfile.gettempdir(), "quiet-kindle.png")
    last, reported = None, "starting"
    while True:
        try:
            data, commands = gather(config)
            taps.commands = commands
            if data != last or not os.path.exists(png):
                draw(data, config, png)
                last = data
            if send(png, data, config):
                draw(data, config, png)
                send(png, data, config)
            problem = None
        except Exception as error:
            problem = str(error)
        if problem != reported:   # say it once, not every 30 seconds
            print(problem or "sending to the Kindle", flush=True)
            reported = problem
        if once:
            return 1 if problem else 0
        # Wait for the next resend, but leave early on a tap or a change of app.
        app, waited = front_app(), 0
        while waited < EVERY_SECONDS and not taps.tapped.wait(WATCH_SECONDS):
            waited += WATCH_SECONDS
            if front_app() != app:
                break
        taps.tapped.clear()


if __name__ == "__main__":
    sys.exit(main())
