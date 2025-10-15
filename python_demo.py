import ctypes
import os
import sys
import time
import math
import random

# Load shared library (adjust name per OS)
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
    # Fallback to system path
    return ctypes.CDLL("hexlib" + (".dll" if os.name == "nt" else (".dylib" if sys.platform=="darwin" else ".so")))

lib = _load_lib()

# --- ctypes mirror of C structs
class HL_Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_uint8),
                ("g", ctypes.c_uint8),
                ("b", ctypes.c_uint8),
                ("a", ctypes.c_uint8)]

class HL_HexInstance(ctypes.Structure):
    _fields_ = [("q", ctypes.c_int32),
                ("r", ctypes.c_int32),
                ("color", HL_Color)]

# arg/restype
lib.hl_init.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
lib.hl_init.restype  = ctypes.c_int
lib.hl_shutdown.argtypes = []
lib.hl_set_grid.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_int]
lib.hl_set_instances.argtypes = [ctypes.POINTER(HL_HexInstance), ctypes.c_int]
lib.hl_step.argtypes = [ctypes.c_float]
lib.hl_poll_event.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
lib.hl_poll_event.restype = ctypes.c_int
lib.hl_set_clear_color.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8]

def init():
    ok = lib.hl_init(1280, 800, b"HexLib (Python-controlled)")
    if not ok:
        raise RuntimeError("Failed to initialize hexlib/SDL2")
    lib.hl_set_grid(22, 32, ctypes.c_float(22.0), 1)
    lib.hl_set_clear_color(14, 14, 18, 255)

def make_ring(cx_q, cx_r, radius, color):
    out = []
    if radius == 0:
        out.append(HL_HexInstance(cx_q, cx_r, color))
        return out
    # Cube directions for ring walk (flat-top axial basis)
    dirs = [(1,0), (1,-1), (0,-1), (-1,0), (-1,1), (0,1)]
    # Start at (cx + dir5*radius)
    q = cx_q + dirs[4][0]*radius
    r = cx_r + dirs[4][1]*radius
    for d in range(6):
        dq, dr = dirs[d]
        for _ in range(radius):
            out.append(HL_HexInstance(q, r, color))
            q += dq
            r += dr
    return out

def main():
    init()
    t0 = time.perf_counter()
    running = True

    # initial batch: a gradient blob
    batch = []
    for q in range(0, 26):
        for r in range(-8, 14):
            g = 80 + ((q*7) % 120)
            b = 100 + ((r*11) % 120)
            batch.append(HL_HexInstance(q, r, HL_Color(40, g & 0xFF, b & 0xFF, 255)))
    arr_type = HL_HexInstance * len(batch)
    lib.hl_set_instances(arr_type(*batch), len(batch))

    while running:
        # Handle events
        out_q = ctypes.c_int(0)
        out_r = ctypes.c_int(0)
        ev = lib.hl_poll_event(ctypes.byref(out_q), ctypes.byref(out_r))
        if ev == 1:  # quit
            running = False
        elif ev == 2:  # click: animate expanding ring from clicked hex
            ring_color = HL_Color(255, 255, 255, 255)
            ring = make_ring(out_q.value, out_r.value, radius=2, color=ring_color)
            arr_t = HL_HexInstance * len(ring)
            lib.hl_set_instances(arr_t(*ring), len(ring))

        # simple time-based color pulse
        t = time.perf_counter() - t0
        pulse = int((math.sin(t*2.0) * 0.5 + 0.5) * 155) + 100
        lib.hl_set_clear_color(14, 14, pulse & 0xFF, 255)

        lib.hl_step(ctypes.c_float(0.016))
        time.sleep(0.001)

    lib.hl_shutdown()

if __name__ == "__main__":
    main()
