# Home Status LED Grid

An animated koi pond on a 64x64 RGB LED matrix (Adafruit MatrixPortal S3,
CircuitPython), with a live CO2 / temperature / humidity readout from Home
Assistant and a small on-screen menu driven by the board's side buttons.

The scene code in `src/` is shared by the board (`src/hardware/code.py`) and a
desktop simulator (`src/run.py`), so changes are previewed on the desktop and
then run on the board unchanged.

## Setup

### 1. Settings

All Home Assistant config lives in one file, `src/hardware/settings.toml`. It is
git-ignored because it holds your token.

```sh
cp src/hardware/settings.toml.example src/hardware/settings.toml
```

| Key | Meaning |
|---|---|
| `CIRCUITPY_WIFI_SSID` / `CIRCUITPY_WIFI_PASSWORD` | WiFi (board only) |
| `HA_URL` | e.g. `http://192.168.1.10:8123`. Plain http. Use an IP: `homeassistant.local` often doesn't resolve on CircuitPython or WSL2 |
| `HA_TOKEN` | Long-lived access token (see below) |
| `HA_CO2_ENTITY`, `HA_TEMPERATURE_ENTITY`, `HA_HUMIDITY_ENTITY` | Entity IDs to show |
| `HA_POLL_SECONDS` | Seconds between reads, 1–60 (clamped, default 5) |

Without the file or without `HA_URL`, the simulator shows fake drifting values
and the board shows `NO HA CFG`.

### 2. Home Assistant token

1. In Home Assistant, open your profile (bottom left), then the **Security** tab.
2. Under **Long-lived access tokens**, choose **Create token** and give it a
   name such as `led-grid`.
3. Copy the token (it is shown only once) into `HA_TOKEN`.

Entity IDs are under **Settings → Devices & services → Entities**. The board
reads `GET /api/states/<entity_id>` and shows the `state` and its unit.

### 3. Desktop simulator

```sh
pip install -r requirements.txt
cd src
python3 run.py                       # pond scene, reads hardware/settings.toml
python3 run.py --settings ../other.toml
python3 run.py --state ../other.json # saved settings (default: ../state.json)
```

Keys stand in for the side buttons: **Up / Down** tap, **Enter / Space** hold.

### 4. Board

The CIRCUITPY drive needs CircuitPython 10.x and `adafruit_imageload` from the
library bundle in `lib/`. The 64x64 panel needs the Address-E solder jumper on
the MatrixPortal closed. Then:

```sh
./deploy.sh                # code.py, settings.toml and src/ to the board
./deploy.sh --no-settings  # keep the board's own settings.toml
./deploy.sh --clean        # also delete files removed from src/
./deploy.sh --state FILE   # also copy FILE to CIRCUITPY/state.json (see below)
```

`deploy.sh` mounts the drive under WSL (`DRIVE=E` or `MOUNT=/path` to override).
At boot the readout shows `WIFI...` while connecting, then the values, or
`NO WIFI` / `NO HA CFG` if setup failed. `HA OFFLINE` means three poll intervals
passed without a successful read; it recovers by itself.

## Buttons and menu

Only the **UP** and **DOWN** buttons are read. **RESET** is a hardware reset: it
reboots the board and code can't see it.

- Any press opens the menu while it is hidden.
- A **tap** on UP or DOWN moves the highlight (it wraps).
- **Holding** either button for about 0.6 s runs the highlighted item.

| Item | Effect |
|---|---|
| `ROTATE 90` | Turns the display 90° clockwise (0 → 90 → 180 → 270 → 0) |
| `SENSORS ON/OFF` | Shows or hides the readout (values keep updating while hidden) |
| `DUMP STATE` | Prints the saved state on the serial console (see below) |
| `HIDE MENU` | Closes the menu |

The rotation and `SENSORS ON/OFF` are saved and come back after a reboot: on the
board in `microcontroller.nvm`, in the simulator in `state.json` at the repo root
(`run.py --state PATH` for another file). A save happens at most once per
`PERSIST_SECONDS` (`settings.toml`, 10–3600, default 60) and only after a change,
so a change made within that time before a power loss is lost. The simulator
also saves when its window closes.

### Editing the board's state

Edits are file-based and take effect at the next start:

1. **Pull.** At startup, and on `DUMP STATE`, the board prints its state as JSON
   between `---STATE BEGIN---` and `---STATE END---` on the serial console.
   `python3 tools/pull_state.py PORT [-o FILE]` waits up to 30 s for it (press
   RESET or select `DUMP STATE`) and writes it to `FILE` (default `state.json`).
   On WSL2 the serial port isn't visible without `usbipd`, so run it with
   Windows Python against `COMn`, or copy the text from any serial terminal.
2. **Edit** the file.
3. **Push.** `./deploy.sh --state FILE`, or drag the file onto CIRCUITPY as
   `state.json`. Copying it makes CircuitPython auto-reload, and the board
   imports it.

The board remembers the checksum of the file it imported, so the file can stay
on the drive: it isn't re-imported on every boot, and later menu changes still
stick. Each top-level section in the file replaces the saved one, so a file
with only `"settings"` leaves the rest alone; keys missing inside a section
get their defaults. A file that doesn't parse shows `BAD STATE.JSON` for a few
seconds and changes nothing (the reason is printed on the console). The
simulator's `state.json` uses the same format, so it can be pushed to the board
as is, and a pulled file runs in the simulator with `run.py --state FILE`.

## Performance

The network client never blocks the animation: each frame it does at most one
small non-blocking socket step. Set `DEBUG = True` in `code.py` to print fps
and per-frame physics, render, net and refresh times to the serial console.
See [OPTIMIZATIONS.md](OPTIMIZATIONS.md) for measurements and
[plans/ha-sensors-and-menu.md](plans/ha-sensors-and-menu.md) for the design.
