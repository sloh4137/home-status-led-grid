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

| Step                                | Boids | FPS | Physics (ms) | Render (ms) | Refresh (ms) |
| ----------------------------------- | ----- | --- | ------------ | ----------- | ------------ |
| Baseline                            | 100   | 1.2 | 662.6        | 135.0       | 17.6         |
| Fixing spatialized grid             | 100   | 1.5 | 501.7        | 132.5       | 18.3         |
| Combining forces into single loop   | 100   | 1.8 | 392.0        | 136.4       | 17.9         |
| Store flat array of x and y         | 100   | 2.7 | 195.4        | 154.9       | 17.7         |
| Swapping to ulab (reverted)         | 100   | 1.4 | 587.2        | 127.8       | 19.7         |
| Steer only half the boids at a time | 100   | 3.1 | 144.4        | 158.5       | 19.4         |
| Have flocking own boid positions    | 100   | 3.8 | 102.0        | 140.4       | 17.3         |
| Limiting avoidance checks           | 100   | 4.0 | 93.4         | 139.4       | 18.5         |

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
- [ ] Merge `get_neighbors` into `flock`, with `in_fov` inlined. Each steered boid
      still builds a `neighbors` list, and `flock` loops over it again,
      recomputing `dx`, `dy`, and `dist_sq`. One loop that checks the field of
      view and adds to the sums inline removes the list, the second pass, and a
      method call per candidate.

## 3. Render

### Cheap

- [x] Don't redraw the `FishBoid` sprite every frame: pre-build the 8 facing sprites
      as 3x3 bitmaps once and swap with `self.grid.bitmap = SPRITES[facing]` (same
      size, so displayio allows it), only when `facing` changes.
- [x] Skip `render()` for boids outside the visible window (`outside_window_size`
      lets most of the swim area be off screen).

### More work

- [ ] See the single full-screen bitmap under Refresh; it also replaces the
      per-boid sprite updates.

## 4. Refresh

### Cheap

- None yet. Refresh is only ~2% of the frame, so it's low priority.

### More work

- [ ] Replace the per-boid TileGrids with one full-screen 64x64 bitmap: each frame,
      erase the previous pixels and draw the new ones (consider `bitmaptools`), so
      displayio only composites one layer.
