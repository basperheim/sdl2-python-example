#ifndef HEXLIB_H
#define HEXLIB_H

// Cross-platform export macro
#if defined(_WIN32) || defined(_WIN64)
  #ifdef HEXLIB_BUILD
    #define HEXLIB_API __declspec(dllexport)
  #else
    #define HEXLIB_API __declspec(dllimport)
  #endif
#else
  #define HEXLIB_API __attribute__((visibility("default")))
#endif

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t r, g, b, a;
} HL_Color;

// One hex instance at axial coord (q, r) with fill color
typedef struct {
    int32_t q;
    int32_t r;
    HL_Color color;
} HL_HexInstance;

// Initialization / teardown
HEXLIB_API int  hl_init(int width, int height, const char* title);
HEXLIB_API void hl_shutdown(void);

// Grid setup (flat_top: 1 = flat-top, 0 = pointy-top; here we’ll use 1)
HEXLIB_API void hl_set_grid(int rows, int cols, float hex_size, int flat_top);

// Replace the set of instances to render this frame (copied internally)
HEXLIB_API void hl_set_instances(const HL_HexInstance* instances, int count);

// Advance a frame: clears, draws, presents. dt_seconds can be 0 if unused.
HEXLIB_API void hl_step(float dt_seconds);

// Poll input: returns an event code and (if mouse) the hex under cursor.
// returns: 0=none, 1=quit, 2=mouse_down, 3=mouse_move
HEXLIB_API int  hl_poll_event(int* out_q, int* out_r);

// Helpers available to embedder (optional)
HEXLIB_API void hl_set_clear_color(uint8_t r, uint8_t g, uint8_t b, uint8_t a);

#ifdef __cplusplus
}
#endif
#endif // HEXLIB_H
