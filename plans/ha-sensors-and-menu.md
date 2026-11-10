# Home Assistant sensors + on-board button menu

## Context
The board should show live data from the Home Assistant (HA) instance on the LAN. The first step is a text readout of CO2, temperature and humidity, which also proves the connection works. Energy usage per device comes later, so the poller takes a generic list of entities. The poll interval can be set from 1 to 60 s. Network I/O must never stall the physics/render loop. CircuitPython has no threads and `adafruit_requests` blocks, so the plan uses a small non-blocking HTTP state machine that advances one step per frame.

A text menu over the scene is driven by the side buttons. **RESET is a hardware reset that reboots the chip, so code can't read it. Only UP and DOWN are used.** Tap UP/DOWN moves the highlight, and holding either button for about 0.6 s selects. While the menu is hidden, any press opens it. Menu items: *Rotate 90°*, *Sensors: ON/OFF*, *Hide menu*. Settings are not saved and reset on boot. Saving comes later.

## Configuration: `settings.toml` is the single source
All HA config comes from `settings.toml`, on both hardware and desktop. Nothing is hard-coded and there are no CLI overrides.

| Key | Meaning |
|---|---|
| `CIRCUITPY_WIFI_SSID` / `CIRCUITPY_WIFI_PASSWORD` | WiFi (hardware only) |
| `HA_URL` | e.g. `http://10.41.2.101:8123`. Parsed once into host and port; a hostname is resolved once at startup |
| `HA_TOKEN` | Long-lived access token |
| `HA_CO2_ENTITY`, `HA_TEMPERATURE_ENTITY`, `HA_HUMIDITY_ENTITY` | Entity IDs |
| `HA_POLL_SECONDS` | 1–60, clamped, default 5 |
| *(later)* `HA_POWER_ENTITIES` | Comma-separated energy entities |

- Hardware: values are read with `os.getenv()` from `CIRCUITPY/settings.toml`.
- Desktop:
  - `src/config.py` (new) has `load_settings(path)`. On CircuitPython it wraps `os.getenv`. On CPython it parses the same file with `tomllib`.
  - `run.py` reads `src/hardware/settings.toml` by default (the same file `deploy.sh` copies to the board), and `--settings PATH` overrides the path.
  - If the file or `HA_URL` is missing, the desktop uses `FakeSensors`.
- Update `src/hardware/settings.toml.example`:
  - Add the new keys and replace the old `HUMIDITY_ENTITY`.
  - Keep `WASHER_ENTITY`.
  - Add a comment for the future `HA_POWER_ENTITIES`.
- Add `settings.toml` to `.gitignore`, since it holds the token.

## Components

### Non-blocking HA client — `src/home/ha_client.py`
- `HAClient(pool, host, port, token, entities, interval_s)`, where `entities` is a list of `(key, entity_id)`.
- `poll(now)` runs once per frame and does **at most one bounded step**:
  - States: IDLE → CONNECTING → SENDING → RECEIVING → PARSE → next entity. Each cycle fetches every entity in turn, then waits until the next interval.
  - The socket has `settimeout(0)`. OSErrors with a "would block" errno (EAGAIN, EINPROGRESS: 11/115/119) mean "try again next frame". Each `recv_into` call reads at most ~1 KB into a preallocated `bytearray(4096)` and `memoryview`.
  - Request: `GET /api/states/<entity_id>` with headers `Authorization: Bearer …` and `Connection: close`. The response is read until the server closes the connection. The client then splits headers from the body at `\r\n\r\n`, checks for status 200, runs `json.loads`, and takes `state` and `attributes.unit_of_measurement`.
  - A request that takes longer than about 5 s is closed and marked as failed. After a failure the client backs off to `max(interval, 10 s)`.
- It exposes `values[key] = (state, unit, t)`, `last_ok`, and a `changed` flag.
- Socket pool:
  - Hardware: `socketpool.SocketPool(wifi.radio)`.
  - Desktop: the CPython `socket` module, which has the same API, so the same client runs in the simulator.
- Hardware risk to check: whether non-blocking `connect()` raises EINPROGRESS cleanly. If it doesn't, use `settimeout(0.05)` for `connect()` only. That is a bounded stall, once per retry.
- `src/home/fake_sensors.py`: drifting values with the same `poll()`/`values` interface.

### Buttons — `src/ui/buttons.py`
- `ButtonGestures`: pure logic. It is fed `(key, pressed, t)` and emits `TAP_UP`, `TAP_DOWN` and `HOLD`.
  - `HOLD` fires once, at 600 ms.
  - The release that ends a hold is ignored.
- `KeypadButtons`: uses `keypad.Keys((board.BUTTON_UP, board.BUTTON_DOWN), value_when_pressed=False, pull=True)`. Scanning is debounced and runs in the background. Each frame it drains `events.get_into(event)` using a preallocated `Event`.
- Simulator: the Up/Down arrows are taps and Enter/Space is HOLD. This avoids X11 auto-repeat.

### Menu — `src/ui/menu.py`
- `Menu(items)` keeps `visible` and `index`, and holds a list of `(label_fn, action_fn)`.
- While hidden, any gesture opens the menu. While visible, a tap moves the highlight (wrapping) and HOLD runs the highlighted item.
- Items:
  - `ROTATE 90` sets rotation to `(rotation + 90) % 360`.
  - `SENSORS ON/OFF` toggles the sensor panel.
  - `HIDE MENU` closes the menu.

### Text overlay — `src/ui/text_panel.py`
- `TextPanel(group, width, y, max_lines)` owns a small bitmap of `width × (max_lines*6+1)` px as the top layer, with its own palette:
  - 0 transparent
  - 1 text
  - 2 dark backing
  - 3 highlight
- Colors are dimmed with `dim_palette`.
- `set_lines(lines, highlight=None)` redraws only when the text changes, using `bitmaptools.fill_region` for the backing and then `draw_text`. `hide()`/`show()` use `tilegrid.hidden`.
- Placement:
  - The sensor panel is at the bottom: `CO2 612PPM` / `T 21.4C` / `H 45%`. It shows `--` for unavailable values, and `HA OFFLINE` after 3 intervals with no success.
  - The menu panel is at the top, with a `>` marker and highlight color.
- The panel is a separate small layer, so it works with any scene and doesn't mark the screen dirty after it is drawn. If `DEBUG` shows refresh time going up, the fallback is to blit the pre-rendered panel into the pond canvas with `bitmaptools.blit(..., skip_source_index=0)`.

### Font — `src/graphics/graphics_helpers.py`
Extend `_FONT_3X5` with A–Z and `. - : > / °`, so text fits 16 characters × 10 lines.

### App wiring — `src/app.py`
- `App(width, height, scene_module, buttons, sensors, set_rotation)` builds the scene, the panels and the menu.
- `tick(dt, now)`: buttons → menu → `sensors.poll(now)` → panel text if anything changed → scene `update(dt)`.
- Rotation goes through `set_rotation`: `display.rotation` on hardware, and the sim display's rotation on desktop.

## Milestones (each one is a separate, testable commit)

**M1 — Font + text panel.**
- Extend the 3×5 font and add `TextPanel`.
- Add `src/app.py` with the scene + a static sensor panel showing placeholder text.
- Change `code.py` and `run.py` to use `App`. Remove the stale "ha director" `show(update(dt))` path in `run.py`.
- *Check:* placeholder text is readable over the pond in the simulator and on hardware, and the `DEBUG` fps and refresh ms are about the same as before.

**M2 — Fake sensors + formatting.**
- Add `FakeSensors` and wire it to the panel, with redraw-on-change and `--` handling.
- *Check:* the values in the simulator update at `HA_POLL_SECONDS`.

**M3 — Settings loader.**
- Add `src/config.py`, the new keys in `settings.toml.example`, and the `.gitignore` entry.
- `run.py` reads `src/hardware/settings.toml` (or `--settings`), `deploy.sh` copies it to the board, and `code.py` uses `os.getenv`.
- *Check:* changing `HA_POLL_SECONDS` in the file changes the fake update rate on both targets.

**M4 — Non-blocking HA client (desktop first).**
- Add `HAClient` over the CPython `socket` module, selected when `HA_URL` is set.
- *Check:* the simulator shows real values that match the HA UI. With a wrong port or IP the animation stays smooth and the panel shows `HA OFFLINE`, then recovers when the config is fixed. WSL2 reaches the LAN IP without mirrored networking, but `homeassistant.local` does not resolve there, so use the IP in `HA_URL`.
- *Done:* worst `poll()` measured at ≤0.3 ms on desktop across OK, 404, 401, slow server (timeout), refused port and blackholed IP. Requests use HTTP/1.0 so replies are never chunked; 401/403 aborts the cycle like an outage, 404 shows `--` for that entity only.

**M5 — HA client on hardware.**
- `code.py` connects to WiFi at boot if needed, builds the `SocketPool` and `HAClient`, and shows `NO WIFI` / `NO HA CFG` on failure.
- Add **net ms avg/max** for `sensors.poll()` to the `DEBUG` stats line.
- Confirm the non-blocking `connect()` behaviour, and apply the `settimeout(0.05)` fallback if needed.
- *Check:* the fps stays about the same and net max stays at a few ms, including with HA unreachable. Values update at both 1 s and 60 s.

**M6 — Buttons + menu.**
- Add `ButtonGestures`, `KeypadButtons`, sim key bindings, `Menu` and the menu panel, with Sensors ON/OFF and Hide menu.
- *Check:* on the real buttons, a tap moves the highlight and a hold selects. Hide closes the menu and any press reopens it. Sensors OFF hides the readout.

**M7 — Rotation.**
- Add the `ROTATE 90` item: `display.rotation` on hardware, plus a `rotation` property in `VirtualDisplay.refresh()` that remaps indices for a square panel.
- *Check:* four selections cycle 0→90→180→270→0 on both targets, with the menu and sensor text rotating with the scene.

**M8 — Docs.**
- Update the README / `code.py` header with the setup steps: settings keys, token creation, the button gestures, and that RESET only reboots.
- Record the measured overlay and net costs in `OPTIMIZATIONS.md`.

## Files
- **New:**
  - `src/app.py`
  - `src/config.py`
  - `src/home/{__init__,ha_client,fake_sensors}.py`
  - `src/ui/{__init__,buttons,menu,text_panel}.py`
  - `plans/ha-sensors-and-menu.md`
- **Modified:**
  - `src/graphics/graphics_helpers.py`
  - `src/hardware/code.py`
  - `src/run.py`
  - `src/simulator/virtual_matrix.py`
  - `deploy.sh`
  - `src/hardware/settings.toml.example`
  - `.gitignore`
- `deploy.sh` copies `src/hardware/settings.toml` to `CIRCUITPY/settings.toml` if it exists (`--no-settings` skips it). New `src/` modules are already copied.
