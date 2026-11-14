#!/usr/bin/python3
"""Draws what this Mac is doing as a black-and-white picture and sends it to
the Quiet Screens add-on, which shows it on the Kindle.

While this runs, the Kindle shows the Mac. When the Mac sleeps this stops, the
picture goes stale, and the add-on switches the Kindle back to TRMNL. Nothing
here needs to detect sleep.

Standard library only; rendering uses Google Chrome in headless mode.

    kindle.py                 loop forever (what the login item runs)
    kindle.py --once          draw and send once
    kindle.py --save out.png  draw to a file, send nothing
    kindle.py --art out.png   draw the art-only fallback picture
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
EVERY_SECONDS = 30      # how often the picture is re-sent, so it stays fresh
MAX_LINES = 3           # the budget; see README


def load_config():
    with open(os.path.join(HERE, "kindle.json")) as handle:
        return json.load(handle)


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


def run_line(line):
    if "text" in line:
        return line["text"]
    try:
        out = subprocess.run(line["command"], shell=True, capture_output=True, text=True, timeout=5).stdout
        return out.strip().splitlines()[0].strip() if out.strip() else ""
    except Exception:
        return ""


def house_lines(config):
    """The same lines every other screen shows, from the add-on."""
    try:
        with urllib.request.urlopen(config["addon"] + "/state.json", timeout=5) as response:
            return json.load(response).get("lines") or []
    except Exception:
        return []


def gather(config):
    app = front_app()
    title, lines = app, []
    for activity in config.get("activities", []):
        if app in activity.get("apps", []):
            title = activity.get("title") or app
            for line in activity.get("lines", [])[:MAX_LINES]:
                text = run_line(line)
                if text:
                    lines.append({"label": line.get("label", ""), "text": text})
            break
    if not lines:
        lines = house_lines(config)[:MAX_LINES]
    now = datetime.datetime.now()
    return {
        "art": now.toordinal(),   # a different drawing each day
        "date": now.strftime("%A, %B ") + str(now.day),
        "title": title,
        "lines": lines,
    }


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


def send(png_path, config):
    with open(png_path, "rb") as handle:
        body = handle.read()
    headers = {"Content-Type": "image/png"}
    if config.get("token"):
        headers["X-Quiet-Token"] = config["token"]
    request = urllib.request.Request(config["addon"] + "/kindle/push", data=body, headers=headers)
    urllib.request.urlopen(request, timeout=10).read()


def main():
    config = load_config()
    args = sys.argv[1:]
    if args[:1] == ["--art"]:
        return draw({"art": 0, "artOnly": True}, config, os.path.abspath(args[1]))
    if args[:1] == ["--save"]:
        return draw(gather(config), config, os.path.abspath(args[1]))

    png = os.path.join(tempfile.gettempdir(), "quiet-kindle.png")
    last, reported = None, None
    while True:
        try:
            data = gather(config)
            if data != last or not os.path.exists(png):
                draw(data, config, png)
                last = data
            send(png, config)
            problem = None
        except Exception as error:
            problem = str(error)
        if problem != reported:   # say it once, not every 30 seconds
            print(problem or "sending to the Kindle", flush=True)
            reported = problem
        if args[:1] == ["--once"]:
            return 1 if problem else 0
        time.sleep(EVERY_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
