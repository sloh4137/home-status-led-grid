# Home Status LED Grid

An animated koi pond on a 64x64 RGB LED matrix (Adafruit MatrixPortal S3,
CircuitPython), with a live CO2 / temperature / humidity readout from Home
Assistant and a small on-screen menu driven by the board's side buttons. The
house shows up in the pond too: bad air drains its color and slows it down,
the washer calls in an electric eel, the 3D printer floats a lily pad, power
use zaps electricity between the fish, and an HA helper puts it to sleep.

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
| `HA_WASHER_POWER_ENTITY` | Washer smart plug power sensor, in W |
| `WASHER_ON_WATTS` | Above this the washer counts as running, 1–500 (clamped, default 10) |
| `HA_PRINTER_POWER_ENTITY` | 3D printer smart plug power sensor, in W |
| `PRINTER_ON_WATTS` | Above this the printer counts as on, 1–500 (clamped, default 10) |
| `HA_TOTAL_POWER_ENTITY` | A helper summing the house's power, in W |
| `ZAP_MIN_WATTS` / `ZAP_MAX_WATTS` | House power range for the zaps: none at or below the min (0–20000, default 300), the top rate at or above the max (100–50000, default 5000, at least min + 100) |
| `HA_DISPLAY_ENTITY` | An `input_boolean` helper, e.g. `input_boolean.pond_display`. `off` puts the panel to sleep (see [Display sleep](#display-sleep)) |
| `HA_POLL_SECONDS` | Seconds between reads, 1–60 (clamped, default 5) |
| `PERSIST_SECONDS` | Minimum seconds between saves of the settings and the pond, 10–3600 (clamped, default 60). Saves only happen after a change |
| `POND_TIME_SCALE` | Debug only: speeds up the pond's clock, so fish age, breed and die in minutes. 3600 makes a pond hour pass every second. 1–86400 (clamped, default 1) |

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

With fake sensors the values cycle slowly so every effect shows up, and keys
set them by hand: **+ / -** CO2 in 100 ppm steps, **W / P** toggle the washer /
the 3D printer, **[ / ]** the house's total power in 500 W steps, **D** the
display helper (off blacks out the window, and any button key wakes it for
5 minutes), and **0** resumes every cycle.

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
- While the display sleeps, a press only wakes it (for 5 minutes) and doesn't
  open the menu.

| Item | Effect |
|---|---|
| `ROTATE 90` | Turns the display 90° clockwise (0 → 90 → 180 → 270 → 0) |
| `SENSORS ON/OFF` | Shows or hides the readout (values keep updating while hidden) |
| `DUMP STATE` | Prints the saved state on the serial console (see below) |
| `HIDE MENU` | Closes the menu |

The rotation, `SENSORS ON/OFF` and the pond (see below) are saved and come
back after a reboot: on the
board in `microcontroller.nvm`, in the simulator in `state.json` at the repo root
(`run.py --state PATH` for another file). A save happens at most once per
`PERSIST_SECONDS` (`settings.toml`, 10–3600, default 60) and only after a change,
so a change made within that time before a power loss is lost. The pond
changes about once a pond hour (ages, births, deaths), so that's a few dozen
saves a day. Each save on the board takes ~170 ms (a short hitch in the
animation), almost all of it rewriting the 8 KB nvm blob. The simulator also
saves when its window closes.

## The pond

Koi, catfish and sturgeon (at most 10 fish in all) plus exactly one turtle
live in the pond, over schools of background boids. Each fish has a saved
genome: its species, color variety, the seed that places its spots, its own
maximum size, its age and how many young it has had. Positions aren't saved,
so after a restart every fish starts at a random spot.

- A fish is born small (30 % of its max size, the turtle 60 %) and grows in
  10 % steps until it's full grown at 30 % of its lifespan.
- Between 50 and 90 % of its lifespan it may breed, up to 2 young, while the
  pond has room. A child usually has its parent's species and variety (about
  80 % the same variety, 15 % one of the same family, 5 % any), and its max
  size is the parent's ±10 %. A small share of births is another species.
- It dies at its lifespan ±10 %, fixed by its seed.
- The turtle never breeds. When it dies it leaves an egg, which hatches 12
  pond hours later into a turtle with completely random stats.
- The pond clock runs in real time: a koi lives about a week. Set
  `POND_TIME_SCALE` to watch it happen faster. Births, deaths and hatchings
  are printed on the console.
- High CO2 drains the color out of the pond (fish and water), in visible
  steps: full color at 800 ppm or below, down to 20 % saturation at
  2000 ppm.
- It also slows every moving thing (fish and boids) over the same range,
  down to 0.4x at 2000 ppm, easing in over a few seconds. Aging and the
  water animation keep real time, so bad air doesn't make fish live longer.

## Home Assistant effects

Besides CO2, the pond reads a few more entities from `settings.toml` that
show up in the pond itself rather than in the readout. Any key left unset
just turns its effect off, and an unavailable sensor counts as off.

| Entity | In the pond |
|---|---|
| `HA_WASHER_POWER_ENTITY` above `WASHER_ON_WATTS` | An **electric eel** swims in from an edge and darts around the pond, flickering in electric colors |
| `HA_PRINTER_POWER_ENTITY` above `PRINTER_ON_WATTS` | A **lily pad with a tiny 3D printer** on it drifts across the surface, its print head moving. The fish swim under it |
| `HA_TOTAL_POWER_ENTITY` | **Electricity zaps** between neighbouring boids: jagged yellow bolts to a nearby flockmate and small arcs around one boid. None at or below `ZAP_MIN_WATTS`, rising on a log scale to about 2 zaps a second at `ZAP_MAX_WATTS` |
| `HA_DISPLAY_ENTITY` | `off` puts the panel to sleep (below) |

- A visitor arrives as soon as its plug goes above the threshold, but leaves
  only after it has stayed below for a minute, so a washer's soaks and a
  printer's heater cycles don't send it away. It then swims off screen on
  its own.
- The eel and the lily pad come from HA, not from the save: they never age,
  breed or count toward the pond's 10 fish.
- Like everything else, they slow down and lose their color with high CO2.
  The zaps keep their rate, since power use has nothing to do with the air.
- The smart plugs' idle draw has to stay under the thresholds. 10 W (the
  default) works for typical plugs; raise it if a device idles higher.

### Display sleep

When `HA_DISPLAY_ENTITY` reads exactly `off`, the panel goes dark: the
board pauses the LED scan, stops moving and drawing the fish, and ticks 10
times a second instead of rendering frames. The pond keeps living: fish
still age, breed and die, saves continue, and HA is still polled, so a
visitor that left while the panel was dark doesn't come back on wake.

- Turning the helper back `on` wakes the panel within one poll interval
  plus a poll cycle, about 5–10 s at `HA_POLL_SECONDS = 5`.
- A button press wakes it for 5 minutes even while the helper is `off`.
  The board never writes the helper back to HA.
- It fails open: an unavailable or unset helper, no WiFi or `HA OFFLINE`
  all keep the pond showing, with its status line, rather than a dark panel
  that looks broken. After a reboot the pond shows for a few seconds until
  the first read.

Create the helper under **Settings → Devices & services → Helpers →
Create helper → Toggle**, then drive it from an automation, e.g. with a
room's presence sensor, so the pond is only on while someone is there:

```yaml
alias: Pond display follows presence
triggers:
  - trigger: state
    entity_id: binary_sensor.living_room_presence
    to: "on"
    id: here
  - trigger: state
    entity_id: binary_sensor.living_room_presence
    to: "off"
    for: "00:15:00"
    id: away
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: here
        sequence:
          - action: input_boolean.turn_on
            target:
              entity_id: input_boolean.pond_display
      - conditions:
          - condition: trigger
            id: away
        sequence:
          - action: input_boolean.turn_off
            target:
              entity_id: input_boolean.pond_display
mode: restart
```

### Genome fields

The `pond` section of the state file (see below) holds `next_id` and a `fish`
list, one object per fish:

```json
{"id": 3, "species": "koi", "variety": "sanke", "seed": 40213, "max_size": 92, "age_hours": 51, "offspring": 1}
```

| Field | Valid values | If missing or invalid |
|---|---|---|
| `id` | Integer ≥ 0, unique | Missing: the next free id. A duplicate drops the fish |
| `species` | `koi`, `catfish`, `sturgeon`, `turtle` | The fish is dropped |
| `variety` | One of the species' varieties (below) | A random variety |
| `seed` | 0–65535: places the spots, and fixes the age of death | A random seed |
| `max_size` | The species' size range (below), percent of the base body | Clamped into range; random if not an integer |
| `age_hours` | Integer ≥ 0 pond hours. Turtle only: −12…−1 is an egg that hatches at 0 | 0 |
| `offspring` | 0–2 (always 0 for the turtle) | Clamped, or 0 |

| Species | Varieties | `max_size` | Lifespan | At most |
|---|---|---|---|---|
| `koi` | `kohaku`, `sanke`, `showa`, `tancho`, `shiro utsuri`, `hi utsuri`, `ki utsuri`, `asagi`, `shusui`, `hariwake`, `yamabuki ogon`, `platinum ogon`, `chagoi` | 50–110 | 7 days (168 h) | 6 |
| `catfish` | `plain`, `mottled`, `albino` | 50–100 | 10 days (240 h) | 2 |
| `sturgeon` | `plain` | 50–130 | 14 days (336 h) | 2 |
| `turtle` | `slider`, `box`, `albino` | 60–90 | 30 days (720 h) | exactly 1, or its egg |

Every fix is printed on the console as `state: pond.fish[i] koi: …`, and the
repaired pond is saved. A pond with no turtle gets a turtle egg, and an extra
turtle is dropped. `{"species": "catfish"}` alone is a valid hand-added fish:
the rest is filled in. A file with an empty `fish` list starts an empty pond
(plus the turtle egg); one with no `pond` section keeps the saved pond, or
starts a fresh one if nothing is saved.

`tools/full_pond.json` is a full pond (10 full-grown fish plus the turtle),
used for the measurements in [OPTIMIZATIONS.md](OPTIMIZATIONS.md).

## Editing the board's state

Edits are file-based and take effect at the next start. There's no live
editing:

1. **Pull.** At startup, and on `DUMP STATE`, the board prints its state as JSON
   between `---STATE BEGIN---` and `---STATE END---` on the serial console.
   `python3 tools/pull_state.py PORT [-o FILE]` waits up to 30 s for it (press
   RESET or select `DUMP STATE`) and writes it to `FILE` (default `state.json`).
   On WSL2 the serial port isn't visible without `usbipd`, so run it with
   Windows Python against `COMn`, or copy the text from any serial terminal.
2. **Edit** the file (see [Genome fields](#genome-fields) for the pond).
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

The simulator doubles as a playground: design a pond by hand, or let one
breed for a while with a high `POND_TIME_SCALE`. Stop the simulator before
editing its `state.json`, or its next save overwrites your edit. Then push it
with `./deploy.sh --state state.json`.

## Performance

The network client never blocks the animation: each frame it does at most one
small non-blocking socket step. Set `DEBUG = True` in `code.py` to print fps
and per-frame physics, render, net and refresh times to the serial console
(and a `sleep` line every 30 s while the display sleeps).
See [OPTIMIZATIONS.md](OPTIMIZATIONS.md) for measurements, and
[plans/ha-sensors-and-menu.md](plans/ha-sensors-and-menu.md) and
[plans/persistence-and-fish-variation.md](plans/persistence-and-fish-variation.md)
and [plans/ha-pond-effects.md](plans/ha-pond-effects.md) for the design.
