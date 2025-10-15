# SDL2 + Python (ctypes) Hex Grid — Setup & Troubleshooting

Minimal C/SDL2 renderer with Python (ctypes) driving the game logic.
Supports macOS, Windows, and Linux. The C side draws a 2D flat-top hex grid; Python sends batches of hex instances each frame.

---

## Prereqs

- C toolchain (Clang/MSVC/GCC)
- CMake ≥ 3.18 and Ninja (or Make)
- SDL2 (and optionally: `sdl2_image`, `sdl2_mixer`, `sdl2_ttf`, `sdl2_gfx`)
- Python 3.10+ (no third-party libs required; `ctypes` only)

---

## Install

### macOS (Homebrew)

```bash
# 0) Xcode Command Line Tools (CLT)
xcode-select --install

# 1) (Optional) Newer LLVM/Clang than Apple Clang
brew update
brew install llvm
echo 'export PATH="$(brew --prefix llvm)/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc

# 2) Build essentials
brew install cmake ninja pkg-config

# 3) SDL2 + common add-ons
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf sdl2_gfx

# 4) Python (virtualenv recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install pysdl2
```

**Sanity checks**

```bash
cc --version
sdl2-config --version
pkg-config --modversion sdl2
```

### Windows

#### Option A — MSYS2 (mingw-w64)

1. Install MSYS2, open **MSYS2 UCRT64** shell:

```bash
pacman -Syu   # may need to close/reopen once
pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-clang \
  mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-pkg-config git

pacman -S --needed mingw-w64-ucrt-x86_64-SDL2 \
  mingw-w64-ucrt-x86_64-SDL2_image \
  mingw-w64-ucrt-x86_64-SDL2_mixer \
  mingw-w64-ucrt-x86_64-SDL2_ttf \
  mingw-w64-ucrt-x86_64-SDL2_gfx

pacman -S --needed mingw-w64-ucrt-x86_64-python-pip
python -m venv .venv && source .venv/Scripts/activate
pip install --upgrade pip
pip install pysdl2
```

#### Option B — MSVC/Clang + vcpkg

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --silent
winget install Git.Git Kitware.CMake Ninja-build.Ninja LLVM.LLVM

git clone https://github.com/microsoft/vcpkg $env:USERPROFILE\vcpkg
& $env:USERPROFILE\vcpkg\bootstrap-vcpkg.bat

$env:VCPKG_DEFAULT_TRIPLET="x64-windows"
$VCP=$env:USERPROFILE+"\vcpkg"
& $VCP\vcpkg.exe install sdl2 sdl2-image sdl2-mixer sdl2-ttf sdl2-gfx

py -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install pysdl2 pysdl2-dll
```

Build with:

```powershell
cmake -B build -S . -G "Ninja" -DCMAKE_TOOLCHAIN_FILE=$VCP\scripts\buildsystems\vcpkg.cmake -A x64
cmake --build build --config Release
```

### Linux

#### Debian/Ubuntu

```bash
sudo apt update
sudo apt install -y build-essential clang pkg-config cmake ninja-build git \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libsdl2-gfx-dev
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install pysdl2
```

#### Fedora

```bash
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y clang cmake ninja-build pkg-config git \
  SDL2-devel SDL2_image-devel SDL2_mixer-devel SDL2_ttf-devel SDL2_gfx-devel
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install pysdl2
```

#### Arch/Manjaro

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel clang cmake ninja pkgconf git \
  sdl2 sdl2_image sdl2_mixer sdl2_ttf sdl2_gfx
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install pysdl2
```

---

## Build & Run

```bash
# from repo root
mkdir -p build && cd build
cmake -G Ninja ..
ninja

# optional C demo
./hex_demo

# Python-controlled renderer
cd ..
python3 python_demo.py
```

> On macOS, you can be explicit about the SDK if needed:
> `cmake -G Ninja -D CMAKE_OSX_SYSROOT="$(xcrun --show-sdk-path)" ..`

---

## macOS Notes (Xcode/SDK after OS upgrades)

If CMake says the compiler can't build a simple test or you see messages like:

- `xcodebuild: error: SDK ".../MacOSX15.5.sdk" cannot be located.`
- `xcrun: error: unable to find utility "clang"`

You probably have a stale developer path or a phantom `SDKROOT`.

**Fix:**

```bash
# remove bad env in your shell
unset SDKROOT
unset DEVELOPER_DIR

# reset/select the real Xcode
sudo xcode-select --reset
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept

# verify
xcrun --find clang
xcodebuild -showsdks | grep -i macos
ls -1 /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs
```

If `xcrun --find clang` still fails, open Xcode once and set **Preferences → Locations → Command Line Tools** to your installed Xcode 16.x.

---

## macOS: `pkg-config` can't find SDL2

If `pkg-config --modversion sdl2` says "No package 'sdl2' found":

```bash
# confirm where Homebrew installed SDL2's .pc
brew --prefix sdl2
ls -1 "$(brew --prefix sdl2)"/lib/pkgconfig/sdl2.pc

# set PKG_CONFIG_PATH for the session
export PKG_CONFIG_PATH="$(brew --prefix sdl2)/lib/pkgconfig:$(brew --prefix)/lib/pkgconfig:$(brew --prefix)/share/pkgconfig:$PKG_CONFIG_PATH"

# optional: make it permanent
echo 'export PKG_CONFIG_PATH="$(brew --prefix sdl2)/lib/pkgconfig:$(brew --prefix)/lib/pkgconfig:$(brew --prefix)/share/pkgconfig:$PKG_CONFIG_PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## CMake: robust SDL2 detection (macOS & others)

We use pkg-config if available and fall back to SDL2's CMake package:

```cmake
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(SDL2 IMPORTED_TARGET sdl2)
endif()

add_library(hexlib SHARED src/hexlib.c)
target_include_directories(hexlib PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_compile_definitions(hexlib PRIVATE HEXLIB_BUILD)

if(TARGET PkgConfig::SDL2)
  target_link_libraries(hexlib PRIVATE PkgConfig::SDL2)
else()
  find_package(SDL2 CONFIG REQUIRED)      # Homebrew: /opt/homebrew/lib/cmake/SDL2
  target_link_libraries(hexlib PRIVATE SDL2::SDL2)
endif()

add_executable(hex_demo src/main.c)
target_include_directories(hex_demo PRIVATE ${PROJECT_SOURCE_DIR}/include)
if(TARGET PkgConfig::SDL2)
  target_link_libraries(hex_demo PRIVATE hexlib PkgConfig::SDL2)
else()
  target_link_libraries(hex_demo PRIVATE hexlib SDL2::SDL2)
endif()
```

If you still see **link-time** `ld: library 'SDL2' not found`, you're passing `-lSDL2` without the `-L` path. Using `PkgConfig::SDL2` or `SDL2::SDL2` fixes that (they carry the proper include, lib, and framework flags).

---

## Common Errors (and quick fixes)

| Symptom                                  | Cause                                         | Fix                                                                                            |
| ---------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `SDK "...MacOSX*.sdk" cannot be located` | Stale `SDKROOT`/CLT after macOS upgrade       | `unset SDKROOT && xcode-select --reset && --switch /Applications/Xcode.app/Contents/Developer` |
| `xcrun: unable to find utility "clang"`  | CLT/Xcode not selected                        | Open Xcode → set **Command Line Tools**, or run the `xcode-select` steps above                 |
| `pkg-config: No package 'sdl2' found`    | `PKG_CONFIG_PATH` missing Homebrew dirs       | Export `PKG_CONFIG_PATH` to include `$(brew --prefix sdl2)/lib/pkgconfig`                      |
| `ld: library 'SDL2' not found`           | Linking with `-lSDL2` but missing `-L`        | Use `PkgConfig::SDL2` or `SDL2::SDL2` in CMake                                                 |
| Blue screen, only outlines drawn         | Using older SDL2 without `SDL_RenderGeometry` | Either update SDL2 or keep outline rendering / link `sdl2_gfx`                                 |

---

## Run the Demos

```bash
# C demo
./build/hex_demo

# Python
python3 python_demo.py
```

You should see a dark background with a hex grid; clicks create a small ring animation and the background pulses over time.

---

## Project Structure

```
include/hexlib.h      # public C API (shared with Python ctypes)
src/hexlib.c          # SDL2 renderer + hex math
src/main.c            # optional standalone C demo
python_demo.py        # Python controller using ctypes
CMakeLists.txt
```

---

## License

MIT (see `LICENSE`).
