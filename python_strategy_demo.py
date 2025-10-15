import ctypes
import math
import os
import sys
import time
from collections import deque


def _load_lib():
    """Locate and load the hexlib shared library that the Python side drives.

    We try platform-specific locations inside the repo first (build tree and
    project root). If that fails, fall back to the platform's shared library
    resolution rules so a system-installed copy can still be picked up.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    if sys.platform == "darwin":
        candidates = [os.path.join(here, "build", "libhexlib.dylib"),
                      os.path.join(here, "libhexlib.dylib")]
    elif sys.platform.startswith("linux"):
        candidates = [os.path.join(here, "build", "libhexlib.so"),
                      os.path.join(here, "libhexlib.so")]
    elif os.name == "nt":
        candidates = [os.path.join(here, "build", "hexlib.dll"),
                      os.path.join(here, "hexlib.dll")]
    for c in candidates:
        if os.path.exists(c):
            return ctypes.CDLL(c)
    suffix = ".dll" if os.name == "nt" else (".dylib" if sys.platform == "darwin" else ".so")
    return ctypes.CDLL("hexlib" + suffix)


# Load the native renderer once; every subsequent call into hexlib uses this handle.
lib = _load_lib()


class HL_Color(ctypes.Structure):
    """ctypes mirror of the hexlib RGBA colour struct (8-bit channels)."""

    _fields_ = [("r", ctypes.c_uint8),
                ("g", ctypes.c_uint8),
                ("b", ctypes.c_uint8),
                ("a", ctypes.c_uint8)]


class HL_TileInstance(ctypes.Structure):
    """Struct describing one tile render request we send to hexlib each frame."""

    _fields_ = [("q", ctypes.c_int32),          # axial q coordinate
                ("r", ctypes.c_int32),          # axial r coordinate
                ("terrain_tex", ctypes.c_int32),  # texture slot index for terrain (-1 = none)
                ("unit_tex", ctypes.c_int32),     # texture slot index for unit sprite (-1 = none)
                ("terrain_scale", ctypes.c_float),  # scale multiplier for terrain blit
                ("unit_scale", ctypes.c_float),     # scale multiplier for unit blit
                ("overlay", HL_Color),             # overlay tint rendered above terrain/unit
                ("offset_x", ctypes.c_float),      # pixel offset applied after projection
                ("offset_y", ctypes.c_float)]


class HL_DebugLabel(ctypes.Structure):
    """Tiny bitmap label (q,r,text) to help debug layout in the renderer."""

    _fields_ = [("q", ctypes.c_int32),
                ("r", ctypes.c_int32),
                ("text", ctypes.c_char * 16)]


# Configure lib prototypes so ctypes knows the argument/return layout for each C function.
lib.hl_init.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
lib.hl_init.restype = ctypes.c_int
lib.hl_shutdown.argtypes = []
lib.hl_set_grid.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_int]
lib.hl_set_grid.restype = None
lib.hl_set_clear_color.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8]
lib.hl_set_clear_color.restype = None
lib.hl_set_tiles.argtypes = [ctypes.POINTER(HL_TileInstance), ctypes.c_int]
lib.hl_set_tiles.restype = None
lib.hl_clear_tiles.argtypes = []
lib.hl_clear_tiles.restype = None
lib.hl_load_texture.argtypes = [ctypes.c_int, ctypes.c_char_p]
lib.hl_load_texture.restype = ctypes.c_int
lib.hl_unload_texture.argtypes = [ctypes.c_int]
lib.hl_unload_texture.restype = None
lib.hl_clear_textures.argtypes = []
lib.hl_clear_textures.restype = None
lib.hl_step.argtypes = [ctypes.c_float]
lib.hl_step.restype = None
lib.hl_poll_event.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
lib.hl_poll_event.restype = ctypes.c_int
lib.hl_query_texture.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
lib.hl_query_texture.restype = ctypes.c_int
lib.hl_set_camera.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
lib.hl_set_camera.restype = None
lib.hl_set_debug_labels.argtypes = [ctypes.POINTER(HL_DebugLabel), ctypes.c_int]
lib.hl_set_debug_labels.restype = None


# Paths and window defaults used throughout the script.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800


# Declarative terrain configuration; each dict is converted into a TerrainType.
TERRAIN_DEFS = [
    {
        "name": "grass",
        "slot": 0,
        "path": "assets/terrain_grass.png",
        "placeholder": (70, 145, 84),
        "overlay": (0, 0, 0, 0),
        "passable": True,
        "scale": 1.0,
    },
    {
        "name": "water",
        "slot": 1,
        "path": "assets/terrain_water.png",
        "placeholder": (58, 105, 190),
        "overlay": (0, 0, 0, 0),
        "passable": False,
        "scale": 1.0,
    },
    {
        "name": "mountain",
        "slot": 2,
        "path": "assets/terrain_mountain.png",
        "placeholder": (145, 141, 132),
        "overlay": (0, 0, 0, 0),
        "passable": False,
        "scale": 1.0,
    },
]


# Unit blueprints mirror terrain definitions and become UnitType objects.
UNIT_DEFS = [
    {
        "name": "scout",
        "slot": 10,
        "path": "assets/unit_scout.png",
        "placeholder": (220, 220, 80),
        "move_range": 3,
        "scale": 0.05,
    }
]


# Axial direction vectors (flat-top layout) used for neighbor traversal.
HEX_DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

# Keyboard constants we care about (SDL keycodes).
SDLK_W = ord("w")
SDLK_A = ord("a")
SDLK_S = ord("s")
SDLK_D = ord("d")
SDLK_MINUS = 45           # '-'
SDLK_EQUALS = 61          # '='
SDLK_KP_MINUS = 1073741910
SDLK_KP_PLUS = 1073741911


def ensure_placeholder_image(path, rgb, size=96):
    """Generate a fallback BMP if the expected asset is missing."""
    if rgb is None:
        return
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_solid_bmp(path, rgb, size=size)


def write_solid_bmp(path, rgb, size=96):
    """Minimal 32-bit BMP writer used to craft placeholder textures on the fly."""
    r, g, b = rgb
    a = 255
    width = height = size
    row = bytes([b, g, r, a] * width)
    pixel_data = row * height
    file_header = bytearray()
    file_header.extend(b"BM")
    file_size = 14 + 40 + len(pixel_data)
    file_header.extend(file_size.to_bytes(4, "little"))
    file_header.extend((0).to_bytes(2, "little"))
    file_header.extend((0).to_bytes(2, "little"))
    file_header.extend((54).to_bytes(4, "little"))

    dib = bytearray()
    dib.extend((40).to_bytes(4, "little"))
    dib.extend(width.to_bytes(4, "little", signed=True))
    dib.extend(height.to_bytes(4, "little", signed=True))
    dib.extend((1).to_bytes(2, "little"))
    dib.extend((32).to_bytes(2, "little"))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend(len(pixel_data).to_bytes(4, "little"))
    dib.extend((2835).to_bytes(4, "little", signed=True))
    dib.extend((2835).to_bytes(4, "little", signed=True))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend((0).to_bytes(4, "little"))

    with open(path, "wb") as fh:
        fh.write(file_header)
        fh.write(dib)
        fh.write(pixel_data)


def resolve_path(rel_path):
    """Normalise an asset path so both absolute and relative entries work."""
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.join(BASE_DIR, rel_path)


def make_color(r, g, b, a=255):
    """Clamp and pack RGBA components into an HL_Color struct."""
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    a = max(0, min(255, int(a)))
    return HL_Color(r, g, b, a)


def axial_neighbors(q, r):
    """Yield the six neighboring axial coordinates around (q, r)."""
    for dq, dr in HEX_DIRECTIONS:
        yield q + dq, r + dr


def hex_distance(a, b):
    """Return the axial distance (in moves) between two hex coordinates."""
    aq, ar = a
    bq, br = b
    ax, az = aq, ar
    ay = -ax - az
    bx, bz = bq, br
    by = -bx - bz
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


class TerrainType:
    """Runtime wrapper for terrain metadata and texture bookkeeping."""

    def __init__(self, name, slot, rel_path, placeholder_rgb, overlay_rgba, passable, scale):
        self.name = name
        self.slot = slot
        self.rel_path = rel_path
        self.placeholder_rgb = placeholder_rgb
        self.overlay_rgba = overlay_rgba
        self.passable = passable
        self.loaded = False
        self.scale = scale
        self.pixel_width = 0
        self.pixel_height = 0

    def ensure_texture(self):
        path = resolve_path(self.rel_path)
        ensure_placeholder_image(path, self.placeholder_rgb)
        ok = lib.hl_load_texture(self.slot, path.encode("utf-8"))
        self.loaded = bool(ok)
        if not self.loaded:
            print(f"[terrain] Texture load failed for {self.name}: {path}")
            return False
        width = ctypes.c_int(0)
        height = ctypes.c_int(0)
        if lib.hl_query_texture(self.slot, ctypes.byref(width), ctypes.byref(height)):
            self.pixel_width = width.value
            self.pixel_height = height.value
        return True

    def base_overlay(self):
        return make_color(*self.overlay_rgba)


class UnitType:
    """Holds shared data for a given unit archetype (textures, stats)."""

    def __init__(self, name, slot, rel_path, placeholder_rgb, move_range, scale):
        self.name = name
        self.slot = slot
        self.rel_path = rel_path
        self.placeholder_rgb = placeholder_rgb
        self.move_range = move_range
        self.loaded = False
        self.scale = scale

    def ensure_texture(self):
        path = resolve_path(self.rel_path)
        ensure_placeholder_image(path, self.placeholder_rgb, size=82)
        ok = lib.hl_load_texture(self.slot, path.encode("utf-8"))
        self.loaded = bool(ok)
        if not self.loaded:
            print(f"[unit] Texture load failed for {self.name}: {path}")
            return False
        return True


class Tile:
    """Represents one map cell with terrain, optional unit, and custom data."""

    def __init__(self, q, r, terrain):
        self.q = q
        self.r = r
        self.terrain = terrain
        self.unit = None

    def passable_for(self, unit):
        if not self.terrain.passable:
            return False
        if self.unit and self.unit is not unit:
            return False
        return True


class Unit:
    """Mutable state for a unit instance (position, attributes)."""

    def __init__(self, unit_type, q, r):
        self.unit_type = unit_type
        self.q = q
        self.r = r

    @property
    def move_range(self):
        return self.unit_type.move_range

    @property
    def texture_slot(self):
        return self.unit_type.slot if self.unit_type.loaded else -1


class HexStrategyGame:
    """Main game controller: world generation, input, rendering bridge."""

    def __init__(self):
        self.terrain_types = {}
        self.unit_types = {}
        self.tiles = {}
        self.units = []
        self.selected_unit = None
        self.reachable = set()
        self.hover_hex = None
        self.running = True
        self.hex_radius = 5
        self.hex_size = 48.0
        self.camera_offset = [0.0, 0.0]
        self.camera_zoom = 1.0
        self.keys_down = set()
        self.pan_speed = 320.0  # pixels per second, before zoom scaling
        self.min_zoom = 0.4
        self.max_zoom = 3.5
        self.time_accum = 0.0

    def initialize(self):
        """Create terrain/unit registries, generate the hex map, prime C renderer."""
        os.makedirs(ASSET_DIR, exist_ok=True)
        self._bootstrap_types()
        self._load_textures()
        self._configure_hex_size()
        self._build_world()
        self._spawn_units()
        grid_extent = self.hex_radius * 2 + 1
        rows = cols = grid_extent
        grid_w = (1.5 * (cols - 1) * self.hex_size) + 2.0 * self.hex_size
        grid_h = (math.sqrt(3.0) * self.hex_size * (rows + 0.5)) + self.hex_size
        fit_zoom = min(1.0, WINDOW_WIDTH / grid_w, WINDOW_HEIGHT / grid_h)
        self.camera_zoom = max(self.min_zoom, min(self.max_zoom, fit_zoom))
        self.camera_offset = [0.0, 0.0]
        lib.hl_set_grid(grid_extent, grid_extent, ctypes.c_float(self.hex_size), 1)
        lib.hl_set_clear_color(18, 20, 26, 255)
        self.sync_camera()

    def _bootstrap_types(self):
        """Hydrate TerrainType/UnitType objects from static definitions."""
        for entry in TERRAIN_DEFS:
            terrain = TerrainType(
                entry["name"],
                entry["slot"],
                entry["path"],
                entry["placeholder"],
                entry["overlay"],
                entry["passable"],
                entry.get("scale", 1.0),
            )
            self.terrain_types[terrain.name] = terrain
        for entry in UNIT_DEFS:
            unit = UnitType(
                entry["name"],
                entry["slot"],
                entry["path"],
                entry["placeholder"],
                entry["move_range"],
                entry.get("scale", 0.7),
            )
            self.unit_types[unit.name] = unit

    def _load_textures(self):
        """Load every referenced texture (and placeholders) into hexlib slots."""
        for terrain in self.terrain_types.values():
            terrain.ensure_texture()
        for unit_type in self.unit_types.values():
            unit_type.ensure_texture()

    def _configure_hex_size(self):
        """Set hex_size based on grass art so tiles align tightly."""
        base = self.terrain_types.get("grass")
        if base and base.pixel_width and base.pixel_height:
            effective_width = base.pixel_width * base.scale
            effective_height = base.pixel_height * base.scale
            size_from_width = effective_width * 0.5
            size_from_height = effective_height / math.sqrt(3.0)
            size = min(size_from_width, size_from_height)
            self.hex_size = max(32.0, size)
        else:
            self.hex_size = max(self.hex_size, 32.0)

    def sync_camera(self):
        """Push the current camera state to C so rendering stays in sync."""
        lib.hl_set_camera(
            ctypes.c_float(self.camera_offset[0]),
            ctypes.c_float(self.camera_offset[1]),
            ctypes.c_float(self.camera_zoom),
        )

    def update(self, dt):
        """Advance any time-based animation counters."""
        if dt > 0.0:
            self.time_accum += dt

    def update_camera(self, dt):
        """Apply WASD movement to the camera and clamp zoom range."""
        move_delta = 0.0
        if dt > 0.0:
            move_delta = self.pan_speed * dt / max(self.camera_zoom, 0.2)

        if SDLK_W in self.keys_down:
            self.camera_offset[1] += move_delta
        if SDLK_S in self.keys_down:
            self.camera_offset[1] -= move_delta
        if SDLK_A in self.keys_down:
            self.camera_offset[0] += move_delta
        if SDLK_D in self.keys_down:
            self.camera_offset[0] -= move_delta

        self.camera_zoom = max(self.min_zoom, min(self.max_zoom, self.camera_zoom))
        self.sync_camera()

    def _build_world(self):
        """Populate self.tiles with terrain based on simple heuristics."""
        rng = random_from_seed(42)
        radius = self.hex_radius
        grass = self.terrain_types["grass"]
        water = self.terrain_types["water"]
        mountain = self.terrain_types["mountain"]

        for q in range(-radius, radius + 1):
            r_min = max(-radius, -q - radius)
            r_max = min(radius, -q + radius)
            for r in range(r_min, r_max + 1):
                terrain = self._pick_terrain(q, r, radius, rng, grass, water, mountain)
                tile = Tile(q, r, terrain)
                self.tiles[(q, r)] = tile

        # Ensure starting area stays passable
        if (0, 0) in self.tiles:
            self.tiles[(0, 0)].terrain = grass
        if (1, -1) in self.tiles:
            self.tiles[(1, -1)].terrain = grass
        if (0, -1) in self.tiles:
            self.tiles[(0, -1)].terrain = grass

    def _pick_terrain(self, q, r, radius, rng, grass, water, mountain):
        """Very simple terrain generator that biases edges to mountains/water."""
        if r <= -3:
            return water
        if q + r > radius - 1:
            return mountain
        if abs(q) <= 1 and abs(r) <= 1:
            return grass
        roll = rng()
        if roll < 0.12:
            return water
        if roll < 0.22:
            return mountain
        return grass

    def _spawn_units(self):
        """Drop initial units onto the map (currently just a single scout)."""
        scout_type = self.unit_types["scout"]
        unit = Unit(scout_type, 0, 0)
        self.units.append(unit)
        self.tiles[(0, 0)].unit = unit

    def handle_event(self, ev, q, r):
        """Route events coming from C to Python helpers."""
        if ev == 1:
            self.running = False
        elif ev == 2:
            self._handle_left_click(q, r)
        elif ev == 4:
            self._handle_right_click(q, r)
        elif ev == 3:
            self._handle_hover(q, r)
        elif ev == 5:
            self._handle_key_down(q)
        elif ev == 6:
            self._handle_key_up(q)

    def _handle_left_click(self, q, r):
        tile = self.tiles.get((q, r))
        if not tile:
            self.selected_unit = None
            self.reachable.clear()
            return
        if tile.unit:
            self.selected_unit = tile.unit
            self.reachable = self._compute_reachable(tile.unit)
        else:
            self.selected_unit = None
            self.reachable.clear()

    def _handle_right_click(self, q, r):
        if not self.selected_unit:
            return
        if (q, r) not in self.tiles:
            return
        if (q, r) not in self.reachable:
            return
        target_tile = self.tiles[(q, r)]
        if not target_tile.passable_for(self.selected_unit):
            return
        self._move_unit(self.selected_unit, target_tile)

    def _handle_hover(self, q, r):
        if (q, r) in self.tiles:
            self.hover_hex = (q, r)
        else:
            self.hover_hex = None

    def _handle_key_down(self, key):
        self.keys_down.add(key)  # tracked so update_camera knows which directions to apply
        if key in (SDLK_MINUS, SDLK_KP_MINUS):
            self.camera_zoom *= 0.9
        elif key in (SDLK_EQUALS, SDLK_KP_PLUS):
            self.camera_zoom *= 1.1

    def _handle_key_up(self, key):
        self.keys_down.discard(key)

    def _move_unit(self, unit, target_tile):
        """Relocate a unit and recompute its reachable tiles."""
        origin_tile = self.tiles[(unit.q, unit.r)]
        origin_tile.unit = None
        unit.q, unit.r = target_tile.q, target_tile.r
        target_tile.unit = unit
        self.reachable = self._compute_reachable(unit)

    def _compute_reachable(self, unit):
        """Breadth-first search for all tiles reachable within move_range."""
        origin = (unit.q, unit.r)
        max_steps = unit.move_range
        visited = {origin}
        reachable = set()
        frontier = deque()
        frontier.append((origin, 0))
        while frontier:
            (cq, cr), dist = frontier.popleft()
            for nq, nr in axial_neighbors(cq, cr):
                if (nq, nr) in visited:
                    continue
                tile = self.tiles.get((nq, nr))
                if not tile:
                    continue
                if dist + 1 > max_steps:
                    continue
                if not tile.passable_for(unit):
                    continue
                visited.add((nq, nr))
                reachable.add((nq, nr))
                frontier.append(((nq, nr), dist + 1))  # enqueue for further exploration
        return reachable

    def push_tiles(self):
        """Construct HL_TileInstance and debug label arrays for hexlib."""
        instances = []
        labels = []
        tile_index = 0  # keeps iteration count if we need deterministic patterns later
        for (q, r), tile in self.tiles.items():
            terrain_slot = tile.terrain.slot if tile.terrain.loaded else -1
            unit_slot = tile.unit.texture_slot if tile.unit else -1
            terrain_scale = float(tile.terrain.scale if tile.terrain else 1.0)
            unit_scale = float(tile.unit.unit_type.scale if tile.unit else 1.0)
            overlay = self._overlay_for_tile(tile)

            # Optional wobble/padding to help visualise offset behaviour.
            offset_x = 0.0
            offset_y = 0.0
            if tile.terrain.name == "water":
                offset_y = math.sin(self.time_accum + q * 0.35 + r * 0.21) * 1.3
            elif (q + r) % 4 == 0:
                offset_x = 0.0  # tweak this to slide every 4th tile horizontally

            # Fill out the ctypes struct explicitly so every field is obvious.
            inst = HL_TileInstance()
            inst.q = q
            inst.r = r
            inst.terrain_tex = terrain_slot
            inst.unit_tex = unit_slot
            inst.terrain_scale = terrain_scale
            inst.unit_scale = unit_scale
            inst.overlay = overlay
            inst.offset_x = offset_x
            inst.offset_y = offset_y
            instances.append(inst)

            # Emit debug labels for tiles aligned on the 5-grid (helps spot drift).
            if q % 5 == 0 or r % 5 == 0:
                label_text = f"{q},{r}".encode("ascii", "replace")[:15]
                label_struct = HL_DebugLabel()
                label_struct.q = q
                label_struct.r = r
                label_struct.text = (label_text + b"\0" * 16)[:16]
                labels.append(label_struct)
            tile_index += 1
        if not instances:
            lib.hl_clear_tiles()
            lib.hl_set_debug_labels(None, 0)
            return
        arr_type = HL_TileInstance * len(instances)
        lib.hl_set_tiles(arr_type(*instances), len(instances))
        if labels:
            label_arr_type = HL_DebugLabel * len(labels)
            lib.hl_set_debug_labels(label_arr_type(*labels), len(labels))
        else:
            lib.hl_set_debug_labels(None, 0)

    def _overlay_for_tile(self, tile):
        """Compute per-tile overlay colour (selection, reachable, hover)."""
        base = tile.terrain.base_overlay()
        coord = (tile.q, tile.r)
        if self.selected_unit and coord == (self.selected_unit.q, self.selected_unit.r):
            return make_color(255, 234, 150, 135)
        if coord in self.reachable:
            return make_color(120, 215, 255, 105)
        if self.hover_hex and coord == self.hover_hex:
            return make_color(255, 255, 255, 75)
        return base


def random_from_seed(seed):
    """Simple LCG-based RNG so world generation is deterministic."""
    state = seed

    def _rnd():
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return (state % 1000) / 1000.0

    return _rnd


def main():
    """Entry point: initialise hexlib, run the main loop, tear down cleanly."""
    if not lib.hl_init(WINDOW_WIDTH, WINDOW_HEIGHT, b"Hex Strategy Demo"):
        raise RuntimeError("Failed to initialize SDL2/hexlib")

    game = HexStrategyGame()
    game.initialize()

    last_time = time.perf_counter()

    try:
        while game.running:
            # Drain all pending input events before simulating the next frame.
            while True:
                out_q = ctypes.c_int(0)
                out_r = ctypes.c_int(0)
                ev = lib.hl_poll_event(ctypes.byref(out_q), ctypes.byref(out_r))
                if ev == 0:
                    break
                game.handle_event(ev, out_q.value, out_r.value)

            now = time.perf_counter()
            dt = now - last_time
            last_time = now

            game.update(dt)
            game.update_camera(dt)
            game.push_tiles()
            lib.hl_step(ctypes.c_float(dt))
            # Tiny sleep to keep CPU usage sane while still targeting ~60 FPS.
            time.sleep(0.004)
    finally:
        lib.hl_shutdown()


if __name__ == "__main__":
    main()
