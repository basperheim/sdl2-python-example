# Hex Strategy Demo – Modding Notes

This document collects tips, reference snippets, and gotchas for extending the
Python-driven hex strategy sandbox. Everything below assumes you are working in
`python_strategy_demo.py` unless noted otherwise.

---

## 1. Adjusting Grid Dimensions & Scale

### Change map radius
```python
class HexStrategyGame:
    def __init__(self):
        # ...
        self.hex_radius = 7  # previously 5 → now larger board
```
The grid uses axial coordinates with a radius-limited hexagon. Increasing the
radius grows the map in every direction. After changing the radius, the grid
auto-recomputes camera zoom to keep the world on screen.

### Alter the default hex size
Set `self.hex_size` before `_configure_hex_size` runs. The method currently
overrides the value using the terrain art dimensions (so tiles automatically
fit). If you want a fixed size, remove or tweak the auto-fit logic:
```python
    def _configure_hex_size(self):
        self.hex_size = 64.0  # static
```

### Switching to pointy-top hexes
The C layer supports both orientations, but the math helpers are tailored to
flat-top. Swapping would require:
1. Update `hl_set_grid(..., flat_top=0)` in `initialize`.
2. Replace `axial_to_pixel_flat` and `pixel_to_axial_flat` in `src/hexlib.c`
   with the pointy-top variants (see Red Blob Games for formulas).

---

## 2. Terrain Definitions

Terrain entries live in `TERRAIN_DEFS`. Each dictionary becomes a `TerrainType`.

```python
TERRAIN_DEFS = [
    {
        "name": "forest",
        "slot": 3,
        "path": "assets/terrain_forest.png",
        "placeholder": (60, 130, 60),  # if the file is missing
        "overlay": (10, 40, 10, 35),   # subtle tint (RGBA)
        "passable": True,
        "scale": 1.0,                  # stretch relative to the default tile bounds
    },
]
```

**Texture slots**  
Slots must stay below `HL_MAX_TEXTURE_SLOTS` (64). Reusing a slot will replace
that texture the next time `ensure_texture` runs.

**Overlay color**  
The overlay is rendered over the tile with alpha blending and is handy for
highlighting ownership, resource output, flood warnings, etc.

---

## 3. Units & Class Attributes

Unit definitions mirror terrain. To store additional per-unit data:

```python
UNIT_DEFS = [
    {
        "name": "scout",
        "slot": 10,
        "path": "assets/unit_scout.png",
        "placeholder": (220, 220, 80),
        "move_range": 3,
        "scale": 0.7,
        "vision": 4,           # <--- custom attribute
        "gather_rate": {"food": 1},
    }
]
```

Extend `UnitType.__init__` to accept the new keys. Example:
```python
class UnitType:
    def __init__(self, name, slot, rel_path, placeholder_rgb,
                 move_range, scale, vision=2, gather_rate=None):
        self.vision = vision
        self.gather_rate = gather_rate or {}
```

Attach runtime state to `Unit` instances. For example, to track current health
and cargo:
```python
class Unit:
    def __init__(self, unit_type, q, r):
        self.unit_type = unit_type
        self.q = q
        self.r = r
        self.health = 100
        self.cargo = {"food": 0}
```

---

## 4. Tile Resources & Metadata

Tiles currently hold terrain + optional unit. To add resources, expand `Tile`.

```python
class Tile:
    def __init__(self, q, r, terrain):
        self.q = q
        self.r = r
        self.terrain = terrain
        self.unit = None
        self.resources = {"food": 0, "ore": 0}
```

Populate data during `_build_world`:
```python
tile.resources["food"] = rng_int(2)  # custom helper
if terrain.name == "mountain":
    tile.resources["ore"] = rng_int(5)
```

Use this metadata during gameplay (e.g., to restrict moves or determine yields).

---

## 5. Camera & Input Hooks

Key constants:
```python
SDLK_W = ord("w")
SDLK_A = ord("a")
SDLK_S = ord("s")
SDLK_D = ord("d")
```

Add new commands by extending `_handle_key_down`/`_handle_key_up`. Example:

```python
from enum import Enum

class GameMode(Enum):
    NORMAL = 0
    BUILD = 1

class HexStrategyGame:
    def __init__(self):
        self.mode = GameMode.NORMAL
        # ...

    def _handle_key_down(self, key):
        self.keys_down.add(key)
        if key == ord("b"):
            self.mode = GameMode.BUILD
```

---

## 6. Rendering Notes

- Textures are scaled to fill the horizontal diameter of the hex. Tall images
  are gently stretched to avoid gaps. Set `terrain_scale`/`unit_scale`
  to tweak per-tile sizing at runtime.
- Coordinate labels come from `hl_set_debug_labels`. To swap out the built-in
  bitmap font for SDL_ttf, you would extend the C renderer accordingly.

---

## 7. Resource Gathering Example

Sketch of a simple gather action:

```python
def gather(self, unit):
    tile = self.tiles[(unit.q, unit.r)]
    food = tile.resources.get("food", 0)
    if food <= 0:
        return False
    unit.cargo["food"] += 1
    tile.resources["food"] = food - 1
    return True
```

Call `gather(selected_unit)` when the player presses a hotkey. You could surface
the remaining resources via overlays or debug labels.

---

## 8. Useful Helpers

- `axial_neighbors(q, r)` yields the 6 adjacent axial coordinates.
- `hex_distance(a, b)` returns the number of steps between two hexes.
- `random_from_seed(seed)` gives a deterministic RNG for world generation.

---

## 9. Customising Draw/Blit Positions

### What Python controls today
Each frame `push_tiles()` builds a list of `HL_TileInstance` structs and sends
them to C with `lib.hl_set_tiles(...)`. A tile instance contains:

- axial coordinates (`q`, `r`)
- terrain/unit texture slot indices
- per-layer scale multipliers
- overlay colour (RGBA)
- per-tile pixel offsets (`offset_x`, `offset_y`)

The actual **axial → pixel** conversion happens inside `src/hexlib.c`
(`axial_to_pixel_flat`). Camera offset/zoom are also applied in C. Without
changing native code, you can only influence tile positions indirectly through
the coordinates, offsets, and the camera transform.

### Quick adjustments in Python
1. **Pan / zoom everything** by editing `self.camera_offset` and
   `self.camera_zoom`, then calling `sync_camera()` (already used in the demo).
2. **Switch axial layout** (e.g. mirror or rotate axes) by preprocessing the
   `q`, `r` values you send. Example: `instances.append(..., q, -q-r, ...)`.
   This is useful for debugging stagger issues without touching C.

### Per-tile pixel offsets (built-in)
`HL_TileInstance` already exposes `offset_x` and `offset_y`. The renderer adds
these after converting axial coordinates to pixel space, so Python can animate
or stagger tiles directly:
```python
inst = HL_TileInstance()
inst.q, inst.r = q, r
inst.offset_x = math.sin(time_accum + q * 0.35) * 3.0
inst.offset_y = 0.0
```
The existing demo uses this to bob water tiles slightly (`push_tiles`).

### Alternative: Expose the projection helper
Another route is to export a function like `hl_axial_to_pixel(q, r, &x, &y)`
via `ctypes`. Python would then compute pixel positions itself and could render
additional sprites with custom offsets (e.g. UI overlays) without duplicating
the math.

### Debug tips while tweaking
- Enable the coordinate labels (`lib.hl_set_debug_labels`) to verify spacing.
- Log the world-space camera offset so you know how far you have panned.
- If textures look misaligned, check the asset aspect ratio. High `terrain_scale`
  values may stretch the art vertically and expose gaps.

---

## 9. Testing Checklist After Changes

1. `cmake --build build` (recompile native layer).
2. `python3 python_strategy_demo.py` (manual smoke test).
3. Ensure camera controls still function (WASD + `-`/`=` zoom).
4. Verify right-click moves respect new terrain rules/resources.

Document new controls or data in `README.md` (Controls section) so future-you
remembers how to trigger them.

---

Happy hacking! Update this file with your findings so the modding backlog grows
alongside the game.*** End Patch```}{
