# LED Matrix Fish Tank 🐟

Generated with AI so we could get a virtual preview before we really started getting working with hardware.

A 64x64 RGB LED matrix (Adafruit #5362) driven by a MatrixPortal, showing
programmable fish + animations that react to Home Assistant sensors
(humidity, washer state, ...).

![fish tank preview](previews/fish_tank.gif)

## 1. Parts checklist

| Part | What | Notes |
|---|---|---|
| [64x64 RGB LED Matrix, 2mm pitch](https://www.adafruit.com/product/5362) | The display (4096 LEDs, 128mm square) | Kit includes the power cable. Uses **5-address (ABCDE)** multiplexing -- needs the E jumper (below). |
| MatrixPortal | The controller | **Recommended: [MatrixPortal S3](https://www.adafruit.com/product/5778)** -- WiFi on the main chip, 8MB flash / 2MB RAM, Adafruit's current pick. The [M4 (4745)](https://adafruit.com/product/4745) you linked also works (WiFi via ESP32 coprocessor) but is older/slower. Either way it plugs straight into the panel's HUB75 port -- no wiring. |
| 5V 4A power supply | Panel power | The panel can pull up to 4A at full white. Adafruit's 5V 4A regulated adapter (linked from the panel page) is the safe pick. USB-C alone is fine for programming, not for bright animations. |
| USB-C **data** cable | Programming | Charge-only cables won't show the CIRCUITPY drive. |
| Soldering iron (5 min) | One jumper | 64x64 panels need the **Address E solder jumper** closed on the Portal (blob the middle pad to "8" -- matches Adafruit panels). Both M4 and S3 need this. |
| M3 screws/spacers (optional) | Mounting | Panel has M3 mounting holes. |
| Diffuser acrylic (optional) | Looks | Adafruit's learn guide has a "LED Matrix Diffuser" page -- makes pixel art look much nicer. |

**Assembly** (from the [MatrixPortal M4 learn guide](https://learn.adafruit.com/adafruit-matrixportal-m4); S3: https://learn.Adafruit.com/adafruit-matrixportal-s3?view=all):
1. Close the Address E jumper (solder blob, middle pad -> 8).
2. Peel the amber protective tape off the two power standoffs.
3. Screw the panel power cable's spade connectors in: **red -> +5V, black -> GND**.
4. Plug a 4-conductor power plug into the panel's power header (one way only).
5. Plug the Portal into the **left** shrouded HUB75 connector, white arrow on the panel pointing **up and right** -- the Portal overhangs the panel edge so the buttons stay reachable.

## 2. CircuitPython setup

1. The Portal ships with a demo; to (re)install CircuitPython: download the `.uf2` for `matrixportal_m4` / `matrixportal_s3` from circuitpython.org, double-tap the reset button (MATRIXBOOT drive appears), drag the `.uf2` on. A `CIRCUITPY` drive appears.
2. Copy `hardware/code.py` to the drive as **`code.py`** (it runs on boot).
3. Copy `settings.toml.example` as **`settings.toml`** and fill in WiFi + HA token (HA: your profile -> Security -> Long-lived access tokens).
4. Libraries: grab the CircuitPython bundle matching your version and copy these `.mpy` files into `lib/`: `adafruit_requests.mpy`, plus on M4 only `adafruit_esp32spi/` and `adafruit_bus_device/`.

## 3. Playing in the virtual display (before hardware arrives)

The `sim/` folder is a tkinter window that emulates the 64x64 panel using the
**same displayio primitives** (`Bitmap`, `Palette`, `TileGrid`, `Group`) as the
real firmware -- animation code ports almost unchanged (see mapping below).

```bash
python3 sim/fish_tank.py   # the fish tank (opens a window on your Mac)
python3 sim/ha_status.py    # HA-driven modes with mock sensor data

# Custom pixel density (defaults to 64x64) and window zoom:
python3 sim/fish_tank.py --width 32 --height 32 --scale 12
python3 sim/ha_status.py --width 96 --height 48
```

Each LED renders as a separate dot with a dark gap between pixels, like the
real panel -- not one continuous image.

`ha_status.py` cycles through mock HA states every 9 seconds so you can preview
each behavior: calm tank (low humidity) -> rain + humidity readout (high
humidity) -> washing-machine animation (washer running).

### Sim -> hardware API mapping

| Virtual sim (`sim/virtual_matrix.py`) | Real CircuitPython |
|---|---|
| `vm.Bitmap(w, h, n)` | `displayio.Bitmap(w, h, n)` |
| `vm.Palette(n)` | `displayio.Palette(n)` |
| `vm.TileGrid(bmp, pal, x, y)` | `displayio.TileGrid(bmp, pixel_shader=pal, x=x, y=y)` |
| `vm.Group()` | `displayio.Group()` |
| `VirtualDisplay(...).show(group)` | `FramebufferDisplay(matrix).show(group)` |
| `vm.draw_text(...)` (3x5 font) | `adafruit_display_text.label.Label` + `terminalio.FONT` |
| `MockHA.poll()` | `adafruit_requests` GET to `/api/states/<entity>` |

## 4. How the HA integration works

`hardware/code.py` polls HA's REST API every 30s (same LAN, no cloud):

```
GET http://<ha>:8123/api/states/sensor.bathroom_humidity
Authorization: Bearer <long-lived token>
```

Mode logic (edit to taste):
- washer == "on" -> washer animation (TODO in code.py -- the icon scene lives in `sim/ha_status.py` waiting to be ported)
- humidity >= 70 -> rain scene, drop count scales with humidity + numeric readout
- otherwise -> fish tank

If WiFi/HA is unreachable it just stays a fish tank. No crashes, no blocking.

## 5. Ideas to try next

- More fish behaviors: schooling, food pellets on tap (the Portal has an accelerometer -- tap the panel to feed them)
- Washer "done" celebration when the vibration sensor goes quiet
- Night mode: dim via `display.brightness` after bedtime (read from HA)
- Weather mode: pull forecast from HA's weather entity
- GIF backgrounds: the S3's 8MB flash can store real GIFs (`adafruit_imageload`)
