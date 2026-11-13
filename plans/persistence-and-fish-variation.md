# Persistence and fish variation

## Context
The pond has one hard-coded koi type drawn in a single color, plus the background boids. Menu settings reset on every boot. This plan adds:

- **Species**: koi, catfish, sturgeon and turtle, with room for more. Each species is a data record, not a subclass. A new species is one table entry. Only a new *kind* of part (tentacles, say) needs new code.
- **Fixed color variants with persistent spots.** Each fish has a small fixed set of colors, and its spots stay in the same place on its body. Unlike OpenMatrix, the hue never changes per segment. The only color change is a global brightness shift with CO2.
- **Genomes and a lifecycle.** A fish grows to its own maximum size, which is inherited from its parent with a random variation and capped per species. A parent breeds its own species, with a small chance of a different one. Turtles are slower and live longer.
- **Persistence.** One JSON document holds the menu settings and, as a separate object, the pond genomes.
  - The board saves it to `microcontroller.nvm`, using a dirty flag and a throttle: at most once per `PERSIST_SECONDS`, default 60.
  - The desktop simulator saves the same document to `state.json`.
  - **Editing is restart-only and file-based.** Drop a `state.json` on CIRCUITPY and the board imports it at the next start. The board prints its current state on the serial console so you can pull it, edit it and copy it back. The simulator doubles as a playground for the same file.

The background boids stay ambient, with flat arrays and no genome (see LEARNINGS.md "Background boids"). The one change is that the single flock of 50 becomes **three independent flocks of 10** (M3), so each flock is under `grid_min_boids` and uses the direct neighbour loop.

## Configuration (`settings.toml`)

| Key | Meaning |
|---|---|
| `PERSIST_SECONDS` | Minimum seconds between saves (nvm on the board, `state.json` on the desktop). 10–3600, clamped, default 60 |
| `POND_TIME_SCALE` | Debug only: multiplies the pond's aging clock, so a lifespan can be watched in minutes. Default 1 |

- `config.py`: generalise `poll_seconds()` into `clamped_int(settings, key, default, lo, hi)` and keep `poll_seconds` as a wrapper around it.
- Add both keys to `settings.toml.example`.

## Persistence

### The document
```json
{
  "v": 1,
  "settings": {"rotation": 90, "sensors_on": true},
  "pond": {"next_id": 7, "fish": [
    {"id": 3, "species": "koi", "colors": 2, "seed": 40213, "max_size": 92, "age_hours": 51, "offspring": 1}
  ]}
}
```
- `v` is the schema version.
- `App` owns `settings` and `Pond` owns `pond`. The document is assembled only at save time, so building it allocates about once a minute, not per frame.
- **Loading** (`persist/document.py`) puts defaults first, then overlays each known field, as in LEARNINGS.md:
  - Missing keys get defaults, so old saves keep working when fields are added.
  - Unknown keys and invalid fish are dropped: unknown species, out-of-range `colors`, non-integers. Each drop is printed on the serial console with the reason.
  - Sizes are clamped to the species range.
  - An unparseable document means defaults.
- Size: about 120 bytes per fish × 20 fish + settings ≈ 2.5–3 KB of compact JSON.
- Pretty-printed (indented) when dumped or written to the desktop file, so it's easy to edit. Compact in nvm.
  - CircuitPython's `json.dumps` has no `indent`, so `document.dumps(pretty=True)` is a small hand-written printer (M2). Objects get one key per line, and each list item is one compact line, so each fish will read as one line.

### Store with dirty flag — `persist/store.py`
- `Store(backend, interval_s)` has `load()`, `mark_dirty()` and `tick(now)`.
- `tick(now)`: if dirty and `now - last_save ≥ PERSIST_SECONDS`, it builds the document, saves it, and clears dirty. Otherwise it does nothing. Callers only set the flag and never block on flash.
- **What marks it dirty**: menu changes, births, deaths, an `age_hours` tick (hourly), and an import. Most minutes nothing is dirty, so nothing is written, which keeps flash wear low.
- There is no immediate save. A change made less than `PERSIST_SECONDS` before a power loss is lost.

### Backends
- **`NvmBackend` (hardware)**: a record of `magic "LPND" | version u8 | import_crc u32 | length u16 | crc32 u32 | JSON bytes`.
  - Bad magic, version or CRC → defaults.
  - Uses `binascii.crc32` if the build has it, otherwise a simple Adler-style sum.
  - `import_crc` is the checksum of the last imported file (see Import).
- **`FileBackend` (desktop)**: `run.py --state PATH`, default `state.json` at the repo root (git-ignored). Writes `PATH.tmp`, then `os.replace`. This file *is* the desktop save. Edit it while the simulator is stopped, because a running simulator overwrites it on its next save.
- **nvm findings** (M1, from `ports/espressif/common-hal/nvm/ByteArray.c` and `mpconfigport.h` on the current `main`, which 10.x matches):
  - Size: `CIRCUITPY_INTERNAL_NVM_SIZE` = 8 KB, stored as one NVS blob (`"data"` in namespace `"CPY"`) in the 20 KB `nvs` partition at 0x9000 (5 pages of 4 KB). `code.py` prints `len(microcontroller.nvm)` at boot to confirm.
  - How it writes: every slice write reads the whole blob, calls **`nvs_erase_all()` first**, then `nvs_set_blob()` with the full 8 KB, then commits. Every slice read also fetches the whole blob. So one slice assignment per save is one blob rewrite, as hoped, but the old copy is erased *before* the new one is written, not after.
  - A/B slots: **not added, because they can't help.** Both slots would live in the same blob, which is erased as a whole. A power loss mid-save leaves the old record, the new one, or no blob at all. No blob reads as zeros, so the magic check fails and the board boots with defaults. A mixed record that passes the CRC can't happen. The only way to get real A/B would be two storage locations (e.g. nvm + a file), and CIRCUITPY isn't writable from code, so we accept the small window.
  - Wear: each save writes ~8 KB of entries whatever the JSON size, so about 2 page erases spread over 5 pages. Flat out (one save every 60 s, 1440/day) that's ~580 erases per page per day, ~170 days to 100k cycles. That's why saves only happen when dirty: menu changes are rare, and with hourly ages plus births and deaths (M9/M10) it's ~30–50 saves/day, i.e. decades. Don't add anything that marks the store dirty every few seconds.
  - Save time: `Store.save` prints `state: saved N bytes in X ms` on the console. Measured on the board: **152.5 ms for the 60-byte settings-only document**, almost all of it the NVS erase + 8 KB rewrite (the JSON is tiny). That's a visible ~5-frame hitch at 30 fps, once per save. Acceptable while saves are rare, but it's another reason to keep dirty events rare, and the cost should stay roughly flat as the pond is added because the whole 8 KB blob is rewritten regardless.

### Import: `CIRCUITPY/state.json` → board
- At startup, if `/state.json` exists, the board reads it and computes its CRC.
  - Same as `import_crc` in nvm → already imported, ignored. The file can stay on the drive without resetting the pond every boot.
  - Different → parse and validate it like any load, then apply it. The imported document replaces the saved one **per section**: a file with only `settings` keeps the saved pond, and a file with only `pond` keeps the saved settings. The board then marks the store dirty with the new `import_crc`.
    - Within a section nothing is merged: a key missing from the imported `settings` gets its default, not the saved value (`document.merge`, M2). Unknown top-level sections are dropped with a printed reason.
  - Unparseable → print the error, keep the saved state, and don't record the CRC, so a fixed file is picked up next time. Also show `BAD STATE.JSON` in the sensor panel's status line for a few seconds.
- The import CRC is saved in the same nvm write as the imported state. If power is lost before that save, the file is simply imported again next boot.
- The code can't write to CIRCUITPY while the PC can, so the board never deletes or rewrites the file. This keeps the USB mode unchanged, with no `boot.py`, and `deploy.sh` keeps working.
- **"Restart" includes auto-reload**: copying a file onto CIRCUITPY makes CircuitPython reload `code.py`, so dropping in a new `state.json` applies it within a second or two without pressing RESET.
- `deploy.sh --state FILE` copies FILE to `CIRCUITPY/state.json`, after `src/` and before `code.py`, like `settings.toml`.

### Export: board → serial → file
- At startup, after loading and importing, the board prints the current document between marker lines:
  ```
  ---STATE BEGIN---
  { ...pretty JSON... }
  ---STATE END---
  ```
  The `DUMP STATE` menu item prints it again on demand, with the latest ages and births.
- `tools/pull_state.py PORT [-o FILE]` opens the serial port (pyserial, added to `requirements.txt`) and waits up to 30 s for the markers. Press RESET or select `DUMP STATE` while it waits. It then writes the JSON to FILE (default `state.json`).
  - On WSL2 the board's serial port isn't visible without `usbipd`. Run the script with Windows Python against `COMn` instead. Any serial terminal (Mu, PuTTY, `tio`) works too: copy the text between the markers.
- Loop: pull → edit → `deploy.sh --state state.json` (or drag the file onto CIRCUITPY) → auto-reload applies it.

### Simulator as the playground
- The desktop `state.json` uses the same format as the board's import file. You can design a pond in the simulator, by hand or by letting it breed with a high `POND_TIME_SCALE`, then copy it to the board with `deploy.sh --state state.json`. In the other direction, a pulled board state can be loaded into the simulator with `run.py --state FILE`.

## Data model: Species → Genome → Creature

| Layer | Holds | Lifetime |
|---|---|---|
| **Species** (`creatures/species.py`) | Body shape, color variants, spot rule, parts, motion settings, lifespan, size cap, offspring odds | Static, one shared object per species |
| **Genome** (`creatures/genome.py`) | id, species, color variant, pattern seed, max size, age, offspring count | One per fish. Persisted, and passed to offspring with mutations |
| **Creature** (`creatures/spine_creature.py`) | Joints, angles, current size, spots and part state built from the genome | Runtime only |

### Species
CircuitPython has no dataclasses, so `Species` is a plain class with keyword arguments. `SPECIES_BY_NAME` is the registry. The JSON stores species by **name**, so the table can be reordered and hand edits stay readable.

```python
KOI = Species(
    name="koi",
    joints=10, link=4, widths=(8, 10, 10, 10, 9, 8, 6, 4, 4, 2),
    angle_limit=pi / 8,
    color_variants=((WHITE, ORANGE, RED), (WHITE, BLACK), (GOLD, ORANGE), (ORANGE, WHITE, BLACK)),
    spots=SpotRule(count=(2, 5), radius=(1, 2), joints=(0, 7)),
    parts=(),
    motion=Flock(**KOI_FLOCK), # or Wander(...); see Behaviors
    lifespan_days=7,
    size_cap=110, size_min=50, # percent of the base body
    offspring_odds=(("koi", 95), ("catfish", 3), ("sturgeon", 2)),
)
```

Planned species. All numbers are starting points to tune on the panel:

| Species | Body | Parts | Motion | Lifespan | Size cap |
|---|---|---|---|---|---|
| koi | 10 joints, wide middle | none | `Flock`: current koi settings | 7 d | 110 |
| catfish | 9 joints, wide flat head | `Whiskers(count=2, length=6)` | `Wander`: slow, hugs the edges | 10 d | 100 |
| sturgeon | 12 joints, narrow (`widths` ≤ 6) | `Snout(length=4)`: extra narrow joints ahead of the head | `Wander`: long, smooth turns (low turn rate, small `angle_limit`) | 14 d | 130 |
| turtle | 3 joints | `Shell(rx=4, ry=3)`, `Flippers()` | `Wander`: ~1/4 koi speed, long pauses | 30 d | 90 |

### Genome fields (integers only)
Integers only keep hand edits simple and the dumps exact. CircuitPython floats are 32-bit, so `0.92` could be dumped as `0.9200001`.

- `id`: unique within the pond. `pond.next_id` gives the next one. For a fish added by hand, pick an id not already used. The loader drops duplicates.
- `species`: a name from `SPECIES_BY_NAME`.
- `colors`: index into `species.color_variants`.
- `seed`: 0–65535. Spots are regenerated from it and never stored. Changing it rerolls the spots.
- `max_size`: percent of the species' base body, clamped to `[size_min, size_cap]`.
- `age_hours`: hours rather than minutes, so aging alone marks the document dirty at most once an hour.
- `offspring`: births so far, max 2.

### Growth and max size
- Current size = `max_size × growth(age)`. `growth` rises from 30 % at birth to 100 % at 30 % of the lifespan, then holds.
- The size is applied in **steps of 10 %**, not every frame. On a step the creature recomputes `link_size`, the widths and `render_radius`. Spots are in body coordinates, so they scale with it. Sprite parts (the turtle shell) are pre-drawn at those few steps, as LEARNINGS.md suggests.
- Child: `max_size = clamp(parent.max_size × uniform(0.9, 1.1), size_min, size_cap)`. If the child is a different species, the parent's value is clamped into the new species' range.

### Offspring
```python
def make_offspring(parent, parent_species, next_id):
    species = weighted_pick(parent_species.offspring_odds)
    same = species is parent_species
    colors = parent.colors if same and random.random() < 0.8 else random_variant(species)
    max_size = clamp(parent.max_size * uniform(0.9, 1.1), species.size_min, species.size_cap)
    return Genome(next_id, species.name, colors, random.getrandbits(16), round(max_size), 0, 0)
```
A child usually keeps the parent's colors but always gets new spots. A child of a different species picks from that species' own variants.

## Components

### Shared colors and CO2 brightness — `creatures/colors.py`
- The canvas shares the pond sprite's 16-entry palette, and the water uses indices 0–5. That leaves **about 10 creature colors in total**, shared by every species. Species variants refer to these slots. **Reserve 2 of them** for the future special fish and boid zaps (see Future ideas), which leaves about 8 for the normal species: for example white, orange, red, black, gold, slate, pale belly and olive.
- `set_brightness(palette, factor)` rewrites those entries from their base RGB. Each brightness change is about 10 palette writes, with no per-creature cost.
- CO2 → factor: 1.0 at ≤ 800 ppm, linear down to 0.4 at ≥ 2000 ppm, quantised to 0.1 steps so the palette only changes when the step changes. Unavailable CO2 → 1.0.
- Wiring: `App.tick` calls `scene.set_sensors(values)` with the whole `sensors.values` dict whenever `sensors.changed`. Scenes without the hook are skipped (`getattr`). `create_scene` can return a small object with `update` / `set_sensors`, or a third tuple element.
  - Use a generic hook, not `set_co2(ppm)`. The scene works out what each value means: the CO2 brightness now, and later the special fish and the zap rate. New sensor-driven effects then need no new wiring in `App`.
- If 10 colors are too few: build a 32- or 64-entry `Palette` in `make_canvas` with the pond colors copied in. The canvas goes to 8 bits per pixel (4 KB). Blitting the 4-bit pond sprite into it should be allowed, since only sources with *more* bits than the destination are rejected, but check this on hardware.

### Spots — `creatures/pattern.py`
- `make_spots(rule, seed, n_colors)` uses a seeded `random.Random` (or seeds the global `random` and restores it) and returns `[(joint, t, radius, color_slot)]`. Here `t` is a lateral offset in −1..1 of the half-width at that joint. `color_slot` 0 is the base color and is never used for spots.
- Render, after the body fill: `cx = jx - sin(a)·t·half`, `cy = jy + cos(a)·t·half`, then `fill_region`. `CreatureSpine` already keeps `angles`, so this costs a few multiplies per spot. The spots bend with the spine.
- Turtle: the shell spots are in shell coordinates, baked into the pre-drawn shell sprites (8 or 16 headings × size steps).

### Parts — `creatures/parts.py`
- Each part type has `attach(creature) -> state` and `render(state, creature, bitmap)`. The species lists part *instances* (shared settings). Per-fish state, such as a whisker chain, comes from `attach`.
- `Whiskers`: a short follow-the-leader chain anchored at the head joint with a side offset, using the same mechanism as `CreatureSpine.move`, so the whiskers trail when the catfish turns.
- `Snout`: extra narrow joints ahead of the head.
- `Shell` / `Flippers`: pre-drawn rotated sprites, blitted at the nearest heading.
- Parts are resolved at construction. A frame does no `if species ==` checks. Draw order: body, then spots, then parts.

### Generic body — `creatures/spine_creature.py`
Replaces `Fish`. It is built from `(species, genome)`, draws the width profile from the species, then the spots, then the parts. `fish.py` is removed once the koi has been ported to it.

- **Spine update with plain floats** (M3.5, in `CreatureSpine` in `creatures/spine.py`, so `spine_creature.py` inherits it). For ~20 fish, the spine is likely to cost more than any neighbour search; the M3 bench measured ~5 ms per koi per frame in `set_state`, against ~0.4 ms of steering. Today the behaviors push state through the default `Creature.set_state`, which calls `CreatureSpine.move(Vector)`. That allocates several `Vector`s per joint per frame and calls `heading()`/`from_angle()` (trig) per joint. At ~20 fish × ~10 joints, that's thousands of allocations a frame.
  - Override `set_state` and keep the joints in flat `jx`/`jy` lists.
  - Follow the leader with `dx, dy = prev - cur`, `d = sqrt(dx² + dy²)`, `cur = prev - (dx, dy) · link / d`. That's one `sqrt` per joint and no allocations.
  - Keep the angle constraint, but don't compute it with angles. Compare the dot product of consecutive link directions with `cos(angle_limit)`, and only fall back to rotating (trig) when a joint goes past the limit, which is rare when swimming smoothly.
  - Keep `angles` only where they're needed: spots and sprite parts need each joint's direction, and the unit link vector `(dx/d, dy/d)` gives it without `atan2`. A sprite part takes one `atan2` at its own joint.

### Behaviors — `behaviors/swim.py`, `flocking.py`, `wander.py`
The rule from OPTIMIZATIONS.md still applies: method calls and allocations are what cost, so each behavior does **one `update(dt)` per frame** with the per-creature math inlined in loops over flat lists. There is never a method call per creature per frame, except `set_state` and `render`.

- **`SwimBehavior` (base)** owns everything that isn't steering:
  - The flat `xs`/`ys`/`vxs`/`vys` lists and `add(creatures)`/`remove(creature)`. `remove` is a swap-remove: the last entry moves into the hole, so each list stays dense. It's shared by flocking and wander, and later by special fish.
  - Wall bounds, the safe rectangle, and the soft wall push (the current `ease_in`/`avoidance`, inlined).
  - Speed clamping, the move loop, `set_state`, and the on-screen render culling.
  - `update(dt)` calls `self._steer(dt)` once, then moves and renders. `_steer` is the only thing subclasses write, and it loops over every creature itself. It updates `vxs`/`vys` in place (wander) or replaces them with new lists (flocking, which needs a snapshot). Subclass per-creature lists are added in `_add_state` and listed in `_state_lists`, so `remove` swaps them too.
  - Speed clamping stays inlined in each `_steer`, so flocking only clamps the boids it steered this frame.
- **`FlockingBehavior(SwimBehavior)`**: separation, alignment and cohesion.
  - **The neighbour search switches at `grid_min_boids`.** This is a constructor setting (default 24, from the M3 board measurements in OPTIMIZATIONS.md: the direct loop wins below ~24 boids, the two are even at 24–32, and the grid wins clearly at 50), so each species' `Flock(...)` can set it.
    - **Below the threshold:** no grid. `_steer` checks every other boid directly. The cell bookkeeping is skipped entirely: no clearing of occupied cells, no cell index per boid, no 9-cell loop.
    - **At or above the threshold:** the current grid.
    - It's chosen once per frame, `use_grid = count >= self.grid_min_boids`, so births and deaths can cross it.
  - **Both paths need the same distance check.** The grid path currently accepts everyone in the 3×3 cells around the boid, which reaches about 1.5–2 × `perception_radius` depending on where the boid sits in its cell, with no distance check. A direct loop with no check would flock with the whole tank. Add `dist_sq <= radius²` to both, so the threshold changes only the speed, not the behavior.
    - This changes the background boids' behavior slightly: fewer neighbours, so less cohesion. Retune `perception_radius` or the forces if they look different.
  - **Merge `get_neighbors` into `flock`** (open item in OPTIMIZATIONS.md): one loop that checks distance and field of view and adds to the sums inline, with no `neighbors` list. Write it twice, once over `range(count)` and once over the 3×3 cells, rather than calling a helper per candidate.
  - **Rough crossover.** Per steered boid, the direct loop does `n − 1` cheap checks (subtract, multiply, compare). The grid path does 9 cell lookups and loop setups plus its checks, and costs about `n` index computations per frame to build.
    - For the koi flock (3–8 fish) the direct loop is clearly faster.
    - Somewhere around 15–30 boids the grid starts winning, depending on how clustered they are. Clustered flocks hurt the grid less than spread ones, because the 3×3 cells then hold most of the flock anyway.
    - Measure it on the board instead of guessing: koi `Flock` with n = 4, 8, 16, 24, 32 in both modes, read from `DEBUG`. Set the default from the result.
  - The steering parity (half the boids each frame) stays. For tiny flocks it might not be worth it, so measure that too.
  - The future zap effect's `neighbor_of(i)` lives here, using whichever path is active.
- **`WanderBehavior(SwimBehavior)`**: no neighbours at all. It costs O(n), with a constant per creature.
  - Each creature has a `turn` rate (rad/s), in a flat list. Every `retarget` seconds (1–4 s, one random draw per creature, staggered so they don't all change at once) it picks a new target turn in `±max_turn`. Each frame, `turn` eases toward the target. This is the "slow random walk on a heading offset" from LEARNINGS.md, and it gives smooth curving paths.
  - **The heading is rotated without trig:** `vx, vy = vx − vy·turn·dt, vy + vx·turn·dt`, followed by the existing speed clamp, which renormalises. The small-angle error disappears in that clamp.
  - Speed eases toward a per-creature cruise speed that is occasionally re-rolled, including near 0 for turtle "pauses" (`pause_chance`).
  - Near a wall (outside the safe rectangle, so rare), the target turn is biased toward the tank centre with one cross-product sign check, then the base wall push applies.
  - Optional side wiggle: add `sin(t·freq + phase)·amp` to `turn`. `phase` is per creature and `sin` is one call per creature per frame. Leave it off by default; the spine already sways when the heading changes.
- **Motion records**: `Flock(**kwargs)` and `Wander(speed, max_turn, retarget, pause_chance, ...)` are small data objects with a `build(canvas, w, h)` that returns the behavior. `Species.motion` holds one, and `Pond` builds one behavior per species present. A species with no fish has no behavior.
- **What this means for the frame:** the background boids become three flocks of 10, and the koi are one small flock. All of them use the direct loop and none needs the grid at the default threshold. The grid stays for any flock that grows past it. Catfish, sturgeon and turtles wander at near-zero steering cost. The spine update (see Generic body) becomes the main per-fish cost, which is why it moves to plain floats.

### Lifecycle — `behaviors/lifecycle.py`
- `Pond` owns the genomes and one behavior per species, built from `species.motion` (see Behaviors). Mixed species never flock together.
- Once per second (not per frame), scaled by `POND_TIME_SCALE`:
  - Add elapsed time to each age and step growth.
  - Roll breeding: a fish breeds at 50–90 % of its lifespan, at most 2 offspring, at most one birth per second, and only while population < `MAX_FISH` (20).
  - Skip any species with `lifecycle=False` (see the Species note in Future ideas). Those fish don't age, breed or die, and don't count toward `MAX_FISH`.
  - A fish dies at 100 % of its lifespan, ± 10 % rolled once per fish.
- Avoid OpenMatrix's bugs: death removes the fish (it doesn't reset age to 0), and the offspring count is persisted.
- Births and deaths use `SwimBehavior.add`/`remove` (see Behaviors).
- `Pond.from_dict(d)` / `to_dict()`. The pond is only built from a document at startup, since edits are restart-only, so there is no live re-apply.
- A fresh pond (no saved state) starts with a few random koi and one of each other species, so everything is visible.

## Future ideas (not in this plan, but the design leaves room for them)

### Special fish driven by HA conditions
Example: a lightning fish that appears only while the washing machine is running. Special fish don't reproduce or age. They use the same movement as normal fish, only much faster.

- **Species flags.** Add `lifecycle=True` and `persist=True` to `Species` now, with those defaults.
  - A special species sets both to `False`.
  - The lifecycle loop skips it (already noted under Lifecycle).
  - `Pond.to_dict()` leaves it out, because its presence comes from HA, not the save.
  - Its genome (colors, seed, size) is rolled when it spawns and never stored.
- **Conditions** live in the species table as data, like `appears_when=("washer", in_states("on", "running"))`. The pond checks them in `set_sensors`.
  - On true, it spawns the fish just outside the window so it swims in.
  - On false, the fish leaves: it stops avoiding the walls, and it is removed with `SwimBehavior.remove` once it is fully off screen.
  - Unavailable sensor → condition false.
- **Movement:** each species already gets its own behavior from its `motion` record (`Flock` or `Wander`), so "much faster" is just higher speeds there. Spawning and removing at runtime uses `SwimBehavior.add`/`remove` (M3).
- **Color:** one reserved palette slot can pulse or flicker for a lightning look. This is a per-frame palette write for that one slot, not per creature. It's the one exception to "fixed colors", and it's limited to special species.
- **Sensors:** `from_settings` only polls `READOUT_ENTITIES` (CO2, temperature, humidity). `WASHER_ENTITY` is in `settings.toml` but isn't polled. Add an `EXTRA_ENTITIES` list, e.g. `("washer", "WASHER_ENTITY")`, `("power", "HA_POWER_ENTITY")`. Those keys get polled and appear in `values` without showing in the readout. `FakeSensors` needs matching fake keys, with the washer toggling every minute or so, so the simulator can show the feature.

### Electricity zapping between boids, rate set by house power
- **Rate:** `zaps_per_second = f(watts)` from a whole-house power entity. For example 0 below ~300 W, rising on a log scale to ~10/s at 5 kW. Unavailable → off. It is computed in `set_sensors`, so nothing extra runs per frame when the value doesn't change.
- **Effects layer in the scene.** After the behaviors draw, the scene runs a list of effects: `draw water → behaviors → effects`.
  - `ZapEffect(behavior)` accumulates `rate × dt`.
  - For each zap due, it picks a random boid and one neighbour from the behavior's spatial grid, then draws a jagged line between them. That's `bitmaptools.draw_line` over 2–3 segments with ±1 px midpoint offsets, in a reserved palette slot.
  - Each zap lasts 1–2 frames.
  - The cost is per zap, not per boid, so a quiet house costs nothing.
- **What FlockingBehavior needs to expose:** the flat `xs`/`ys` and a `neighbor_of(i)` helper: one 3×3 grid lookup above `grid_min_boids`, a short scan below it. `SwimBehavior.remove` swap-removes, so zaps should only hold indices for the frame they're drawn in.
- The same effects layer can carry later ambient effects (bubbles, ripples) without touching the behaviors.

## Milestones (each one is a separate, testable commit)

**M1: Store + menu settings persistence.**
- Add `persist/document.py` (settings part only), `persist/store.py`, `NvmBackend`, `FileBackend` + `run.py --state`, `PERSIST_SECONDS`, `clamped_int`, and the `.gitignore` entry for `state.json`.
- `App` loads the settings at startup (rotation applied via `set_rotation`, sensors on/off) and calls `mark_dirty()` from the menu actions. `Store.tick(now)` runs in `App.tick`.
- Read the espressif nvm implementation first, and record the findings here (size, how it writes, whether A/B is needed).
- *Check:*
  - Rotate and turn sensors off, wait one interval, and the settings survive a reboot (hardware) or a restart (desktop).
  - Pull the power within the interval and the old settings come back.
  - Garbage in nvm boots with defaults.
  - `DEBUG` frame time is unchanged outside saves. Record the save cost.

**M2: Import file + serial dump.**
- Add the `/state.json` import with the CRC check and per-section replace, the `BAD STATE.JSON` message, the startup dump with markers, the `DUMP STATE` menu item, `tools/pull_state.py`, `deploy.sh --state FILE`, and pyserial in `requirements.txt`.
- *Check:*
  - Pull the state, change `rotation`, and copy it back. The board auto-reloads with the new rotation.
  - Another reload with the same file changes nothing, and a later menu change survives a reboot even with the file still on the drive.
  - A broken file shows `BAD STATE.JSON` and keeps the saved state.

**M3: Behavior base, small-flock path, wander.**
- Split `SwimBehavior` out of `FlockingBehavior`, with shared integration, walls, render, and `add`/`remove`.
- Add the `grid_min_boids` switch, the distance check in both paths, and merge `get_neighbors` into `flock`.
- Add `WanderBehavior`. As a test, try the current koi on it.
- **Split the 50 background boids into three flocks of 10.**
  - Three `FlockingBehavior` instances, with the same settings and the same `BOID_COLOR`. Each starts in its own random third of the tank.
  - Flocks don't see each other. They pass through one another, and each keeps its own cohesion. That reads as separate schools, which is the point.
  - Each flock is under `grid_min_boids`, so all three use the direct loop. Per steered boid that's 9 checks instead of up to 49 candidates spread over 9 cells.
  - The total boid count drops from 50 to 30. If the pond looks too empty, try 3 × 12–15 and re-measure against the threshold.
- *Check:*
  - With `DEBUG` on the board, time the koi `Flock` at n = 4, 8, 16, 24, 32 in grid and direct mode. Record the crossover in `OPTIMIZATIONS.md` and set the `grid_min_boids` default from it.
  - The three boid flocks read as separate schools.
  - Total boid physics time for 3 × 10 is recorded and compared with the old single flock of 50 (OPTIMIZATIONS.md "Results").
  - Repeat the comparison with 3 × 10 forced onto the grid, to confirm the direct loop is the faster choice there.
  - Wandering koi curve smoothly, turn back before the walls, and never get stuck in a corner.

**M3.5: Float spine.**
- Do the "Spine update with plain floats" item (see Generic body) in `CreatureSpine` (`creatures/spine.py`), on its own, before any species work, so its gain can be measured cleanly against the M3 numbers.
  - Joints in flat `jx`/`jy` lists. A `set_state` override does follow-the-leader with one `sqrt` per joint and no allocations.
  - The angle limit uses the dot product against `cos(angle_limit)`, with trig only when a joint goes past it.
  - `Fish.render` reads `jx`/`jy` instead of `Vector` joints.
  - `move(Vector)` stays as a thin wrapper over the float update, so `CircleBehavior` and `example_fish_scene` keep working.
- *Check:*
  - `bench_flock.py` on the board: the koi totals drop well below the M3 table (20.2 ms at n = 4, 38.6 ms at n = 8, direct). Record the new rows in `OPTIMIZATIONS.md`.
  - Pond `DEBUG` physics is recorded against M3's 51–56 ms.
  - The koi look and swim the same, including the angle limit on tight turns. `example_fish_scene` still runs.

**M4: Species table + generic body.**
- Add `species.py` with `KOI` only, and `spine_creature.py` on top of the M3.5 `CreatureSpine`. Port the koi and remove `fish.py`. `Species` already takes `lifecycle` and `persist` (both default `True`), for the future special fish.
  - Done: the `Flock` / `Wander` motion records live next to their behaviors (`flocking.py`, `wander.py`). `SpineCreature(species, origin, size, color_index)` takes the size in percent until the genome exists (M9), and `set_size` precomputes the link, per-joint radii and `render_radius`, ready for growth steps. The pond builds one behavior per species present. On the desktop, a seeded 200-frame run of the pond is pixel-identical to M3.5. On the board, `DEBUG` shows 14.5–16.2 fps and 30.7–33.5 ms physics, the same as M3.5 (OPTIMIZATIONS.md "M4").
- *Check:* the pond looks and performs the same as after M3.5.

**M5: Shared colors + CO2 brightness.**
- Add `colors.py` and the `scene.set_sensors` hook. Creatures use the shared slots.
- *Check:* `FakeSensors` drifting CO2 dims and brightens the fish in visible steps, and the water is unchanged. Frame time is unchanged.

**M6: Color variants + spots.**
- Add `pattern.py`, `SpotRule` and the koi variants.
- *Check:* koi show different variants, and the spots stay in place as they swim and turn. The same seed gives the same markings after a restart.

**M7: Sturgeon + catfish.**
- Add the `Snout` and `Whiskers` parts and their species entries. Each gets its own behavior with its own speed.
- *Check:* both are recognisable at 64×64, the whiskers trail on turns, and the fps stays near the M6 value.

**M8: Turtle.**
- Add `Shell` (pre-drawn, spots baked in), `Flippers`, and the slow turtle behavior.
- *Check:* the turtle swims slowly, the shell rotates smoothly through its pre-drawn headings, and memory use for the sprites is recorded.

**M9: Genome, growth, max size, pond persistence.**
- Add `genome.py`, growth in size steps, size clamps, and `Pond.from_dict()`/`to_dict()`. The `pond` object joins the document, the import and the dump.
- *Check:*
  - Fish restored after a reboot keep their species, colors, spots and size.
  - Editing a fish's `colors`, `seed` or `max_size` in the desktop `state.json`, or in an imported file on the board, changes that fish on the next start.
  - Adding a fish by hand works, and invalid or duplicate entries are dropped with a printed reason.

**M10: Lifecycle + reproduction.**
- Add aging, breeding, `make_offspring` (inherited size ± 10 %, rare species switch), death, `MAX_FISH` and `POND_TIME_SCALE`.
- *Check:*
  - With a high `POND_TIME_SCALE` in the simulator, fish are born small, grow to their own max sizes, breed and die. The population stays ≤ 20.
  - Births and deaths mark the document dirty, and the offspring count survives a restart.
  - A pond bred in the simulator copies to the board with `deploy.sh --state state.json`.

**M11: Docs + measurements.**
- README:
  - the new settings keys
  - the edit loop (pull → edit → deploy/drag → auto-reload), including the WSL2 serial note
  - a genome field reference with the species names and valid ranges
  - that the simulator's `state.json` uses the same format
- `OPTIMIZATIONS.md`: save cost (JSON + nvm), per-species render cost, and fps with a full pond of 20.
- LEARNINGS.md: tick the "Doing it for real" and "Creature architecture" items that are now done, and update the persistence section with the nvm findings.

## Files
- **New:**
  - `src/creatures/{species,genome,colors,pattern,parts,spine_creature}.py`
  - `src/behaviors/{lifecycle,swim,wander}.py`
  - `src/persist/{__init__,document,store}.py`
  - `tools/pull_state.py`
  - `src/bench_flock.py`: grid vs direct timings (M3), runnable on the board's REPL
  - `plans/persistence-and-fish-variation.md`
- **Modified:**
  - `src/app.py`: settings load, dirty marking, `Store.tick`, `DUMP STATE`, `set_sensors`
  - `src/scenes/pond.py`: builds a `Pond` from the document
  - `src/creatures/spine.py`: float joints and `set_state` (M3.5)
  - `src/behaviors/flocking.py`: built on `SwimBehavior`, `grid_min_boids`, merged neighbour loop, distance check
  - `src/config.py`: `clamped_int`
  - `src/hardware/code.py`: `NvmBackend`, import, dump
  - `src/run.py`: `--state`
  - `src/hardware/settings.toml.example`
  - `deploy.sh`: `--state FILE`
  - `requirements.txt`: pyserial
  - `.gitignore`: `state.json`
  - README, `OPTIMIZATIONS.md`, LEARNINGS.md
- **Removed:** `src/creatures/fish.py` (in M4)
