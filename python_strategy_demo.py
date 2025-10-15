import ctypes
import os
import sys
import time
from collections import deque


def _load_lib():
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


lib = _load_lib()


class HL_Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_uint8),
                ("g", ctypes.c_uint8),
                ("b", ctypes.c_uint8),
                ("a", ctypes.c_uint8)]


class HL_TileInstance(ctypes.Structure):
    _fields_ = [("q", ctypes.c_int32),
                ("r", ctypes.c_int32),
                ("terrain_tex", ctypes.c_int32),
                ("unit_tex", ctypes.c_int32),
                ("overlay", HL_Color)]


# Configure lib prototypes
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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")


TERRAIN_DEFS = [
    {
        "name": "grass",
        "slot": 0,
        "path": "assets/terrain_grass.png",
        "placeholder": (70, 145, 84),
        "overlay": (64, 140, 82, 40),
        "passable": True,
    },
    {
        "name": "water",
        "slot": 1,
        "path": "assets/terrain_water.png",
        "placeholder": (58, 105, 190),
        "overlay": (70, 110, 200, 70),
        "passable": False,
    },
    {
        "name": "mountain",
        "slot": 2,
        "path": "assets/terrain_mountain.png",
        "placeholder": (145, 141, 132),
        "overlay": (140, 135, 125, 60),
        "passable": False,
    },
]


UNIT_DEFS = [
    {
        "name": "scout",
        "slot": 10,
        "path": "assets/unit_scout.png",
        "placeholder": (220, 220, 80),
        "move_range": 3,
    }
]


HEX_DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def ensure_placeholder_image(path, rgb, size=96):
    if rgb is None:
        return
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_solid_bmp(path, rgb, size=size)


def write_solid_bmp(path, rgb, size=96):
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
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.join(BASE_DIR, rel_path)


def make_color(r, g, b, a=255):
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    a = max(0, min(255, int(a)))
    return HL_Color(r, g, b, a)


def axial_neighbors(q, r):
    for dq, dr in HEX_DIRECTIONS:
        yield q + dq, r + dr


def hex_distance(a, b):
    aq, ar = a
    bq, br = b
    ax, az = aq, ar
    ay = -ax - az
    bx, bz = bq, br
    by = -bx - bz
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


class TerrainType:
    def __init__(self, name, slot, rel_path, placeholder_rgb, overlay_rgba, passable):
        self.name = name
        self.slot = slot
        self.rel_path = rel_path
        self.placeholder_rgb = placeholder_rgb
        self.overlay_rgba = overlay_rgba
        self.passable = passable
        self.loaded = False

    def ensure_texture(self):
        path = resolve_path(self.rel_path)
        ensure_placeholder_image(path, self.placeholder_rgb)
        ok = lib.hl_load_texture(self.slot, path.encode("utf-8"))
        self.loaded = bool(ok)
        if not self.loaded:
            print(f"[terrain] Texture load failed for {self.name}: {path}")
        return self.loaded

    def base_overlay(self):
        return make_color(*self.overlay_rgba)


class UnitType:
    def __init__(self, name, slot, rel_path, placeholder_rgb, move_range):
        self.name = name
        self.slot = slot
        self.rel_path = rel_path
        self.placeholder_rgb = placeholder_rgb
        self.move_range = move_range
        self.loaded = False

    def ensure_texture(self):
        path = resolve_path(self.rel_path)
        ensure_placeholder_image(path, self.placeholder_rgb, size=82)
        ok = lib.hl_load_texture(self.slot, path.encode("utf-8"))
        self.loaded = bool(ok)
        if not self.loaded:
            print(f"[unit] Texture load failed for {self.name}: {path}")
        return self.loaded


class Tile:
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
        self.hex_size = 38.0

    def initialize(self):
        os.makedirs(ASSET_DIR, exist_ok=True)
        self._bootstrap_types()
        self._load_textures()
        self._build_world()
        self._spawn_units()
        grid_extent = self.hex_radius * 2 + 1
        lib.hl_set_grid(grid_extent, grid_extent, ctypes.c_float(self.hex_size), 1)
        lib.hl_set_clear_color(18, 20, 26, 255)

    def _bootstrap_types(self):
        for entry in TERRAIN_DEFS:
            terrain = TerrainType(
                entry["name"],
                entry["slot"],
                entry["path"],
                entry["placeholder"],
                entry["overlay"],
                entry["passable"],
            )
            self.terrain_types[terrain.name] = terrain
        for entry in UNIT_DEFS:
            unit = UnitType(
                entry["name"],
                entry["slot"],
                entry["path"],
                entry["placeholder"],
                entry["move_range"],
            )
            self.unit_types[unit.name] = unit

    def _load_textures(self):
        for terrain in self.terrain_types.values():
            terrain.ensure_texture()
        for unit_type in self.unit_types.values():
            unit_type.ensure_texture()

    def _build_world(self):
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
        scout_type = self.unit_types["scout"]
        unit = Unit(scout_type, 0, 0)
        self.units.append(unit)
        self.tiles[(0, 0)].unit = unit

    def handle_event(self, ev, q, r):
        if ev == 1:
            self.running = False
        elif ev == 2:
            self._handle_left_click(q, r)
        elif ev == 4:
            self._handle_right_click(q, r)
        elif ev == 3:
            self._handle_hover(q, r)

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

    def _move_unit(self, unit, target_tile):
        origin_tile = self.tiles[(unit.q, unit.r)]
        origin_tile.unit = None
        unit.q, unit.r = target_tile.q, target_tile.r
        target_tile.unit = unit
        self.reachable = self._compute_reachable(unit)

    def _compute_reachable(self, unit):
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
                frontier.append(((nq, nr), dist + 1))
        return reachable

    def push_tiles(self):
        instances = []
        for (q, r), tile in self.tiles.items():
            terrain_slot = tile.terrain.slot if tile.terrain.loaded else -1
            unit_slot = tile.unit.texture_slot if tile.unit else -1
            overlay = self._overlay_for_tile(tile)
            instances.append(HL_TileInstance(q, r, terrain_slot, unit_slot, overlay))
        if not instances:
            lib.hl_clear_tiles()
            return
        arr_type = HL_TileInstance * len(instances)
        lib.hl_set_tiles(arr_type(*instances), len(instances))

    def _overlay_for_tile(self, tile):
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
    state = seed

    def _rnd():
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return (state % 1000) / 1000.0

    return _rnd


def main():
    if not lib.hl_init(1280, 800, b"Hex Strategy Demo"):
        raise RuntimeError("Failed to initialize SDL2/hexlib")

    game = HexStrategyGame()
    game.initialize()

    last_time = time.perf_counter()

    try:
        while game.running:
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

            game.push_tiles()
            lib.hl_step(ctypes.c_float(dt))
            time.sleep(0.004)
    finally:
        lib.hl_shutdown()


if __name__ == "__main__":
    main()
