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
