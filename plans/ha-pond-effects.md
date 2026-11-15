# Home Assistant effects in the pond

## Context
The pond already reads CO2, temperature and humidity from HA, and the CO2 level dims the creature palette. This plan makes the house show up in the pond itself:

1. **CO2 → saturation.** Bad air drains the color out of the pond instead of dimming it. The brightness shift is removed.
2. **CO2 → speed.** One global speed factor slows every moving thing (fish, boids, visitors) as the air gets worse.
3. **Washer → electric eel.** While the washing machine draws more than 10 W, a very fast electric eel darts around the pond.
4. **3D printer → lily pad.** While the printer draws more than 10 W, a lily pad with a tiny 3D printer on it drifts across the surface.
5. **House power → zaps.** Sparks of electricity jump between neighbouring boids, more often the more power the house uses, read from a total-power helper entity in HA.
6. **Display sleep.** An HA helper turns the panel off. While it's off, the board stops rendering and stops the physics, and runs only what has to keep going: the lifecycle, saves and the HA poll, which it needs to notice when to wake.

The washer and the printer are both on smart plugs that report power, so both conditions are a watts threshold. This replaces the "Special fish driven by HA conditions" and "Electricity zapping between boids" sketches in `persistence-and-fish-variation.md` (Future ideas). The two reserved palette slots go to the eel and the zaps.

Rules carried over from the earlier plans:
- No per-frame work when a sensor value hasn't changed. Saturation is a palette rewrite on a step change, not a per-creature cost.
- Visitors (the eel and the lily pad) come from HA, not from the save. They are never persisted, never age and never breed.
- Off-screen now and then is fine. No extra steering to keep anything on the panel. Simple tuning like wall margins is enough.

## Configuration (`settings.toml`)

| Key | Meaning |
|---|---|
| `HA_WASHER_POWER_ENTITY` | Washer power sensor, in W. Replaces the unused `WASHER_ENTITY` |
| `WASHER_ON_WATTS` | Above this the washer counts as running. 1–500, clamped, default 10 |
| `HA_PRINTER_POWER_ENTITY` | 3D printer smart plug power sensor, in W |
| `PRINTER_ON_WATTS` | Above this the printer counts as on. 1–500, clamped, default 10 |
| `HA_TOTAL_POWER_ENTITY` | The HA helper that sums the house's power, in W |
| `ZAP_MIN_WATTS` | No zaps at or below this. 0–20000, clamped, default 300 |
| `ZAP_MAX_WATTS` | Zaps reach their top rate at or above this. 100–50000, clamped, default 5000 |
| `HA_DISPLAY_ENTITY` | An `input_boolean` helper, e.g. `input_boolean.pond_display`. `on` shows the pond, `off` puts it to sleep |

- `config.py`: `washer_on_watts`, `printer_on_watts`, `zap_min_watts` and `zap_max_watts` as `clamped_int` wrappers. If `ZAP_MAX_WATTS ≤ ZAP_MIN_WATTS`, the max is set to min + 100.
- The zap range is a setting because it depends on the house. The off delays and the top zap rate are module constants, to keep the file short.
- 10 W is the default for both plugs. M3 measures each one's idle and running draw and records it here, and the defaults change if 10 W turns out wrong.
- Update `settings.toml.example` and the README's settings table. Remove `WASHER_ENTITY` and the commented `HA_POWER_ENTITIES` line.

## Sensors

### Extra entities — `home/ha_client.py`
- Add `EXTRA_ENTITIES`:
  ```python
  EXTRA_ENTITIES = (
      ("washer_power", "HA_WASHER_POWER_ENTITY"),
      ("printer_power", "HA_PRINTER_POWER_ENTITY"),
      ("total_power", "HA_TOTAL_POWER_ENTITY"),
      ("display", "HA_DISPLAY_ENTITY"),
  )
  ```
  `from_settings` polls them after `READOUT_ENTITIES`. Unset keys are skipped, as today.
- Their values land in `sensors.values` like the others, so `scene.set_sensors` sees them with no new wiring in `App`.
- `readout.sensor_lines` keeps showing only CO2, temperature and humidity.
- Seven entities per poll cycle instead of three. The client fetches one at a time, so the cost is more frames with a small step each, not a longer stall. At the default 5 s interval a visitor shows up within one or two polls. Check in M3 that a full cycle still fits in the interval. If it doesn't, the cycle just starts late, which is fine.

### Fakes — `home/fake_sensors.py`
- Add `washer_power`, `printer_power` and `total_power` keys.
- By default they cycle slowly so a headless simulator run shows every effect:
  - washer: on for 60 s of every 180 s, with random 0–8 W while "off" and 20–500 W while "on" (including a few dips under 10 W, to exercise the off delay)
  - printer: on for 90 s of every 240 s, 3–6 W while off and 80–250 W while on
  - total power: a sweep from 150 W to 6000 W and back every 300 s, like the CO2 sweep
- Simulator keys: **W** toggles the washer, **P** toggles the printer, and **[** / **]** set the total power by hand in 500 W steps. Each one stops that value's cycle (like +/- for CO2). **0** resumes every cycle.
- `display` is `"on"` and doesn't cycle. **D** toggles it.

### Conditions — `scenes/visitors.py`
```python
def watts(entry):
    """The entry's state as a float, or None if missing or not a number
    ("unavailable", "unknown")."""

def above(entry, on_watts):
    """True when watts(entry) is above on_watts. No number -> False."""
```
- Both plugs report watts, so one threshold check covers the washer and the printer. `watts` is shared with the zaps.
- **Hysteresis.** A washer drops to a few watts during soaks and pauses, and a printer's power swings as the heaters cycle. So a visitor *arrives* as soon as its condition is true, but only *leaves* after the condition has been false for its off delay:
  - washer: `WASHER_OFF_SECONDS = 60` (was 5 min, which felt like the eel never left; see M4)
  - printer: `PRINTER_OFF_SECONDS = 60`
- The timer runs on the scene's `update(dt)`, not on poll times, so it keeps counting if HA goes quiet. Unavailable counts as false, so a dead sensor makes the visitor leave after the delay rather than stay forever.

## CO2 → saturation — `creatures/colors.py`

- **Desaturate toward each color's own luma**, so a color goes gray without changing much in brightness:
  ```python
  luma = (r * 77 + g * 150 + b * 29) >> 8     # integer, no floats
  r2 = luma + (r - luma) * step // FULL_STEP   # same for g, b
  ```
  `set_saturation(palette, step)` replaces `set_brightness`. It's the same one write per slot, from `BASE_RGB`.
- **Mapping.** The CO2 → step curve stays (1.0 at ≤ 800 ppm, linear to the minimum at ≥ 2000 ppm, whole tenths), but the minimum becomes `MIN_SATURATION_STEP = 2`. That's not 0, because a fully gray pond loses the difference between kohaku red and white, and between species. Tune on the panel.
- **Refactor**: `co2_step(values)` becomes `co2_level(values)`, which returns 0–10 badness tenths (0 = clean air, 10 = at or above `CO2_DIM`, unavailable = 0). Saturation and speed (below) each map that level to their own range, so the thresholds live in one place.
- **Water too.** Store the water slots' RGB after `dim_palette` and desaturate them with the same step. A gray pond says "stale air" much more clearly than gray fish in blue water. `DESATURATE_WATER = True` is a module flag. At `POND_BRIGHTNESS = 0.1` the water values are tiny (≤ 0x19), so check on the panel that the shift is visible and doesn't band. If it doesn't look right, turn the flag off.
- **The eel's flicker slot and the zap slot** (below) are written every frame while they're in use. They run their colors through the same `desaturate(rgb, step)` helper, so they go gray with everything else.
- `CreatureColors` becomes `PondColors` (it now owns water slots too). `set_sensors` rewrites the palette only when the step changes, as today.

## CO2 → speed

- **Slow motion, not lower speed limits.** The scene keeps one `speed` factor and passes `dt * speed` to every behavior. Velocities stay in px/s and the steering doesn't change, so every behavior just runs slower. Fins, tails and the spine follow-the-leader are position-driven, so they slow with it. Nothing in `SwimBehavior`, `FlockingBehavior` or `WanderBehavior` needs to change.
- **What does *not* slow down**:
  - the lifecycle clock (`Pond.update` splits into the real `dt` for aging and `motion_dt` for its behaviors), so bad air doesn't make fish live longer
  - the water animation (`update_pond(dt)`)
  - the visitor off-delay timers
  - the zap rate: power use is real time, not pond time
- **Mapping.** `speed = 1.0` at level 0, down to `MIN_SPEED = 0.4` at level 10, in tenths. Tune on the panel.
- **Easing.** The target changes in 0.1 jumps once per poll, which would show as a sudden slowdown. The scene eases toward it: `speed += (target - speed) * min(1, dt * SPEED_EASE)` with `SPEED_EASE = 0.5`, so a step takes a few seconds. One multiply per frame.
- The eel and the lily pad are slowed too ("all fish"). The eel stays far faster than anything else, even at 0.4.

## Visitors — `scenes/visitors.py`

A visitor is a creature that HA calls in. One record per visitor, so a third one later is one table entry plus its look:

```python
class Visitor:
    """name, condition(values) -> bool, off_seconds, build(canvas, w, h) -> (behavior, creature)"""
VISITORS = (
    Visitor("eel", washer_running, WASHER_OFF_SECONDS, build_eel),
    Visitor("lily", printer_on, PRINTER_OFF_SECONDS, build_lily_pad),
)
```

- **State per visitor**: `away → arriving/present → leaving → away`.
  - **Arrive** (condition true): build the behavior and the creature, place it just outside a random edge (`outside_window_size` past it, inside the walls), and `add` it. The walls push it in, so it swims or drifts in on its own.
  - **Leave** (condition false for `off_seconds`): turn its walls off (`behavior.walls = False`, see below) so it wanders out. Once it's fully off screen (past `render_margin`), `remove` it and drop the behavior.
    - Fallback: if it's still on screen after `LEAVE_TIMEOUT = 20` s, remove it anyway. That's one pop, rare enough to accept, and better than turning it toward an edge with more steering code.
  - If the condition turns true again while it's leaving, it turns its walls back on and stays.
- Each visitor has its own behavior with a single creature. It's built on arrival and dropped on removal, so an absent visitor costs nothing per frame.
- **`walls` switch** on `SwimBehavior` (default `True`). When it's `False`, `_steer` skips the wall avoidance and `WanderBehavior` skips its wall look-ahead. That's one branch per creature, and it's only on in the visitor behaviors.
- **Not persisted, not in the lifecycle.** Visitors live in the scene, not in `Pond`, and their species are not in `SPECIES_BY_NAME`, so a `state.json` can't load an eel as a pond fish. After a restart, a running washer brings the eel back on the first poll.
- **Draw order**: water → eggs → pond fish → boids → zaps → eel → lily pad. The lily pad floats on the surface, so everything swims under it.

### Electric eel (washer)
- **Body**: a `Species` record (`lifecycle=False`, `persist=False`) built with `SpineCreature` and no genome, using `size`, `variety` and `seed` directly.
  - 14 joints, narrow (`widths` ≤ 4), long and flexible (a larger `angle_limit` than the sturgeon), so it whips when it turns.
  - Parts: `Tail` only. Its long ventral fin is too fine to show at this scale.
- **Look**: a dark `SLATE` body with two rows of `ELECTRIC` spots along the flanks (a `line` zone, like the sturgeon's `SCUTES`). This uses no new mode.
- **`ELECTRIC` takes reserved slot 14.** Slot 15 goes to the zaps.
  - **Flicker**: every frame the scene writes slot 14 from a short table (cyan-white, pale yellow, dim blue, with an occasional full-white flash), picked by a cheap counter plus `random` every 2–3 frames. The table goes through `desaturate()`.
  - That's one palette write per frame, and only while the eel is present.
- **Motion**: `Wander` with `cruise_speed ≈ 60`, `max_speed ≈ 80` (3–4× the koi), high `turn_ease`, low `pause_chance`, short target timers. Lots of darting and sudden turns.
  - At 14–16 fps, 60 px/s is about 4 px per frame. Check that it reads as fast rather than jumpy. If it jumps, lower the cruise speed and raise the turn rate, which looks frantic without the big hops.

### Lily pad with a 3D printer (printer)
- **Not a fish.** `LilyPad` is a small `Creature` whose `render` blits a pre-drawn sprite centred on its position. It has no spine and doesn't turn. `set_state` just stores x, y.
- **Sprite** (pre-drawn once, like the egg): a ~13 px `OLIVE` pad with the classic notch, plus a ~6 × 6 px printer on top: a `BLACK` frame, a `SLATE` gantry and a `RED` or `GOLD` print on a `WHITE` bed. No new palette slots.
  - **Two frames** with the print head one pixel apart, swapped every 0.5 s, so it's visibly printing. That's still one blit per frame.
- **Motion**: `Wander` with `cruise_speed ≈ 2–3`, a high `pause_chance` and slow turns, so it drifts. A smaller `outside_window_size` keeps it mostly on screen by tuning alone.
- Cost: one sprite blit (≈ 0.3 ms, like the shell) plus one Wander creature.

## House power → zaps — `scenes/effects.py`

- **Rate**, computed in `set_sensors` only when `total_power` changes:
  ```python
  # 0 at or below ZAP_MIN_WATTS, rising on a log scale to ZAP_MAX_RATE at ZAP_MAX_WATTS
  rate = ZAP_MAX_RATE * log(w / lo) / log(hi / lo)    # clamped to 0..ZAP_MAX_RATE
  ```
  `ZAP_MAX_RATE = 10` zaps per second. A log scale because house power spans a few hundred watts idle to several kW with the oven on, and each doubling should look like a similar step up. No number (unavailable) → 0.
  - If `ZAP_MIN_WATTS` is 0, `lo` is 1 W, so the log stays defined.
- **Effects layer.** After the boids draw, the scene runs a short list of effects. Draw order becomes water → eggs → fish → boids → **zaps** → eel → lily pad. Later ambient effects (bubbles, ripples) can go in the same list without touching the behaviors.
- **`ZapEffect(flocks)`**, once per frame with the real `dt`:
  - Accumulate `rate × dt`. For each whole zap due, at most `MAX_NEW_ZAPS = 2` per frame, pick a random flock and a random **on-screen** boid in it, then its nearest flockmate within `ZAP_REACH = 12` px (`FlockingBehavior.nearest(i, reach)`). No flockmate in reach means no zap: the accumulator is spent and nothing is drawn. Sparks only jump between boids that are actually close.
    - The `random` draw is what makes the timing irregular. At 0.5/s a spark comes every couple of seconds, not on a metronome.
  - Each zap lives 1–2 frames and holds the two boid **objects**, not indices, because `remove` swap-moves indices. Boids are never removed today, but holding objects keeps it safe. Each frame it's drawn between their current positions, so it follows them.
  - **Drawing**: a jagged line of 2–3 `bitmaptools.draw_line` segments between the two boids, with the midpoints nudged ±1 px at random, in the `ZAP` slot.
- **`ZAP` takes reserved slot 15**: a pale blue-white, brighter on a zap's first frame than its second, through `desaturate()`. That's one palette write per frame while any zap is live, and none otherwise.
- **Cost.** A line is about 0.2 ms on the board (OPTIMIZATIONS.md "M5.5"), so a zap is about 0.5 ms per frame it's shown. At the top rate and ~15 fps that's under one new zap a frame, so about 0.5–1 ms a frame on average, and `MAX_NEW_ZAPS` caps the worst frame. A quiet house costs nothing, because the accumulator stays at 0.
- **`FlockingBehavior.nearest(i, reach)`**: a scan of the flock's 10 boids (all three flocks are under `grid_min_boids`), comparing squared distances. Above `grid_min_boids` it would be a 3×3 grid lookup instead. It's called only for a due zap, not per frame.

## Display sleep — `app.py`, `hardware/code.py`

**Where the power goes, and what sleep can and can't save.** This sets expectations before building it:
- **The LEDs** are the biggest variable draw. The pond is dim (water at 10 %), so they likely draw less than you'd guess, but they're still the main thing to cut.
- **The panel scan.** Even an all-black frame keeps the HUB75 drivers clocking and the board's matrix interrupt running, so a black frame alone isn't "off". `matrix.brightness = 0` **pauses** the scan in CircuitPython's `rgbmatrix` (the panel goes dark and the interrupt stops), which is what we want. M7 confirms this with a USB power meter.
- **The CPU.** Running flat out at ~15 fps is the next cost. Sleeping in `time.sleep` between ticks lets the ESP32-S3 idle, so sleep ticks at `SLEEP_HZ = 10` instead of rendering frames.
- **WiFi stays on**, and it's a large part of what's left (on the order of 0.3–0.5 W with the chip). It can't go off, because the board has to poll HA to learn when to wake. Deeper options (deep sleep, the radio off between polls) would break the non-blocking HA client and the lifecycle clock, so they're out of scope. Measure first; if what's left is still too much, revisit.

**Physics off too.** Nobody can see the fish while the panel is dark, so there's no reason to move them. Skipping physics and rendering together is what lets the CPU idle. On wake, everything resumes exactly where it stopped, which looks fine. Fish that were born or died during sleep are simply there or gone.

**What keeps running while asleep:**

| Keeps running | Why |
|---|---|
| Lifecycle (aging, births, deaths, eggs) | It's the pond's real clock, and the point of the feature |
| `Store.tick` | Lifecycle changes still get saved |
| HA poll (every entity) | To notice the wake. Polling all of them keeps the CO2, visitor and zap state current, so the pond is right the moment it wakes |
| Visitor off-delay timers | So a washer that finished an hour ago doesn't bring the eel back on wake |
| Buttons | To wake locally (below) |

The water animation, the behaviors, the zaps, the eel flicker, the text panels and `display.refresh` all stop.

**The condition.**
- Asleep only when the state is exactly `off`. Anything else (`on`, `unavailable`, an unset key, no WiFi, no reading yet) means awake. **Fail open**: if HA is down, you want to see the pond and its `NO WIFI` / offline status line, not a dark panel that looks broken.
- So after a reboot the board shows the pond for the few seconds until the first poll, then goes dark if the helper is off. That's acceptable, and no sleep state is saved.
- **Wake latency** is up to one poll interval plus a poll cycle. At 10 Hz the client still advances one step per tick, so seven entities take a few seconds: expect about 5–10 s at `HA_POLL_SECONDS = 5`. If that's too slow, lower the poll interval, which costs little since each step is small.

**Local wake (an addition; push back if you don't want it).** Any button press while asleep wakes the panel for `WAKE_SECONDS = 300`, even though the helper is still `off`. Standing in front of a dark panel and having to open HA to see it seems wrong. The press only wakes; it doesn't also open the menu. After the timeout it goes back to sleep if the helper is still off. The board doesn't write the helper back to HA, which keeps the client read-only.

**On the HA side** (not code in this repo): driving the helper from an automation, e.g. off when the room's presence or motion sensor has been clear for 15 minutes and on when it trips, is what makes this "off until we're looking at it". README gets an example automation in M8.

**Wiring:**
- `App.awake` (property): `not (display == "off") or now < wake_until`.
- `App.tick(dt, now)`:
  - Always: `buttons.poll` (a press while asleep sets `wake_until` and is swallowed), `sensors.poll`, `scene_sensors` on change, `store.tick`.
  - Awake: the menu, the text panels and `update_scene(dt)`, as today.
  - Asleep: `scene_background(dt)` only.
- **Scene hook**: `create_scene` may return a fourth element, `background(dt)`, for what has to run while asleep. The pond's is `pond.tick_clock(dt)` (the lifecycle half of `Pond.update`, split out) plus the visitor timers. A scene without one simply freezes while asleep.
- **On the edges**, `App` calls `set_display(on)`, passed in by the runner like `set_rotation`:
  - hardware: `matrix.brightness = 0.0` or `1.0`
  - desktop: the virtual display shows black
- **The runner's loop** reads `app.awake`. When it's `False`, it skips `display.refresh()` and sleeps to `1 / SLEEP_HZ` instead of the frame time. `DEBUG` prints a `sleep` line every 30 s instead of the fps line.
- On wake, the first `dt` is at most 0.1 s (one sleep tick), so nothing jumps.
- Sleeping during a pending save is fine: `Store.tick` keeps running.

## Scene wiring — `scenes/pond.py`
- `create_scene` builds `PondColors`, the `Visitors(VISITORS, canvas, width, height)` manager, the `ZapEffect` over the boid flocks and the speed state.
- `set_sensors(values)`: CO2 level → saturation step + speed target, each visitor's condition, and total power → zap rate.
- `create_scene` returns a fourth element, `background(dt)`, which `App` calls instead of `update` while asleep:
  ```python
  def background(dt):
      pond.tick_clock(dt)      # lifecycle only: aging, births, deaths, eggs
      visitors.tick_timers(dt) # off delays keep counting
  ```
- `update(dt)`:
  ```python
  speed += (target - speed) * min(1.0, dt * SPEED_EASE)
  motion_dt = dt * speed
  update_pond(dt); draw_pond(canvas)
  pond.update(dt, motion_dt)
  for flock in boid_flocks: flock.update(motion_dt)
  zaps.update(dt)                  # real time: power use doesn't slow with CO2
  visitors.update(dt, motion_dt)   # timers on dt, behaviors on motion_dt, eel flicker
  ```

## Milestones (each one is a separate, testable commit)

**M1: CO2 → saturation.**
- `co2_level`, `desaturate`, `set_saturation` and `PondColors` with the water slots. Remove `set_brightness` and the brightness steps.
  - Done: `saturation_step(level)` maps the level, and `PondColors.set_step` writes the 14 slots (6 water + 8 creature) only on a change. On the desktop at 2200 ppm, kohaku red stays distinct from white. **On the panel the colors look good, water included, so `DESATURATE_WATER` stays on.**
- *Check:*
  - In the simulator, +/- through 800–2000 ppm takes the pond from full color to nearly gray. Kohaku red and white stay distinguishable at the lowest step.
  - On the panel, the water's desaturation is visible and doesn't band. If it does, set `DESATURATE_WATER = False` and note why here.
  - Palette writes happen only on a step change (count them in the simulator).

**M2: Global speed factor.**
- `speed` in the scene, eased; `Pond.update(dt, motion_dt)`; boids on `motion_dt`.
  - Done: `speed_for_level(level)` in `scenes/pond.py`, `Pond.tick_clock(dt)` split out of `Pond.update` (M7 reuses it). Headless at 2000 ppm: boids move at 0.39× (36.4 → 14.1 px/s), the ease reaches 0.45 in ~5 s, pond hours per 20 s are the same (20 vs 20) at 400 and 2000 ppm, and the flocks hold together (mean distance to flock centre 5.9 px → 7.6 px). On the board, `DEBUG` frame time is unchanged from OPTIMIZATIONS.md's M8 run: 10.2–10.7 fps (M8 10.0–10.7), physics 38.7–41.6 ms (37.4–40.3), render 33.6–40.9 ms (36.9–41.8), refresh 15.6–17.0 ms (15.4–16.2). Physics is ~1 ms up at most, within the noise.
- *Check:*
  - At 2000 ppm everything moves at about 0.4× and the change eases in over a few seconds.
  - With `POND_TIME_SCALE`, aging runs at the same rate at 400 and 2000 ppm.
  - Flocks still hold together at 0.4× (the `steer_dt` half-rate path).
  - `DEBUG` frame time is unchanged.

**M3: Extra entities + conditions.**
- `EXTRA_ENTITIES`, the new config keys, `watts` / `above` and the hysteresis timers, plus the fake keys with W/P/[/] and the slow cycles. No visitors or zaps yet: print `visitor: eel arrive/leave` and `zaps: N.N/s` on the console.
  - Done (desktop): `Visitor` / `Visitors` in `scenes/visitors.py` hold the condition and the off timer (`tick_timers(dt)` on the real dt, ready for M7's `background`); `zap_rate` in `scenes/effects.py`. The washer fake is **on 120 s of every 600 s**, not 60 of 180: 120 s off is shorter than the 5 min off delay, so the eel never left. Headless over 1300 s: the eel leaves 300 s after the last read above 10 W (dips included), the lily pad 60 s after, and the zap print follows the sweep (300 W → 0, 1 kW → 4.3/s, 2 kW → 6.7/s, 5 kW → 10/s). The readout still shows the three values. On the board: the arrive/leave prints follow the real washer and printer, and the zap rate follows the `total_power` helper. The zap print was too noisy (it changes on most polls), so it's gone; M6 shows the rate as sparks. `DEBUG` with all seven entities: 9.8–10.4 fps (M2 10.2–10.7), physics 42.2–42.4 ms (38.7–41.6), render 33.5–38.5 ms (33.6–40.9), refresh 15.4–16.3 ms (15.6–17.0), net 3.8–4.8 ms per frame on average with a 47–50 ms worst frame, and `ha ok` stays at 0–1 s, so a full poll cycle fits in the 5 s interval. Physics is ~1–3 ms up, about the noise. Plug idle/running watts still to measure.
- *Check:*
  - **Measure both plugs** and record the numbers here: washer idle, soak dips and running draw; printer idle (on, not printing), heating and printing draw. Confirm that 10 W separates idle from running for both, and that 60 s (washer and printer) rides over the dips. Adjust the defaults if not.
  - On the board with the real washer and printer, the arrive/leave prints follow them, with the eel's leave coming 1 min after the washer stops.
  - The `total_power` helper reads as a number, and the zap rate print follows it.
  - The readout still shows only the three values.
  - A missing entity key or an unavailable sensor never brings a visitor.

**M4: Visitors + electric eel.**
- `Visitor` manager, `walls` switch, eel species and look, the `ELECTRIC` slot and its flicker.
  - Done (desktop): `build(canvas, w, h)` returns the behavior. Its one creature is `behavior.creatures[0]`. The eel's spine is laid out behind its heading at the entry point, so at the top edge it doesn't hang onto the screen. 14 joints at link 2.5 (about 32 px), widths ≤ 4, `angle_limit` π/6. Only `WanderBehavior` honours `walls`, which is all the visitors use. The flicker picks a new color every 2–3 frames, not every frame, so it writes the palette less often. At 2200 ppm the table goes gray-blue and off-white. **Walls tuned**: at `outside_window_size` 20 the eel's head was on screen only 60 % of the time, so it's now 5, with `wall_avoid_distance` 30, for 96–97 %. Headless, 40 leaves: every one swam off on its own in 4.1 s on average (6.7 s max), with no timeouts. A returning washer turns the walls back on (`visitor: eel stays`), and an unavailable sensor makes it leave after the delay. `bench_render.py` on the desktop: eel 0.25 ms full (18 discs, 11 spots). **Washer off delay cut to 60 s**: at 5 min the eel seemed never to leave in the simulator. The washer fake goes back to on 60 s of every 180 s, so the eel comes and goes every 3 minutes. Still to check on the board: the flicker, the bench row, and `DEBUG` with and without the eel.
- *Check:*
  - The eel swims in from an edge, darts around, and leaves off screen after the off delay. The timeout fallback works (force it with a tiny `LEAVE_TIMEOUT`).
  - The flicker reads as electric on the panel and goes gray with high CO2.
  - `bench_render.py` gets an eel row. `DEBUG` fps is recorded with and without the eel (OPTIMIZATIONS.md).

**M5: Lily pad with a 3D printer.**
- `LilyPad` creature, its two-frame sprite, the drift motion.
  - Done (desktop): `creatures/lily_pad.py`, a 13 × 13 sprite drawn from ASCII art (`ART`, frame B moves the `WHITE` head one pixel along the `SLATE` gantry) with the printer's inside filled `BLACK`, so the bed and the print stand out against the pad. The print is `RED` or `GOLD`, picked on arrival. The head swaps every 0.5 s on `motion_dt`, so it slows with the CO2 too: `Visitor.animate` is now `animate(behavior, motion_dt)`. **Drift tuned** headless (40 runs): `max_turn` 0.15, `pause_chance` 0.2, cruise 3 px/s, walls 8 px out with a 20 px soft push. Fully on screen 86 % of the time, partly the rest, never fully off. It's in view about 4 s after arriving. Gentle turns keep its heading, so with walls off it drifts out instead of circling (18 s median, 37 s max in clean air). That's still well past the eel's 20 s timeout, so the timeout is now per visitor: `LILY_LEAVE_TIMEOUT = 90`. At the 0.4 speed floor a few leaves take longer (50 s median, 118 s max) and pop. Fish swim under it (draw order: eel, then lily). `bench_render.py` on the desktop: lily pad 0.18 ms full (one blit). **On the board** the printer is recognisable enough as drawn. `bench_render.py`: lily pad 0.20 ms full, tick 0.03 ms (the eel, for M4: 2.26 ms full, body 1.05 ms for 18 discs, spots 0.75 ms, spine 0.57 ms, about a kohaku plus a sturgeon's spots). `DEBUG` with the pad: 9.7–10.4 fps (M3 9.8–10.4), physics 41.4–44.8 ms (42.2–42.4), render 36.0–40.2 ms (33.5–38.5), refresh 14.2–14.8 ms (15.4–16.3), net 2.6–3.7 ms with a 48 ms worst frame. Render is ~2 ms up at most, within the noise of the fish on screen at the time, against 0.2 ms for the blit.
- *Check:*
  - The printer is recognisable at 64 × 64 (adjust the art on the panel).
  - The pad drifts in, mostly stays visible, and fish swim under it.
    - Its render cost is recorded.

**M6: Zaps between boids.**
- `ZapEffect`, `FlockingBehavior.nearest`, the `ZAP` slot, the effects list in the scene and the zap config keys.
- *Check:*
  - With the simulator's [ / ], nothing at 300 W, an occasional spark around 1 kW, and a busy crackle at 5 kW and above.
  - Sparks jump between visibly close boids and follow them for their 1–2 frames.
  - On the board, record `DEBUG` frame time at 0, 3 and 10 zaps/s (OPTIMIZATIONS.md). At 0 it must equal M5.
  - Set `ZAP_MIN_WATTS` / `ZAP_MAX_WATTS` from the house's real idle and busy totals, and record them here.

**M7: Display sleep.**
- `HA_DISPLAY_ENTITY`, `App.awake`, the `background` scene hook, `Pond.tick_clock`, `set_display` on both runners, the slow loop, the local button wake and the D key.
- *Check:*
  - **Measure** with a USB power meter and record it in OPTIMIZATIONS.md: the pond awake (dim and bright scenes), awake with an all-black frame, and asleep. This shows what pausing the scan and idling the CPU each save. Confirm `brightness = 0` really pauses the scan (a visible drop from the black-frame number). If it doesn't, try `matrix.deinit()` / re-create on wake instead.
  - With `POND_TIME_SCALE`, fish age, breed and die while asleep. On wake the population matches, and the saves happened.
  - Wake within ~10 s of flipping the helper. A button wakes for 5 minutes and doesn't open the menu.
  - Unavailable helper, an unset key or no WiFi → awake.
  - A washer that stopped during sleep doesn't bring the eel back on wake.

**M8: Docs.**
- README: the new settings, the W/P/[/]/D simulator keys, what each effect means, and an example HA presence automation for the display helper. `persistence-and-fish-variation.md`: point its "Special fish" and "zapping" ideas at this plan. OPTIMIZATIONS.md: the M4–M7 numbers.

## Open questions
- **Saturation and speed floors** (0.2 and 0.4) are guesses to tune on the panel.
- **Zap range** (300 W–5 kW) is a placeholder until M6 reads the house's real totals.
- **Sleep savings** are unknown until M7 measures them. WiFi has to stay on, so the board's floor is set by the chip and the radio, not by the code.

## Files

| File | Change |
|---|---|
| `src/config.py` | `washer_on_watts`, `printer_on_watts`, `zap_min_watts`, `zap_max_watts` |
| `src/hardware/settings.toml.example` | New keys, drop `WASHER_ENTITY` and `HA_POWER_ENTITIES` |
| `src/home/ha_client.py` | `EXTRA_ENTITIES` |
| `src/home/fake_sensors.py` | Washer/printer/total power fakes, W/P/[/] keys |
| `src/creatures/colors.py` | Saturation, `co2_level`, `PondColors`, `ELECTRIC` and `ZAP` slots |
| `src/creatures/species.py` | `ELECTRIC_EEL` (not registered) |
| `src/behaviors/swim.py`, `wander.py`, `flocking.py` | `walls` switch; `FlockingBehavior.nearest` |
| `src/scenes/effects.py` | New: `ZapEffect` |
| `src/behaviors/lifecycle.py` | `Pond.update(dt, motion_dt)`, `Pond.tick_clock(dt)` |
| `src/app.py` | `awake`, `set_display`, the `background` hook, button wake |
| `src/hardware/code.py`, `src/run.py`, `src/simulator/virtual_matrix.py` | `set_display`, the slow loop while asleep |
| `src/scenes/visitors.py` | New: `Visitor`, conditions, manager, eel and lily pad builders |
| `src/creatures/lily_pad.py` | New: `LilyPad` creature and sprite |
| `src/scenes/pond.py` | Speed factor, visitors, draw order |
| `src/bench_render.py` | Eel and lily pad rows |
| `README.md`, `OPTIMIZATIONS.md`, `plans/persistence-and-fish-variation.md` | Docs |
