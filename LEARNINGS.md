# Learnings

Notes from studying other projects (starting with
[OpenMatrix](https://github.com/livegrid/OpenMatrix)) and what applies to this
project on the MatrixPortal S3 with CircuitPython.

## Persisting state across reloads

### How OpenMatrix does it

- All state lives in one in-RAM struct. Anything that changes it (web UI, MQTT,
  touch) calls `save()`, which only sets a dirty flag. A background task checks the
  flag once a second and writes the whole struct as JSON to LittleFS, plus an
  unconditional save every 30 minutes. Callers never block on flash, and bursts of
  changes coalesce into one write.
- Restore loads defaults first, then overlays each saved field
  (`json["x"] | DEFAULT_X`). Missing keys fall back to defaults, so adding fields
  never breaks an old save file, and an unparseable file just means defaults.
  Runtime-only fields (e.g. connection status) are always reset.
- The aquarium saves each creature's "genome" (age, health, body/head/tail/fin
  type, motion type, colours), not positions or velocities. A reboot keeps *who*
  is in the scene, not the exact frame.
- Weakness to avoid: the file is opened with `"w"` (truncated) and rewritten in
  place, so a power loss mid-write corrupts it.

### Options in CircuitPython on the S3

1. **`microcontroller.nvm`** (what we use): a small byte array that survives
   reloads, resets and power cycles, no remount needed. On the Espressif port it is
   backed by ESP-IDF NVS, which wear-levels.
   - A header record (magic, version, length, CRC) in front of a compact JSON
     payload. Bad magic, version or CRC → load defaults. JSON instead of fixed
     `struct.pack` fields keeps hand edits and schema changes easy, and at
     ~120 bytes per fish it fits easily.
   - Findings from `ports/espressif/common-hal/nvm/ByteArray.c` (CircuitPython
     10.x):
     - **Size: 8 KB** (`CIRCUITPY_INTERNAL_NVM_SIZE`), stored as one NVS blob in
       the 20 KB `nvs` partition (5 pages of 4 KB).
     - **Every slice write rewrites the whole blob**: it reads all 8 KB, calls
       `nvs_erase_all()`, writes the full 8 KB back and commits. Every slice read
       also fetches the whole blob. So write the record in one slice assignment,
       and read it in as few slices as possible.
     - **A/B slots can't help here.** Both slots live in the same blob, and the
       old blob is erased *before* the new one is written. A power loss mid-save
       leaves the old record, the new one, or no blob (reads as zeros, so bad
       magic → defaults), never a mixed record that passes the CRC. Real A/B
       would need two storage locations.
     - **Wear**: each save is ~2 page erases spread over 5 pages, whatever the
       payload size. One save a minute flat out would reach 100k cycles in about
       170 days. Saving only when dirty (a few dozen saves a day for the pond's
       hourly ages, births and deaths) makes it decades.
     - **Save time is ~150–180 ms**, almost all of it the erase and the 8 KB rewrite,
       so it barely depends on the payload: a visible hitch of a frame or two,
       once per save. Another reason to keep dirty events rare. 152.5 ms for
       a 60-byte document, 170.5 ms for 900 bytes (OPTIMIZATIONS.md "M11").
   - Fits settings and per-creature genomes with room to spare: a full pond (10
     fish + the turtle) is ~1.4 KB of compact JSON. Even full boid state would fit
     (100 boids × 4 float32 = 1.6 KB).
2. **Writable CIRCUITPY**: `storage.remount("/", readonly=False)` in `boot.py`.
   The host then sees the drive read-only; both sides writing at once corrupts FAT.
   - Pick the mode at boot with a button (`board.BUTTON_UP` / `board.BUTTON_DOWN`),
     e.g. hold for dev mode (host writable), otherwise code writable.
     `storage.disable_usb_drive()` is an option for a deployed device.
   - Write `state.tmp`, then `os.rename()` it over the real file instead of
     truncating in place (FAT still isn't journaled).
   - Only worth it for larger or human-readable files.
   - Not used: the drive stays writable by the PC, and the board only *reads* an
     imported `CIRCUITPY/state.json` at startup (remembering its checksum, so
     it's imported once). Edits go file → board; the current state goes board →
     serial console → file.
3. **MQTT retained messages**: publish state with `retain=True` and the broker
   hands it back on subscribe at boot. No flash wear, visible and editable from
   Home Assistant, survives reflashing. Depends on the network, so pair it with
   nvm: nvm is the fallback, the retained message wins when it arrives.
4. **Not suitable**: `alarm.sleep_memory` only survives deep sleep, not resets.
   `settings.toml` / `os.getenv` is read-only config (WiFi, broker), not runtime
   state.

### Patterns to copy

- Dirty flag + throttled save (save at most every N seconds/minutes). Flash wears
  out. We dropped the "save immediately on significant events" part: at ~170 ms
  per nvm save, a burst of menu taps would stall the animation each time.
- Defaults first, saved values overlaid; a version field for schema changes.
- Persist what defines the scene (seed, creature genomes, settings), not every
  frame's positions, unless resuming mid-motion is actually wanted.

## Creature animation techniques

From OpenMatrix's aquarium (`lib/Aquarium/`). Creatures there are a `Motion`
(forces → position/heading) plus a `Body` (head, fin, tail parts drawn from
primitives every frame).

- **Motion is a sum of forces**, then clamped between a min and max speed:
  - Side sine: a force perpendicular to the heading,
    `sin(millis() * freq + phase) * amplitude`, with a random phase per creature
    so they don't wiggle in sync.
  - Forward sine (octopus): the same along the heading gives a pulsing,
    jet-propelled gait.
  - Noise wander: sample a simplex noise field at the creature's position, map it
    to an angle, push that way. Smooth, non-repeating wandering.
  - Boundary and food-seeking forces on top.
- **Fixed-point sub-pixel positions**: physics runs in pixels × `PHYSICS_SCALE`
  (50–80) and divides back for drawing, so small integer speed settings still
  give smooth motion.
- **Follow-the-leader spine**: each segment is placed a fixed distance behind the
  previous one, along the line between them. The head's sine wiggle travels down
  the body as a swimming wave. (Same idea as our `CreatureSpine`.)
- **Fins and tails are static shapes drawn at a spine joint, rotated to that
  joint's local angle.** Fins at segments 1 and 3, tail at the last. They never
  animate themselves: they swing because the spine bends under them. Most motion
  for the least code.
- **Segment sizes along a half sine** (`base + sin(π·i/(n-1)) · extra`): thin at
  head and tail, fat in the middle, from three numbers.
- **Secondary chains**: a "wavy tail" is its own small chain of pixels trailing
  the last segment, like a ribbon.
- **Phase-shifted sine on chain joints** (octopus tentacles): each joint angle
  gets `sin(t·2 + i·0.5 + j·0.3) · 0.2 · speedFactor`. Ripples when moving fast,
  hangs loose when drifting. Good for tails, tentacles, kelp.
- **Palettes from two numbers**: a base hue plus a hue step per segment, optionally
  "striped" by shifting every other segment's hue by ⅓ or ⅔ of the wheel.
- **Appearance as data display**: `size = age` (creatures grow from an egg pixel
  to full size), brightness fades after adulthood, saturation tracks health (which
  tracks CO₂), and CO₂ caps max speed. Sensor readings show up as how the scene
  looks, with no text needed.

## Creature architecture

### How OpenMatrix structures it

- `Fish` is the shared class. It owns one `Motion` and one `Body`, each built by
  name through a factory (`MotionFactory`, `BodyFactory`).
- `Motion::update()` does all the shared work each frame:
  1. Eggs stop (velocity 0) and skip the rest.
  2. Boundary push (10× stronger when CO₂ is bad or in demo mode).
  3. One steering source: food-seeking if it has a target, otherwise the
     subclass's `doMotion()`. Out of bounds, only the boundary push applies.
  4. Integrate: add forces to velocity, enforce min speed, cap at a CO₂-scaled max
     speed, move, set heading from velocity.
- The five motion subclasses are really one algorithm with different settings.
  Each constructor sets six constants, and `doMotion()` picks two of three shared
  helpers:

  | Variant      | `doMotion()`         |
  | ------------ | -------------------- |
  | Fish, Snake  | side sine + noise    |
  | Turtle, Star | forward sine + noise |
  | Octopus      | forward sine only    |

- Most visible variety comes from the `Body` side (spine chain, star rotation,
  tentacles), not from motion.
- Creatures never interact (no separation or flocking between fish), so each
  costs the same however many there are.
- The background boids are a separate, simpler `Boid` class, not `Fish`.

### Adapting it to CircuitPython

Method calls and allocations are what's expensive, not the class design itself
(inlining `cell_index` alone took physics from 80.8 to 44.0 ms; see
`OPTIMIZATIONS.md`). Copied literally, OpenMatrix makes many calls per creature
per frame (`update → boundaryCheck → doMotion → sine helper → applyForce`, a new
`PVector` per operation, one `display()` per part per segment).

- [x] **Split fish and boids completely.**
  - Creatures (few, ~5–20, e.g. koi): the shared class with parameter-driven
    motion, part variations, genome, lifecycle, persistence.
  - Boids (many): flat arrays and one loop for the whole behavior (as now), no
    per-boid objects in the hot path, ambient only (see Background boids).
  - Done: creatures are `SpineCreature`s with a genome; the boids stay flat
    arrays in `FlockingBehavior`.
- [x] **Variations as data, not subclasses.** One `Motion` with a parameter record
      (`side_amp`, `front_amp`, `freq`, `noise_amp`, `min_speed`, `max_speed`);
      an amplitude of 0 turns a term off. The record doubles as the motion part of
      the genome (mutation = nudging numbers, saving = `struct.pack`) and maps
      directly onto a C struct if physics ever moves to C.
  - Done as `Species` records (`creatures/species.py`) holding a `Flock` or
    `Wander` motion record; a new species is one table entry. The motion
    records aren't part of the genome: a fish inherits its species, variety
    and size, not its speeds.
- [x] **One `update()` call per creature per frame**, with the math inlined: copy
      settings into locals, accumulate plain `ax`/`ay` floats, no `Vector`
      allocations or `apply_force()` helpers. One call per creature per frame
      (even a virtual one) is negligible.
  - Done: one behavior loop per species with plain-float steering, and a
    float spine with one `set_state` per creature (M3.5).
- [x] **Replace per-creature simplex noise**, which is costly in pure Python.
      Cheaper look-alikes: a small precomputed noise table sampled with linear
      interpolation, the sum of two sines at unrelated frequencies, or a slow
      random walk on a heading offset.
  - Never needed: `Wander` steers toward a random target it picks every few
    seconds, eased in, which reads as natural wandering.
- [x] **Pre-drawn parts.** Fins, tails and heads are fixed shapes rotated to the
      joint angle, so render each at 8–16 angles into small bitmaps at startup
      and `bitmaptools.blit` the nearest one each frame (like `FishBoid`'s 8
      facing sprites).
  - Only draw live what really deforms (the spine, tentacles), using
    `bitmaptools` so the drawing loops run in C.
  - Bake the creature's palette colours into the sprites at creation (or share
    sprites between creatures with the same part and palette indices).
  - Memory: 16 angles × a few parts × small bitmaps per creature is cheap at
    koi counts. Watch it if part sizes grow with age; pre-draw at a few size
    steps, not every size.
  - Done differently: the body, fins, tail, spots and flippers are pre-drawn
    *discs* (`graphics/stamps.py`) placed per frame. A disc looks the same at
    every heading, so it needs no per-angle copies. Only the turtle's shell
    is a sprite per heading (16, rebuilt per size step, ~4 KB), with its
    marks baked in. Each blit costs ~0.1 ms on the board whatever its size,
    so the item count matters more than the drawing method (OPTIMIZATIONS.md
    "Render cost per item").
- [x] **Pick variations once, at construction**: store the variant's draw function
      on the creature (e.g. `self.draw_fin = FINS[genome.fin]`), so a frame does
      one attribute lookup, not string compares or `if/elif` chains on type.
  - Done: the variety record, the spots in pixels and the part states are
    worked out in `set_size`, so a frame only reads them.

## Evolution

### What OpenMatrix does (not real evolution)

- A creature is a random combination of parts: body type (weighted: Fish 50%,
  Turtle 20%, Star/Snake/Octopus 10% each), head, fin, tail, segment count/sizes,
  palette. That combination is the saved "genome".
- Age 0→1 runs in real time (avg 7 days); ageing pauses when CO₂ ≥ 2000. Age
  < 0.1 is an egg (one pixel, no motion).
- Health drops when CO₂ is bad and recovers when good; it only affects saturation.
- At age 0.5–0.9 a fish has a 1% chance per frame to spawn (max 2 offspring, at
  most one birth per frame, only while population < 20).
- **The offspring is fully random**: no inheritance, no mutation.
- Bugs to avoid copying: `update()` resets age to 0 instead of killing, so fish
  never die (they become eggs again with the same body). Offspring count isn't
  persisted, so every fish can reproduce again after a reboot. Health rates are
  labelled "per second" but applied per frame.

### Doing it for real

- [x] Keep a small, explicit genome: part types, palette start + step, stripe type,
      segment count, size curve, sine amplitude/frequency, speed.
  - Done with fewer fields: id, species, variety, spot seed, max size, age and
    offspring count (`creatures/genome.py`), all integers. Body shape, parts
    and motion belong to the species and colors to the variety, so they
    aren't per-fish genes.
- [x] Offspring = copy of the parent's genome with small mutations: nudge hue
      ±a few steps, occasionally swap one part type, ±1 segment, jitter
      motion parameters within bounds.
  - Done as: max size ±10 %, the same variety ~80 % of the time (15 % one of
    the same family, 5 % any), a rare switch to another species, a new seed.
- [ ] Optional selection pressure from home status: e.g. health (from sensor/status
      data) affects lifespan or reproduction chance, so the population drifts toward
      traits that survive the house's conditions.
  - Not done: CO2 only dims the fish.
- [x] Persist genomes (plus age and offspring count) to nvm, not positions.
- [x] Make death actually remove the creature, and cap the population.
  - At most `MAX_FISH` (10) plus the turtle, and per-species caps: with only
    the total cap, a pond drifted to a single species within months.

## Background boids

### What OpenMatrix does

The aquarium's `BoidManager` (using `EffectManager/Boid.cpp`) is purely ambient:

- 2 independent groups of 10–19 boids. Groups never interact, which keeps the
  brute-force O(n²) neighbor checks small; no spatial grid, no field of view.
- Classic Reynolds rules with tiny radii (separation 4 px, neighbors 8 px) and
  fixed weights (separation 1.5, alignment 1, cohesion 1).
- Edges wrap around instead of steering away from walls. (`avoidBorders()` is
  also called, but after the wrap, so it effectively never fires.)
- Per-boid random max speed (~0.4–0.9 px/frame).
- Updated and drawn every frame in both normal and demo mode, as 2-pixel lines in
  one fixed colour.
- The only outside input: CO₂ scales their speed down to 0 when CO₂ is
  really bad.
- No lifecycle, no persistence (re-randomized on boot), and no reaction to fish,
  food or touch.

### Plan for our boids

- [ ] Treat our boids the same way: ambient background that always runs. No
      lifecycle, evolution or persistence; re-randomize on boot. Lifecycle,
      evolution and saved genomes are only for the "real" creatures (e.g. koi).
- [ ] At most one global input from home status (e.g. a speed or colour
      multiplier), not per-boid logic.
- [ ] Optional simplifications worth trying, since the boids are only
      background:
  - Wrap-around edges instead of wall avoidance (removes `avoidance()` and
    `ease_in` entirely).
  - Several small independent groups instead of one large flock.
  - Dropping the field-of-view check.

## To-do (optional): move physics into C

Only if pure-Python optimizations (see `OPTIMIZATIONS.md`) don't reach the
target boid count.

- [ ] First check the cheap options: whether `micropython.native` is enabled on
      the S3 build, and the remaining items in `OPTIMIZATIONS.md`.
- [ ] Build a custom CircuitPython firmware for `adafruit_matrixportal_s3` with a
      native module: API in `shared-bindings/<module>/`, implementation in
      `shared-module/<module>/`, enabled with a `CIRCUITPY_<MODULE> = 1` flag. Built
      with ESP-IDF (Linux/WSL or Docker). Loading native code from `.mpy`,
      `USER_C_MODULES` and `@viper` are MicroPython features CircuitPython mostly
      lacks; don't plan around them. Cost: maintaining a fork and reflashing for
      every C change, so keep the C small and stable and tune from Python.
- [ ] Interface: one call per frame, not one per boid.
  - A `Flock` type owns x/y/vx/vy and the spatial grid in C float arrays.
  - Tuning values (separation, alignment, cohesion, max speed, FOV, wall
    distance) are properties, adjustable from Python without reflashing.
  - `flock.step(dt)` runs grid build, steering and integration.
  - Expose positions via the buffer protocol (a float32 `memoryview`) so Python
    reads them without allocating; the same buffer can be written to nvm.
  - Later, optionally `flock.draw(bitmap, sprites)` to blit straight into the
    full-screen `displayio.Bitmap` and mark only the changed area dirty.
  - Use `float`, not `double`: the S3 FPU is single-precision only.
- [ ] Keep the desktop simulator working: write the core as plain C with no
      MicroPython headers (`boids_step(state*, dt)`), wrap it once for CircuitPython
      and once for CPython (`ctypes` or a small extension), and keep the
      pure-Python `FlockingBehavior` as a same-API fallback
      (`try: import boids` / `except ImportError:`).
- [ ] Measure with the existing `DEBUG` timing. Expect physics to drop from ~34 ms
      to a few ms (an estimate, not measured).
