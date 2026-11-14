# HimboFrame

Quiet home screens. One web page, loaded by every screen in the house. It looks
like art until you need it.

## The three modes

| Mode | What shows | How you get there |
| --- | --- | --- |
| Art | A picture and a small clock | The default; everything returns here after 20 seconds |
| Glance | Time, date, up to three lines | Any remote key or tap, or an alert arriving |
| Play | A row of app names | Down or OK from Glance, on screens that list apps |

## The rules

These are what keep it quiet. Changing one is a decision, not a tweak.

1. **Three lines.** A screen shows the time, the date, one alert and at most
   three lines. A new line replaces an old one.
2. **One file in.** Screens only read `state.json`. Anything new is a change to
   the add-on's line templates, never to the screen.
3. **One file to edit.** Per-screen differences live in `quiet/app/config.js`.
4. **No build step, no dependencies.** Plain files that any device can load.
5. **Wrong is worse than blank.** Data older than 15 minutes is hidden.

## state.json

```json
{
  "updated": "2026-11-11T14:05:00Z",
  "lines": [
    { "label": "Weather", "text": "52° and clear" },
    { "label": "Next", "text": "Dentist at 2:30" }
  ],
  "alert": ""
}
```

`updated` is optional; when present it drives the 15-minute staleness check. A
non-empty `alert` wakes the screen into Glance for 45 seconds.

## Layout

This folder is a Home Assistant add-on repository. `quiet/` is the add-on: a
small server (`server.py`) plus the screen itself (`quiet/app/`).

Inside Home Assistant the server builds `state.json` from the templates in the
add-on's Configuration tab, using the access Home Assistant gives add-ons. No
token to manage. It listens on port 4796, separate from Home Assistant's own
address.

## Installing

Either:

- **From GitHub:** push this folder to a repository, then in Home Assistant go
  to Settings, Add-ons, Add-on Store, the menu, Repositories, and add its URL.
- **As a local add-on:** copy the `quiet` folder into Home Assistant's `addons`
  folder, then use Check for updates in the Add-on Store.

Install Quiet Screens, start it, and point each screen at
`http://<home-assistant-address>:4796/?screen=<name>`.

## Kindle (e-ink)

A jailbroken Kindle running KOReader shows a black-and-white version. The
Kindle only fetches a picture and reports taps; the add-on and the Mac do the
rest.

- **Mac awake:** `mac/kindle.py` draws what the Mac is doing and sends it to
  the add-on every 30 seconds. The Kindle shows that.
- **Mac asleep:** the picture goes stale after two minutes and the add-on hands
  the Kindle your TRMNL device's current screen instead (set `trmnl_api_key` in
  the add-on's Configuration tab). With no key it shows a line drawing.
- **Buttons:** up to three across the bottom. A tap goes Kindle, add-on, Mac;
  the Mac runs that button's command and redraws.

What the Mac screen says is set in `mac/kindle.json`:

- `activities`: each names the apps it applies to, a title, up to three lines,
  and optional buttons. A line is fixed `text` or a shell `command` whose first
  line of output is shown. Apps with no activity show the house lines.
- `buttons` (top level): shown on every Mac screen.
- A button has a `label`, a `command` to run when tapped, and an optional
  `show_if` command; the button appears only when that succeeds.

On the Kindle, copy `kindle/quiet.koplugin` into KOReader's `plugins` folder,
check the address in its `server.txt`, restart KOReader, and start it from
Tools, Quiet Screens. Hold anywhere on the screen to leave. The last TRMNL
screen is kept at `koreader/quiet/sleep.png` for use as a sleep screen.

To run the Mac side at login:

```bash
cp mac/net.himbo.quiet-kindle.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/net.himbo.quiet-kindle.plist
```

## Running it on a laptop

```bash
python3 quiet/server.py
```

Then open `http://localhost:4796/?screen=demo`. Arrow keys, Enter and Escape
stand in for the remote. Without Home Assistant it serves the sample
`quiet/app/state.json`.

## Art

Put images in `quiet/app/art/` and list them under `art` in
`quiet/app/config.js`. The three
SVGs there are placeholders.
