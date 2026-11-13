# Flocking performance optimizations

With 100 boids the MatrixPortal S3 runs at roughly 1 fps; 10 boids is smooth.
Work through these in order, measuring after each step.

## 1. Measure first

- [x] Set `auto_refresh=False` on the display in `src/hardware/code.py` and call
      `display.refresh()` in the main loop so display cost isn't hidden in the
      background.
- [x] Time physics, `render()`, and `display.refresh()` separately with
      `time.monotonic_ns()` and print the breakdown to the serial console.

### Results

| Step                                                     | Boids | FPS  | Physics (ms) | Render (ms) | Refresh (ms) |
| -------------------------------------------------------- | ----- | ---- | ------------ | ----------- | ------------ |
| Baseline                                                 | 100   | 1.2  | 662.6        | 135.0       | 17.6         |
| Fixing spatialized grid                                  | 100   | 1.5  | 501.7        | 132.5       | 18.3         |
| Combining forces into single loop                        | 100   | 1.8  | 392.0        | 136.4       | 17.9         |
| Store flat array of x and y                              | 100   | 2.7  | 195.4        | 154.9       | 17.7         |
| Swapping to ulab (reverted)                              | 100   | 1.4  | 587.2        | 127.8       | 19.7         |
| Steer only half the boids at a time                      | 100   | 3.1  | 144.4        | 158.5       | 19.4         |
| Have flocking own boid positions                         | 100   | 3.8  | 102.0        | 140.4       | 17.3         |
| Limiting avoidance checks                                | 100   | 4.0  | 93.4         | 139.4       | 18.5         |
| Pre-computed bitmaps and only render visible boids       | 100   | 8.7  | 89.3         | 9.6         | 15.9         |
| Make FishBoid its own Creature instead of having a spine | 50    | 9.7  | 80.8         | 6.6         | 14.7         |
| Inline cell_index                                        | 50    | 16.2 | 44.0         | 7.4         | 10.0         |
| Render flock bitmaps all at once                         | 50    | 16.2 | 34.0         | 9.0         | 18.3         |
| Render all bitmaps at once                               | 50    | 16.2 | 32.0         | 13.8        | 13.3         |

At baseline, physics was ~81% of the frame time, render ~17%, and
`display.refresh()` ~2%. As of the latest row, render is the biggest cost at ~54%,
with physics ~39% and refresh ~7%.

## 2. Physics

### Cheap

- [x] Move `boid_direction = self.velocities[boid].normalized()` in
      `FlockingBehavior.get_neighbors` out of the 3x3 cell loop (it's computed up to
      9 times per boid).
- [x] Use an integer key (e.g. `cx + cy * 1000`) for the spatial grid instead of
      allocating a `(x, y)` tuple in `cell_coords`. Small ints aren't heap
      allocated, hash to themselves, and compare in one step. Precompute the 9
      neighbor offsets (`dx + dy * 1000`) so each lookup is `grid.get(key + off)`.
      The multiplier must exceed the number of cells across the swim area, and
      `abs(cx)` must stay under half of it, since cells can be negative off screen.
- [x] Copy attributes like `self.separation_force` into local variables before the
      loops.
- [x] Do the physics less often: update steering for half the boids each frame
      (alternating), while still moving every boid every frame. Physics only went
      from 195 ms to 144 ms: steering was ~100 ms of it, and the other ~95 ms
      (reading positions, rebuilding the grid, moving boids) still ran for every
      boid every frame.
- [ ] Or run flocking at a lower rate (e.g. 15 Hz) and just move boids along their
      current velocity on frames in between. Like the item above, this only
      reduces the steering cost.
- [x] ~~Rebuild the spatial grid only every other frame.~~ Not worth it: timing
      the rebuild on its own showed it takes ~5 ms of the ~80 ms of physics, so
      skipping it saves little. It would also hurt accuracy: boids move ~4 px per
      frame and cells are 5 px wide, so a one-frame-old grid misses close
      neighbors (mostly hurting separation). And since steering alternates
      parity, one half of the boids would always steer with the stale grid.
- [ ] Inline `cell_index` in the grid-build loop and the neighbor lookup. Method
      calls are expensive in CircuitPython. Since the swim area is fixed, the
      clamping can be a cheap check that only runs for boids outside it.
- [x] Skip `avoidance()` for boids more than `wall_avoid_distance` from every wall.
      It makes four `ease_in` calls per steered boid, but most boids are nowhere
      near a wall.
- [ ] Minor: drop the full `new_vxs`/`new_vys` copies by buffering only the steered
      half, and replace the two `uniform()` calls with one cheaper random value.

### More work

Every `Vector` operation allocates a new object; at 100 boids that's thousands of
allocations per frame, plus garbage-collector pauses.

- [x] Replace the spatial grid dict with a fixed grid (after the integer key): the
      swim area has fixed bounds, so preallocate
      `cells = [[] for _ in range(cols * rows)]` once and index it with
      `(cx - min_cx) + (cy - min_cy) * cols`. No hashing, no dict probing. Pad one
      cell on each side so the 3x3 neighborhood never goes out of range (no bounds
      checks), and clear each cell list in place each frame instead of rebuilding.
      Pairs with the flat arrays below: cells can hold boid indices.
- [x] Do the per-boid steering math with plain `x`/`y` floats in the hot loop instead
      of `Vector` operations.
- [x] Compute separation, alignment, and cohesion in a single pass over the
      neighbors instead of building a neighbor list and looping over it three times.
- [x] Store positions and velocities in flat lists of floats for x, y, vx, vy,
      indexed by boid number instead of dicts keyed by boid object. Plain lists
      beat `array.array('f')` here: CircuitPython floats fit in the list slot
      without heap allocation, so arrays save no memory and add a float32
      conversion on every read and write.
- [x] ~~If the above isn't enough, use `ulab` (numpy-like, included in the S3 build)
      to compute all pairwise offsets and forces as arrays, skipping the spatial
      grid entirely.~~ Tried and reverted: physics went from 195 ms to 587 ms.
      All-pairs is ~5x the pairs the spatial grid visits, and each frame
      allocates ~20 N x N float32 temporaries (40 KB each at 100 boids). Blocks
      that size land in PSRAM, which is much slower than internal RAM, and the
      garbage collector has to clean them up every frame. The C loops don't make
      up for that at this boid count; the grid with flat lists stays.
- [x] Have `FlockingBehavior` own the boid positions: integrate `xs`/`ys` itself
      and push the result with `Creature.set_state(x, y, vx, vy)` instead of
      reading `position()` back and calling `move(Vector(...))` every frame.
      `FishBoid` overrides `set_state` to store plain floats, skipping the Vector
      allocations and the unused `atan2` in `CreatureSpine.move`. Other creatures
      fall back to the default `set_state`, which calls `move()`, so the behavior
      still works with any creature. Physics went from 144 ms to 102 ms.
- [x] Merge `get_neighbors` into `flock`, with `in_fov` inlined. Each steered boid
      still builds a `neighbors` list, and `flock` loops over it again,
      recomputing `dx`, `dy`, and `dist_sq`. One loop that checks the field of
      view and adds to the sums inline removes the list, the second pass, and a
      method call per candidate. Done in M3 (see section 6); the loop also
      checks `dist_sq <= perception_radius²` now.

## 3. Render

### Cheap

- [x] Don't redraw the `FishBoid` sprite every frame: pre-build the 8 facing sprites
      as 3x3 bitmaps once and swap with `self.grid.bitmap = SPRITES[facing]` (same
      size, so displayio allows it), only when `facing` changes.
- [x] Skip `render()` for boids outside the visible window (`outside_window_size`
      lets most of the swim area be off screen).

### More work

- [x] See the single full-screen bitmap under Refresh; it also replaces the
      per-boid sprite updates.

## 4. Refresh

### Cheap

- None yet. Refresh is only ~2% of the frame, so it's low priority.

### More work

- [x] Replace the per-boid TileGrids with one full-screen 64x64 bitmap: each frame,
      erase the previous pixels and draw the new ones (consider `bitmaptools`), so
      displayio only composites one layer. First try: each behavior owned a
      transparent canvas and cleared it with `fill(0)`, calling `render(bitmap)` on
      its visible creatures (`FishBoid` uses `bitmaptools.blit`, `Fish` uses
      `bitmaptools.fill_region`). Physics + render dropped from 51.4 to 43.0 ms,
      but refresh rose from 10.0 to 18.3 ms: `fill(0)` marks the whole canvas dirty
      every frame, so displayio recomposited the full screen through every layer.
      Render timing now wraps `FlockingBehavior.render`, so it includes the clear
      and the koi, which were previously counted as physics.
- [ ] Draw everything into a single opaque canvas: the scene blits the current pond
      frame over it each frame (replacing `fill(0)` and the pond's own TileGrid),
      then the creatures draw on top using free indices in the pond's palette.
      Refresh composites one layer with no transparency. Render timing also counts
      the pond blit (`scenes.pond.draw_frame`). Not yet measured on hardware.

## 5. HA sensors and menu overlay

The sensor readout and the menu are separate small `TextPanel` layers on top of
the scene ([plan](plans/ha-sensors-and-menu.md)). They only redraw when their
text changes, so after the first draw they shouldn't mark the screen dirty.
`sensors.poll()` does at most one non-blocking socket step per frame and is
timed as **net** in the `DEBUG` stats line (physics excludes it).

### Results

Pond scene, 50 boids, `DEBUG` stats averaged over 30 frames. Ranges span the
stats lines captured; net max is the worst across them.

| Setup                                   | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| --------------------------------------- | --- | ------------ | ----------- | ------------------ | ------------ |
| Before this branch (`b328ea7`, no App or HA) | 8.7–8.8 | 82.7–87.0 | 14.3–17.2 | – | 13.2–13.8 |
| Readout hidden (`SENSORS OFF`), menu hidden | 7.3 | 92.2–94.0 | 26.5–27.8 | 1.5–2.1 / 8.2 | 13.5–14.6 |
| Readout shown, HA reachable, 5 s poll   | 7.2–7.3 | 94.1–95.4 | 24.0–24.2 | 1.2–1.5 / 8.3 | 15.7–16.4 |
| Readout shown, 1 s poll                 | 7.0–7.3 | 92.8–96.8 | 24.1–26.9 | 3.3–3.4 / 9.2 | 15.8–16.1 |
| Readout + menu shown                    | 7.0 | 94.3–97.6 | 25.1–26.9 | 2.1 / 8.8 | 17.6–18.2 |
| HA unreachable (wrong IP)               | 6.8–7.2 | 97.5–101.3 | 24.8–28.6 | 0.3–1.5 / 3.8 | 16.1–16.8 |

- Each visible text layer adds ~2 ms of refresh (13.5–14.6 ms with nothing
  shown, 15.7–16.4 with the readout, 17.6–18.2 with the menu too). FPS stays
  at ~7 in every setup, so the `bitmaptools.blit` fallback isn't needed.
- Net averages 1.2–1.5 ms at a 5 s poll and 3.3–3.4 ms at 1 s, since a request
  is in progress on more frames. The worst frame stays at ~9 ms either way:
  one bounded socket step.
- With HA unreachable the worst frame is 3.8 ms while connecting, then
  0.3–0.5 ms during the backoff. The animation doesn't stall.
- Physics is ~92–101 ms in every row. Most of the gap from the 32 ms in the
  last flocking row came before this branch: the pre-branch build already runs
  physics at ~85 ms. This branch adds ~8 ms of physics and ~11 ms of render
  with nothing shown (8.8 → 7.3 fps), although the scene and render code are
  unchanged and the timing code is the same. Physics here is `app.tick()` minus
  render and net, so it includes the menu, button and readout code. Not yet
  traced to a commit.

On the desktop the worst `poll()` was ≤0.3 ms across OK, 404, 401, a slow
server (timeout), a refused port and a blackholed IP.

- The `settimeout(0.05)` fallback for `connect()` was dropped: CircuitPython's
  `connect()` polls in 100 ms steps, so it stalled for up to 100 ms per retry.
  Non-blocking `connect()` (ETIMEDOUT, then EALREADY, then EISCONN) has no stall.
- If refresh rises with the panels shown, the fallback is to blit the
  pre-rendered panel into the pond canvas with
  `bitmaptools.blit(..., skip_source_index=0)` so displayio composites one layer.

## 6. Small flocks without the grid (M3)

From the [persistence and fish variation plan](plans/persistence-and-fish-variation.md).

- `SwimBehavior` (`behaviors/swim.py`) holds the shared flat lists, walls,
  integration and render; `FlockingBehavior` and `WanderBehavior` only write
  `_steer(dt)`. `DEBUG` render timing now wraps `SwimBehavior.render`.
- `FlockingBehavior(grid_min_boids=16)`: below that many boids each steered boid
  checks every other boid directly, with no grid build. Both paths run the same
  loop (`for offset in offsets: for j in source[base + offset]`; the direct
  path's `source` is one group holding every boid) and the same distance and
  field-of-view checks, so they pick the same neighbours. On the desktop the two
  modes give identical trajectories for the same seed.
- The grid path used to accept everyone in the 3×3 cells, reaching
  ~1.5–2 × `perception_radius`. With the distance check the boids have fewer
  neighbours, so slightly less cohesion. Retune if the schools look looser.
- The 50 background boids are now 3 independent flocks of 10, so the pond
  draws 30 boids instead of 50.
- `steer_half=False` steers every boid every frame, to measure whether the
  alternating parity is worth it for tiny flocks.

### Measuring

`src/bench_flock.py` times physics only (render off) for the koi flock at
n = 4, 8, 16, 24, 32 in both modes, with and without `steer_half`, and the
background boids as 3 × 10 and 1 × 50 in both modes. On the board, Ctrl-C out
of `code.py`, then at the REPL:

```python
import sys; sys.path.insert(0, "/src")
import bench_flock; bench_flock.run()
```

### Results

Pond scene on the board, default settings (koi flocking, 3 × 10 boids, all
direct), readout shown, HA reachable. `DEBUG` stats over 4 lines of 30 frames:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| Section 5, readout shown, 5 s poll (1 × 50 boids, grid) | 7.2–7.3 | 94.1–95.4 | 24.0–24.2 | 1.2–1.5 / 8.3 | 15.7–16.4 |
| M3: 3 × 10 boids, direct loop, merged neighbour loop | 10.1–11.0 | 52.0–55.6 | 21.0–24.3 | 0.2–3.5 / 50.6 | 15.7–16.2 |

- Physics drops by ~42 ms (−44 %) and fps goes from ~7 to ~11. This mixes
  three changes: 30 boids instead of 50, the direct loop instead of the grid,
  and the merged neighbour loop. `bench_flock.py` separates them.
- Render is slightly lower, as expected with 20 fewer boids to blit.
- One frame took 50.6 ms of net, against a worst of ~9 ms in section 5. It
  happened once in 120 frames and didn't repeat in the runs below (max 8–10 ms).

Tuning runs, same setup:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| 3 × 10 boids, perception 10, cohesion 10, koi wandering | 10.5–11.0 | 50.9–53.9 | 19.8–24.0 | 0.7–1.6 / 8.6 | 15.9–16.5 |
| 3 × 3 boids, perception 10, cohesion 10, koi wandering | 13.2–14.1 | 35.6–37.6 | 18.4–19.3 | 0.2–2.1 / 9.9 | 15.5–16.2 |

- The wider perception radius (5 → 10) and stronger cohesion (5 → 10) cost
  nothing measurable: the direct loop checks all 9 other boids in a flock
  whatever the radius. They're kept, to make up for the distance check
  leaving each boid fewer neighbours. The koi went back to flocking.
- Wandering koi save nothing visible, since steering is ~0.4 ms per koi and the
  spine ~5 ms either way.
- 3 × 3 boids saves ~16 ms (~0.75 ms per boid at perception 10), but 3 boids
  don't read as a school. Kept at 3 × 10; revisit after M3.5's float spine,
  which targets the ~15 ms the 3 koi cost.

`bench_flock.py` on the board: physics only (render off), ms per frame.
"Steer" is the flocking alone; "total" adds the move loop and
`Creature.set_state`, i.e. the koi spine.

| Flock | n | Steer direct | Steer grid | Steer direct, all | Steer grid, all | Total direct | Total grid |
| ----- | - | ------------ | ---------- | ----------------- | --------------- | ------------ | ---------- |
| koi   | 4  | 1.63  | 2.28  | 2.47  | 3.52  | 20.16  | 20.91  |
| koi   | 8  | 2.67  | 3.81  | 4.56  | 6.14  | 38.63  | 39.77  |
| koi   | 16 | 5.55  | 6.84  | 10.77 | 12.06 | 79.29  | 80.38  |
| koi   | 24 | 9.95  | 10.69 | 19.30 | 19.33 | 120.88 | 121.69 |
| koi   | 32 | 14.50 | 14.71 | 31.63 | 29.61 | 157.39 | 158.53 |
| boids | 3 × 10 | 9.42  | 12.80 | – | – | 12.77 | 16.28 |
| boids | 1 × 50 | 27.54 | 21.35 | – | – | 31.44 | 25.31 |

("all" = `steer_half=False`; totals are with `steer_half` on.)

- **Crossover: ~24–32 boids.** The direct loop wins below 24 and the two are
  even at 24–32. The grid only wins clearly at 50 (21.4 vs 27.5 ms). The
  `grid_min_boids` default is now **24**.
- **3 × 10 direct vs grid:** 9.4 vs 12.8 ms steer, so the direct loop is the
  right choice for the background flocks.
- **3 × 10 vs 1 × 50 (both with the new code):** 12.8 vs 25.3 ms total, about
  12.5 ms saved. The pond's physics fell by ~42 ms, so the other ~30 ms comes
  from the merged neighbour loop and the distance check (fewer neighbours) on
  the old grid path. The old code wasn't benched, so this is by elimination.
- **`steer_half` stays.** It saves 0.8 ms at n = 4 and 5 ms at n = 16. The
  saving is less than half, because the velocity list copies and loop setup
  cost the same either way.
- **The koi spine is the real cost:** ~4.6–5 ms per koi per frame in
  `set_state`, against ~0.4 ms of steering. The 3 koi in the pond cost ~15 ms
  of the ~52 ms physics. This is the `Vector`-allocating `CreatureSpine.move`
  that M3.5 replaces with the float spine.

### M3.5: float spine

`CreatureSpine` keeps its joints in flat `jx`/`jy` lists and each joint's unit
direction in `ux`/`uy`, and overrides `set_state`: one `sqrt` per joint and no
`Vector`s. The angle limit is a dot product against `cos(angle_constraint)`;
the clamp rotates by the precomputed cos/sin, so the spine does no trig at all.
`move(Vector)` is a thin wrapper, so `CircleBehavior` still works.

- Same result as the old spine: on a 300-frame path with tight turns, with
  and without the limit, the joints match the `Vector` version to ~1e-13 px.
- Desktop `bench_flock.py` (CPython, only a rough guide): koi total at n = 24
  0.19 → 0.09 ms, n = 32 0.24 → 0.12 ms, about half.
Pond on the board, same setup as M3 (3 koi, 3 × 10 boids, readout shown).
`DEBUG` stats over 3 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M3 (for comparison) | 10.1–11.0 | 52.0–55.6 | 21.0–24.3 | 0.2–3.5 / 50.6 | 15.7–16.2 |
| M3.5: float spine | 14.1–16.7 | 29.4–35.3 | 14.6–16.8 | 0.2–2.4 / 37.1 | 14.9–16.1 |

- Physics drops by ~20 ms (about −40 %), more than the ~15 ms the 3 koi
  spines cost in M3. The rest is probably less garbage collection, now that
  the spine creates no `Vector`s.
- Render drops by ~6 ms. `Fish.render` reads the flat lists and does the
  square fill inline, with no `Vector` joints and no helper call per joint.
- One frame had 37.1 ms of net, a one-off spike like the 50.6 ms one in M3.

`bench_flock.py` on the board, same columns as the M3 table:

| Flock | n | Steer direct | Steer grid | Steer direct, all | Steer grid, all | Total direct | Total grid |
| ----- | - | ------------ | ---------- | ----------------- | --------------- | ------------ | ---------- |
| koi   | 4  | 1.33  | 2.02  | 2.28  | 3.37  | 3.50  | 4.22  |
| koi   | 8  | 2.43  | 3.51  | 4.41  | 5.88  | 6.38  | 7.53  |
| koi   | 16 | 5.38  | 6.49  | 10.40 | 11.74 | 12.85 | 14.06 |
| koi   | 24 | 9.28  | 9.59  | 19.13 | 19.13 | 20.46 | 20.99 |
| koi   | 32 | 13.91 | 12.81 | 29.88 | 27.77 | 28.92 | 27.89 |
| boids | 3 × 10 | 11.76 | 14.85 | – | – | 15.34 | 18.93 |
| boids | 1 × 50 | 27.61 | 21.13 | – | – | 31.51 | 25.06 |

- **The spine is ~9× cheaper:** total minus steer (the move loop plus
  `set_state`) is ~0.5 ms per koi per frame, down from ~4.6 ms in M3 (n = 4:
  2.2 vs 18.5 ms; n = 32: 15.0 vs 142.9 ms). Koi totals drop from 20.2 to
  3.5 ms at n = 4 and from 38.6 to 6.4 ms at n = 8.
- **Steering is now the bigger half** of the koi cost at every size (e.g.
  9.3 of 20.5 ms at n = 24, and the steer-all column is the larger share from
  n = 16 on). The next koi gains are in `FlockingBehavior._steer`, not the
  spine.
- **The crossover is unchanged:** direct wins below 24, the two are even at
  24, and the grid edges ahead at 32. `grid_min_boids` stays at 24.
- **Budget for M4+:** ~20 fish in one flock would cost ~17 ms of physics
  (interpolating between n = 16 and 24), against ~140 ms with the old spine.
- The 1 × 50 boid rows match M3 (27.6 vs 27.5 ms direct steer). The 3 × 10
  rows are ~2.3 ms slower than M3's (11.8 vs 9.4 ms) although the boid code
  didn't change in M3.5 and the bench is seeded. Unexplained; worth a re-run
  before reading anything into it.

### M4: species table + generic body

The koi is now a `SpineCreature` built from the `KOI` species record, and the
pond builds one behavior per species from its motion record. `render` reads
per-joint radii precomputed by `set_size` instead of computing
`ceil(width * scale / 2)` per joint per frame. Pond on the board, same setup
as M3.5, `DEBUG` stats over 4 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M3.5 (for comparison) | 14.1–16.7 | 29.4–35.3 | 14.6–16.8 | 0.2–2.4 / 37.1 | 14.9–16.1 |
| M4: species + `SpineCreature` | 14.5–16.2 | 30.7–33.5 | 13.0–18.8 | 0.2–2.1 / 8.6 | 14.5–16.6 |

- Same as M3.5 within noise, as expected: on the desktop a seeded 200-frame
  run of the pond is pixel-identical. The 18.8 ms render line is also the
  slowest-fps line, with the biggest net spike; the 13.0 ms line is the best
  render so far, but 4 lines can't show whether the precomputed radii help.

`bench_flock.py` on the board, same columns as the M3.5 table:

| Flock | n | Steer direct | Steer grid | Steer direct, all | Steer grid, all | Total direct | Total grid |
| ----- | - | ------------ | ---------- | ----------------- | --------------- | ------------ | ---------- |
| koi   | 4  | 1.34  | 2.05  | 2.32  | 3.34  | 3.50  | 4.26  |
| koi   | 8  | 2.50  | 3.52  | 4.42  | 5.98  | 6.40  | 7.49  |
| koi   | 16 | 5.39  | 6.56  | 10.36 | 11.74 | 12.92 | 14.07 |
| koi   | 24 | 9.26  | 9.75  | 18.89 | 19.00 | 20.33 | 20.97 |
| koi   | 32 | 13.46 | 12.51 | 29.50 | 27.79 | 28.31 | 27.50 |
| boids | 3 × 10 | 16.18 | 18.74 | – | – | 19.55 | 23.16 |
| boids | 1 × 50 | 27.49 | 21.11 | – | – | 31.38 | 25.04 |

- **The koi rows match M3.5** to within ~0.5 ms everywhere, so
  `SpineCreature` costs the same as the old `Fish`. The crossover is
  unchanged (even at 24, grid ahead at 32).
- The 1 × 50 boid rows match M3 and M3.5 again (27.5 ms direct steer).
- **The 3 × 10 boid rows keep drifting up**, with no boid code changes:
  direct steer 9.4 (M3) → 11.8 (M3.5) → 16.2 ms (M4). The pond's `DEBUG`
  physics didn't move, so it looks like a bench artifact rather than a
  regression. One guess: these rows run after all the koi rows, on a heap
  that the earlier rows left more fragmented, and three small flocks
  allocate more separate lists than one big one. Re-running only the boid
  rows on a fresh boot would tell.

### M5: shared colors + CO2 brightness

The creature colors moved to shared palette slots (`creatures/colors.py`),
and the CO2 level rewrites them only when its brightness step changes (two
palette writes today), so a frame does no color work. Pond on the board,
same setup as M4, `DEBUG` stats over 5 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M4 (for comparison) | 14.5–16.2 | 30.7–33.5 | 13.0–18.8 | 0.2–2.1 / 8.6 | 14.5–16.6 |
| M5: shared colors + CO2 brightness | 14.4–16.1 | 30.6–35.4 | 11.1–17.8 | 0.2–2.0 / 8.6 | 14.8–16.7 |

- Same as M4 within noise, as expected; on the desktop a seeded 200-frame
  run at full brightness is pixel-identical to M4.
- The two fastest-render lines (11.1, 11.3 ms) are also the two slowest
  physics lines (35.1, 35.4 ms), so the split between the two looks noisy
  from line to line, while their sum stays at ~46–48 ms.

### M5.5: fins, tail and a rounder body

The first version drew the koi's fins and tail as lines: 17
`bitmaptools.draw_line` calls per fish per frame (4 rays per pectoral fin,
2 per pelvic fin, 5 for the tail), each with a few `floor()`s and multiplies
in Python around it. Pond on the board, `DEBUG` stats over 4 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M5 (for comparison) | 14.4–16.1 | 30.6–35.4 | 11.1–17.8 | 0.2–2.0 / 8.6 | 14.8–16.7 |
| M5.5a: fins + tail as lines | 12.8–13.3 | 29.8–34.9 | 23.7–29.4 | 0.2–3.1 / 31.4 | 15.0–16.0 |
| M5.5b: disc body, disc fins + tail | 14.0–14.6 | 31.9–33.5 | 18.6–20.9 | 0.2–2.1 / 8.6 | 15.0–16.3 |

- Render went up ~11 ms for 3 koi × 17 lines: **~0.2 ms per line**, almost
  all of it the Python around each call, not the native line drawing.
  On the desktop the lines added ~75 % to the koi render, about the same
  ratio.
- So per-frame line drawing is out for parts. The second version uses
  discs instead (`graphics/stamps.py`):
  - The body is one pre-drawn disc per joint (blit with
    `skip_source_index=0`) instead of a `fill_region` square, so it keeps its
    width at any heading and the head and tail come out round. Narrow tail
    joints whose disc is smaller than the link get a second disc at the
    midpoint to close the gap (2 extra blits per koi).
  - The fins and tail are solid shapes built from the same shared discs
    (`BlobPart`): 4 discs for the pectoral pair and 6 for the forked tail.
    A disc looks the same at any heading, so nothing is pre-drawn per
    direction, and a frame does a few multiplies and one blit per disc.
    That's 22 blits per koi per frame in total, and no trig.
  - Tried and set aside: pre-drawing each part at 16 headings per (size,
    fin color), so a frame does one `atan2` and one blit per part (2 per koi
    instead of 10). It costs ~7 KB of images per (size, fin color), built the
    first time a fish needs one. It's the fallback if the disc parts turn out
    slow on the board.
- **Desktop timings can't compare these.** Blinka's `blit` is a Python loop
  per pixel, so on the desktop the disc body looks ~4× slower than
  `fill_region` squares, while on the board both are native.
- Memory: discs are shared per (diameter, color), about 8 small bitmaps per
  color for the koi.
- **Result (M5.5b):** render is ~4–5 ms above M5 for 3 koi, so ~1.5 ms
  per koi for 22 blits (12 body, 10 parts) where M5 did 10 `fill_region`s.
  That's ~0.1 ms per blit with the offset math around it, about half the
  cost of a line. FPS is 14.0–14.6, against M5's 14.4–16.1. Physics is
  unchanged. Accepted for now, since it looks right.
- Left for later, cheapest first:
  - Tail 2 discs per lobe instead of 3 (−2 blits per koi).
  - Drop the midpoint gap fills where a slightly wider disc closes the gap
    (−2 blits).
  - Pre-draw the fins and tail per heading (−8 blits, +1 `atan2` per
    part, ~7 KB per size and fin color).
  - Recheck the per-koi cost with a full pond of 20 in M11. That's where it
    matters: at ~1.5 ms each, 20 fish are ~30 ms of render.

### M6: koi varieties + spots

Each koi now has a variety and seeded spots, drawn after the body as shared
discs with the same native blit (`SpineCreature._place_spots` converts them to
pixels on each size step, so a frame only lerps, offsets and blits). That's
one extra blit per spot: 0 for the solid varieties, ≤ 4 for kohaku, ≤ 9 for
sanke, 13 for asagi and 17 for shusui. Pond on the board, 3 koi with random
varieties, `DEBUG` stats over 5 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M5.5b (for comparison) | 14.0–14.6 | 31.9–33.5 | 18.6–20.9 | 0.2–2.1 / 8.6 | 15.0–16.3 |
| M6: varieties + spots | 12.9–14.4 | 31.8–34.9 | 20.2–24.0 | 0.2–2.3 / 8.9 | 15.0–16.4 |

- Render is ~1.5–3 ms above M5.5b, in line with ~0.1 ms per blit for a
  handful of spots across the 3 koi. Physics is unchanged.
- The lowest FPS line (12.9) is also the one with the highest net time
  (2.3 ms), so part of the spread is the HA poll, not the spots.
- Cost depends on the variety mix. If a pond of 20 (M11) turns out
  render-bound, the cheapest cut is `EDGES` at 5 per side instead of 7
  (−4 blits per asagi/shusui).

### M7: catfish + sturgeon

The pond gains one catfish and one sturgeon next to the 3 koi (now on the
narrower 8 px body). Per frame the sturgeon blits 12 body discs, 12 fin and
6 tail discs, 3 snout discs and 20 one-pixel scutes; the catfish 9 body
discs (plus tail fills), 4 fin and 6 tail discs and 0–10 mottle spots, then
writes its 2 × 5 whisker pixels from Python after a follow-the-leader step
per link. Both are on `WanderBehavior` (catfish edge hugging included).
`DEBUG` stats over 4 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M6 (for comparison) | 12.9–14.4 | 31.8–34.9 | 20.2–24.0 | 0.2–2.3 / 8.9 | 15.0–16.4 |
| M7: + catfish + sturgeon | 10.8–11.3 | 36.3–37.2 | 33.0–37.1 | 0.7–1.9 / 9.2 | 15.5–16.8 |

- Render is up ~13 ms for the two new fish, about 80 extra blits at the
  ~0.1–0.15 ms each seen in M5.5/M6, plus the whiskers. Physics is up
  ~3 ms for two more spines (the sturgeon's has 12 joints) and the wander
  steering.
- FPS drops ~2.5 below M6, more than "near M6".
- M7b: `SCUTES` at 5 per row instead of 7, staggered so the three rows don't
  line up into crossbars (14 pixels instead of 21), and 1 px spots written
  with `bitmap[x, y] = slot` instead of blitted. No change on the board:
  10.7–11.2 fps, physics 36.3–39.7 ms, render 32.9–38.9 ms. Tried and
  dropped: the sturgeon's long pectorals at 3 discs instead of 4 per side,
  since three 2 px discs can't cover a 7 px fin and its tip came loose as a
  dot on a diagonal.

#### Render cost per item (`bench_render.py`)

The board, one fish fully on screen at size 100, ms per call:

| Fish | Full | Body (discs) | Spots (count) | Parts | Spine |
| ---- | ---- | ------------ | ------------- | ----- | ----- |
| koi kohaku | 3.74 | 1.87 (13) | 0.41 (2) | fins 0.61, tail 0.88 | 0.71 |
| koi shusui | 5.17 | 1.90 (13) | 1.77 (17) | fins 0.62, tail 0.95 | 0.71 |
| catfish plain | 4.97 | 1.67 (10) | 0 | fins 0.62, tail 0.77, whiskers 2.00 | 0.68 |
| catfish mottled | 6.02 | 1.72 (10) | 0.96 (7) | fins 0.60, tail 0.79, whiskers 1.93 | 0.65 |
| sturgeon | 6.05 | 1.68 (14) | 1.92 (14 px) | fins 0.96 + 0.63, tail 0.79, snout 0.52 | 0.89 |

Pond water background: 4.59 ms.

- **Every drawn item costs ~0.1–0.15 ms, whatever draws it.** A spot blit
  is 0.10 ms (shusui), a body disc 0.14, a fin or tail disc ~0.15, and a
  1 px `bitmap[x, y]` write 0.14 (sturgeon), *slower* than blitting a 1 px
  disc. The cost is the Python per item (loop, float math, the call), not
  the blit, so the pixel-write path was reverted. Cutting render time means
  cutting the number of items.
- Disc size barely matters: the catfish's 10 discs up to 10 px wide cost
  less than the koi's 13 smaller ones.
- The catfish's whiskers (2 × 5 chain links with a `sqrt` each, plus 12
  pixel writes) are its most expensive part at ~2 ms, more than its body.
- The spine update is 0.65–0.9 ms per fish; for 5 fish that's ~3.7 ms of
  the ~37 ms physics.

#### Open options (not applied; kept as-is for the look)

Render cost scales with the number of drawn items (~0.1–0.15 ms each), so
these are the cuts to reach for if the full pond (10 fish + the turtle,
M11) is too slow. Savings are from the table above; rerun
`bench_render.py` after any change.

| Cut | Saves | Look |
| --- | ----- | ---- |
| `Tail` lobes at 2 discs instead of 3 (every species) | ~0.3 ms per fish | shorter, blunter fork |
| Sturgeon `SCUTES` back row only (5 instead of 14) | ~1.2 ms | spots down the back only, not the sides |
| `Whiskers` chain stepped every other frame (pixels still drawn every frame) | ~0.4 ms per catfish (estimate: the chain math is roughly the half of the 2 ms that isn't pixel writes) | shape lags a frame on turns |
| `Whiskers(length=3)` instead of 4.5 (4 pixels each instead of 6) | ~0.6 ms per catfish | shorter whiskers |
| `EDGES` at 5 per side instead of 7 (asagi, shusui; see M6) | ~0.4 ms per fish | sparser side markings |
| Long `Fins` at 3 discs instead of 4 | ~0.3 ms per sturgeon | tried in M7b: the tip comes loose on a diagonal; would need a wider tip disc |

Not worth it: drawing 1 px spots with `bitmap[x, y]` (0.14 ms per pixel,
slower than a 1 px blit at 0.10 ms), and shrinking discs (size barely
changes a blit's cost).

### M8: turtle

The pond gains one turtle (size 90). Per frame it draws 2 body discs (head
and tail; the joint under the shell has width 0, so it gets no disc and no
gap fill), 8 flipper discs (one of 6 pre-worked paddle phases), and the
shell as **one pre-drawn sprite**: 16 headings, picked with one `atan2`.
The shell's seeded marks are baked into those sprites, so they cost nothing
per frame. Width 0 saves the 3 body blits the turtle would otherwise draw
under its own shell. `DEBUG` stats over 5 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M7b (for comparison) | 10.7–11.2 | 36.3–39.7 | 32.9–38.9 | — | — |
| M8: + turtle | 10.0–10.7 | 37.4–40.3 | 36.9–41.8 | 0.2–2.2 / 9.2 | 15.4–16.2 |

- About 0.5 fps below M7b. Render is up ~3 ms and physics ~1–2 ms (one
  more spine and wander steering), roughly what the bench predicts.

`bench_render.py` on the board, ms per call:

| Fish | Full | Body (discs) | Spots (count) | Parts | Spine |
| ---- | ---- | ------------ | ------------- | ----- | ----- |
| koi kohaku | 2.03 | 1.04 (13) | 0.28 (2) | fins 0.33, tail 0.43 | 0.44 |
| koi shusui | 2.93 | 1.10 (13) | 1.04 (17) | fins 0.33, tail 0.43 | 0.43 |
| catfish plain | 3.10 | 1.01 (10) | 0.07 (0) | fins 0.32, tail 0.39, whiskers 1.18 | 0.40 |
| catfish mottled | 3.62 | 0.99 (10) | 0.54 (7) | fins 0.31, tail 0.41, whiskers 1.22 | 0.40 |
| sturgeon | 3.23 | 0.96 (14) | 0.96 (14 px) | fins 0.50 + 0.31, tail 0.41, snout 0.27 | 0.54 |
| turtle slider | 1.55 | 0.21 (2) | 0 | flippers 0.71, shell 0.58 | 0.18 |
| turtle box | 1.53 | 0.21 (2) | 0 | flippers 0.73, shell 0.58 | 0.18 |

Pond water background: 2.66 ms.

- **The turtle is the cheapest creature in the pond** at ~1.5 ms, under
  the plain koi.
- The shell's one blit costs 0.58 ms, about four disc blits: the 17 × 17
  sprite is the biggest stamp in the pond, plus the `atan2` and the
  clipped `stamps.blit` call. The flippers' 8 discs are ~0.09 ms each, in
  line with everything else.
- **Every row is ~40 % below the M7 table** (koi kohaku 2.03 against
  3.74, pond water 2.66 against 4.59), including fish whose code didn't
  change. That's from the run conditions, not M8, so compare rows within
  one run, not across runs.
- Shell sprite memory: **4208 bytes** for 16 sprites of 17 × 17 at size
  100 (the bench's size). At the pond's size 90 they're 15 × 15, a little
  less. Each size step rebuilds them, and the old set is freed.

### M9: genomes and pond persistence

The fish now come from the saved pond (`behaviors/lifecycle.py`), so sizes
and varieties are each fish's own instead of the hard-coded M8 set. The
board's pond for this run: koi chagoi 88, kohaku 75, showa 69 (M8: 100, 50,
50), catfish 19 (age 5 h, still at the 30 % growth step; M8: 100), sturgeon
105 (M8: 100) and turtle 74 (M8: 90). The koi also lost a joint (9 joints,
widths `(6, 8, 8, 8, 7, 6, 5, 3, 2)`), which is one disc fewer per koi, and
`link_size` is no longer rounded up. `DEBUG` stats over 5 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M8 (for comparison) | 10.0–10.7 | 37.4–40.3 | 36.9–41.8 | 0.2–2.2 / 9.2 | 15.4–16.2 |
| M9: saved pond, 9-joint koi | 10.4–10.9 | 37.0–39.2 | 35.3–37.5 | 0.3–3.5 / 46.1 | 15.0–16.5 |

- The same as M8 or a little better. The genome code only runs at startup
  and at save time, so it adds nothing per frame. The small render gain
  fits the koi's missing disc and the tiny catfish; with a different pond
  the numbers will move by a fraction of a ms either way.
- The 46 ms net maximums are HA polls, not M9.

### M10: lifecycle + reproduction

The lifecycle (`behaviors/lifecycle.py`) checks the pond once per real
second, and at `POND_TIME_SCALE` 1 it only does work when a pond hour has
passed, so it should add nothing per frame. Same pond size as M9 (the
board's saved pond, no full 10-fish pond yet; that's M11). `DEBUG` stats
over 3 lines:

| Setup | FPS | Physics (ms) | Render (ms) | Net avg / max (ms) | Refresh (ms) |
| ----- | --- | ------------ | ----------- | ------------------ | ------------ |
| M9 (for comparison) | 10.4–10.9 | 37.0–39.2 | 35.3–37.5 | 0.3–3.5 / 46.1 | 15.0–16.5 |
| M10: lifecycle on, scale 1 | 10.4–10.7 | 37.6–40.7 | 34.0–40.0 | 0.2–2.2 / 38.6 | 15.0–16.5 |

- Within noise of M9. The once-per-second check is a float add and a
  compare; aging, breeding and growth only run once per pond hour.
- The 38.6 ms net maximum is an HA poll, not M10.
