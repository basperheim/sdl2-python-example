#define SDL_DISABLE_IMMINTRIN_H 1
#include <SDL.h>
#include <SDL_image.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../include/hexlib.h"

typedef struct {
    int rows, cols;
    float size;          // hex radius (flat-top: horizontal radius)
    int flat_top;        // 1 flat-top, 0 pointy
    float origin_x;      // top-left origin for grid
    float origin_y;
} HL_Grid;

static SDL_Window*     g_window = NULL;
static SDL_Renderer*   g_renderer = NULL;
static HL_Grid         g_grid = {0};
static HL_HexInstance* g_instances = NULL;
static int             g_instance_count = 0;
static SDL_Color       g_clear = { 12, 12, 16, 255 }; // default dark

typedef struct {
    SDL_Texture* texture;
    int w;
    int h;
} HL_TextureSlot;

static HL_TextureSlot  g_textures[HL_MAX_TEXTURE_SLOTS] = {0};
static HL_TileInstance* g_tiles = NULL;
static int             g_tile_count = 0;
static float           g_camera_offset_x = 0.0f;
static float           g_camera_offset_y = 0.0f;
static float           g_camera_zoom = 1.0f;
static HL_DebugLabel*  g_labels = NULL;
static int             g_label_count = 0;

// --- Math for axial coords (flat-top) ---
// Reference: https://www.redblobgames.com/grids/hex-grids/
static void axial_to_pixel_flat(int q, int r, float size, float* outx, float* outy) {
    // flat-top axial to pixel
    float x = size * (3.0f/2.0f * q);
    float y = size * (sqrtf(3.0f)/2.0f * q + sqrtf(3.0f) * r);
    *outx = x + g_grid.origin_x;
    *outy = y + g_grid.origin_y;
}

// Inverse (pixel to axial, flat-top), rounded to nearest hex
static void cube_round(float x, float y, float z, int* rq, int* rr) {
    int rx = (int)lroundf(x);
    int ry = (int)lroundf(y);
    int rz = (int)lroundf(z);

    float x_diff = fabsf(rx - x);
    float y_diff = fabsf(ry - y);
    float z_diff = fabsf(rz - z);

    if (x_diff > y_diff && x_diff > z_diff) {
        rx = -ry - rz;
    } else if (y_diff > z_diff) {
        ry = -rx - rz;
    } else {
        rz = -rx - ry;
    }
    // Convert cube (x,y,z) -> axial (q,r)
    *rq = rx;
    *rr = rz;
}

static void pixel_to_axial_flat(float px, float py, float size, int* outq, int* outr) {
    float x = px - g_grid.origin_x;
    float y = py - g_grid.origin_y;
    // Inverse of axial_to_pixel (flat-top)
    float qf = (2.0f/3.0f) * x / size;
    float rf = (-1.0f/3.0f) * x / size + (1.0f/sqrtf(3.0f)) * y / size;

    // Convert axial (qf, rf) to cube
    float xf = qf;
    float zf = rf;
    float yf = -xf - zf;
    int rq, rr;
    cube_round(xf, yf, zf, &rq, &rr);
    *outq = rq;
    *outr = rr;
}

static void hex_corners_flat(float cx, float cy, float size, SDL_FPoint out[6]) {
    // flat-top: angles start at 0°, step 60°
    for (int i = 0; i < 6; ++i) {
        float angle = (float)M_PI / 180.0f * (60.0f * i);
        out[i].x = cx + size * cosf(angle);
        out[i].y = cy + size * sinf(angle);
    }
}

static void screen_to_world(float* px, float* py) {
    int w = 0, h = 0;
    SDL_GetWindowSize(g_window, &w, &h);
    float zoom = g_camera_zoom;
    if (zoom < 0.05f) zoom = 0.05f;
    float x = *px;
    float y = *py;
    x = (x - w * 0.5f) / zoom + w * 0.5f;
    y = (y - h * 0.5f) / zoom + h * 0.5f;
    x -= g_camera_offset_x;
    y -= g_camera_offset_y;
    *px = x;
    *py = y;
}

static void world_to_screen(float* px, float* py, int win_w, int win_h) {
    float zoom = g_camera_zoom;
    if (zoom < 0.05f) zoom = 0.05f;
    float x = *px + g_camera_offset_x;
    float y = *py + g_camera_offset_y;
    x = (x - win_w * 0.5f) * zoom + win_w * 0.5f;
    y = (y - win_h * 0.5f) * zoom + win_h * 0.5f;
    *px = x;
    *py = y;
}

typedef struct {
    uint8_t rows[5];
} Glyph3x5;

static const Glyph3x5 glyph_digits[10] = {
    {{0b111,0b101,0b101,0b101,0b111}}, // 0
    {{0b010,0b110,0b010,0b010,0b111}}, // 1
    {{0b111,0b001,0b111,0b100,0b111}}, // 2
    {{0b111,0b001,0b111,0b001,0b111}}, // 3
    {{0b101,0b101,0b111,0b001,0b001}}, // 4
    {{0b111,0b100,0b111,0b001,0b111}}, // 5
    {{0b111,0b100,0b111,0b101,0b111}}, // 6
    {{0b111,0b001,0b010,0b010,0b010}}, // 7
    {{0b111,0b101,0b111,0b101,0b111}}, // 8
    {{0b111,0b101,0b111,0b001,0b111}}, // 9
};
static const Glyph3x5 glyph_minus = { {0b000,0b000,0b111,0b000,0b000} };
static const Glyph3x5 glyph_comma = { {0b000,0b000,0b000,0b010,0b100} };

static const Glyph3x5* glyph_for_char(char c) {
    if (c >= '0' && c <= '9') return &glyph_digits[c - '0'];
    if (c == '-') return &glyph_minus;
    if (c == ',') return &glyph_comma;
    return NULL;
}

static void draw_glyph(SDL_Renderer* renderer, float x, float y, float scale, const Glyph3x5* glyph) {
    if (!glyph) return;
    for (int row = 0; row < 5; ++row) {
        uint8_t bits = glyph->rows[row];
        for (int col = 0; col < 3; ++col) {
            if (bits & (1 << (2 - col))) {
                SDL_FRect rect = { x + col * scale, y + row * scale, scale, scale };
                SDL_RenderFillRectF(renderer, &rect);
            }
        }
    }
}

static void draw_label(SDL_Renderer* renderer, float cx, float cy, const char* text, float base_scale) {
    if (!text || !*text) return;
    size_t len = strlen(text);
    if (len == 0) return;
    float char_w = 3.0f * base_scale;
    float spacing = base_scale;
    float text_w = len * char_w + (len - 1) * spacing;
    float text_h = 5.0f * base_scale;
    float x = cx - text_w * 0.5f;
    float y = cy - text_h * 0.5f;
    SDL_SetRenderDrawColor(renderer, 245, 245, 245, 255);
    for (size_t i = 0; i < len; ++i) {
        const Glyph3x5* glyph = glyph_for_char(text[i]);
        if (glyph) {
            draw_glyph(renderer, x, y, base_scale, glyph);
            x += char_w + spacing;
        } else {
            x += char_w + spacing;
        }
    }
}
HEXLIB_API int hl_init(int width, int height, const char* title) {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS) != 0) {
        SDL_Log("SDL_Init failed: %s", SDL_GetError());
        return 0;
    }
    // SDL_HINT_RENDER_DRIVER can be set if you prefer "opengl", "metal", etc.
    g_window = SDL_CreateWindow(
        title ? title : "HexLib",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        width, height,
        SDL_WINDOW_SHOWN
    );
    if (!g_window) {
        SDL_Log("CreateWindow failed: %s", SDL_GetError());
        SDL_Quit();
        return 0;
    }

    // SDL_Renderer with geometry support (SDL 2.0.18+)
    g_renderer = SDL_CreateRenderer(g_window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!g_renderer) {
        SDL_Log("CreateRenderer failed: %s", SDL_GetError());
        SDL_DestroyWindow(g_window);
        SDL_Quit();
        return 0;
    }
    SDL_SetRenderDrawBlendMode(g_renderer, SDL_BLENDMODE_BLEND);

    int img_flags = IMG_INIT_PNG | IMG_INIT_JPG;
    int img_init = IMG_Init(img_flags);
    if ((img_init & img_flags) != img_flags) {
        SDL_Log("IMG_Init warning: %s", IMG_GetError());
    }
    return 1;
}

HEXLIB_API void hl_shutdown(void) {
    hl_clear_tiles();
    hl_clear_textures();
    if (g_instances) { free(g_instances); g_instances = NULL; g_instance_count = 0; }
    if (g_labels) { free(g_labels); g_labels = NULL; g_label_count = 0; }
    if (g_renderer) { SDL_DestroyRenderer(g_renderer); g_renderer = NULL; }
    if (g_window)   { SDL_DestroyWindow(g_window); g_window = NULL; }
    IMG_Quit();
    SDL_Quit();
}

HEXLIB_API void hl_set_grid(int rows, int cols, float hex_size, int flat_top) {
    g_grid.rows = rows;
    g_grid.cols = cols;
    g_grid.size = hex_size;
    g_grid.flat_top = flat_top ? 1 : 0;

    // Center grid roughly in window
    int w=0,h=0;
    SDL_GetWindowSize(g_window, &w, &h);
    float grid_w = (3.0f/2.0f * (cols-1) * hex_size) + 2.0f*hex_size;
    float grid_h = (sqrtf(3.0f) * hex_size * (rows + 0.5f)) + hex_size;
    float origin_x = (w - grid_w) * 0.5f + hex_size;
    float origin_y = (h - grid_h) * 0.5f + hex_size;
    if (grid_w > w) origin_x = w * 0.5f;
    if (grid_h > h) origin_y = h * 0.5f;
    g_grid.origin_x = origin_x;
    g_grid.origin_y = origin_y;
}

HEXLIB_API void hl_set_camera(float offset_x, float offset_y, float zoom) {
    g_camera_offset_x = offset_x;
    g_camera_offset_y = offset_y;
    if (zoom < 0.05f) zoom = 0.05f;
    g_camera_zoom = zoom;
}

HEXLIB_API void hl_set_instances(const HL_HexInstance* instances, int count) {
    if (g_tiles) { free(g_tiles); g_tiles = NULL; g_tile_count = 0; }
    if (g_labels) { free(g_labels); g_labels = NULL; g_label_count = 0; }
    if (g_instances) { free(g_instances); g_instances = NULL; g_instance_count = 0; }
    if (count <= 0 || !instances) return;
    g_instances = (HL_HexInstance*)malloc(sizeof(HL_HexInstance) * count);
    if (!g_instances) return;
    memcpy(g_instances, instances, sizeof(HL_HexInstance) * count);
    g_instance_count = count;
}

static void destroy_texture_slot(int slot) {
    if (slot < 0 || slot >= HL_MAX_TEXTURE_SLOTS) return;
    if (g_textures[slot].texture) {
        SDL_DestroyTexture(g_textures[slot].texture);
        g_textures[slot].texture = NULL;
    }
    g_textures[slot].w = 0;
    g_textures[slot].h = 0;
}

HEXLIB_API int hl_load_texture(int slot, const char* path) {
    if (!g_renderer || !path) return 0;
    if (slot < 0 || slot >= HL_MAX_TEXTURE_SLOTS) return 0;

    destroy_texture_slot(slot);

    SDL_Surface* surf = IMG_Load(path);
    if (!surf) {
        SDL_Log("IMG_Load failed for '%s': %s", path, IMG_GetError());
        surf = SDL_LoadBMP(path);
        if (!surf) {
            SDL_Log("SDL_LoadBMP fallback failed for '%s': %s", path, SDL_GetError());
            return 0;
        }
    }

    SDL_Texture* tex = SDL_CreateTextureFromSurface(g_renderer, surf);
    if (!tex) {
        SDL_Log("SDL_CreateTextureFromSurface failed for '%s': %s", path, SDL_GetError());
        SDL_FreeSurface(surf);
        return 0;
    }

    SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_BLEND);
    g_textures[slot].texture = tex;
    g_textures[slot].w = surf->w;
    g_textures[slot].h = surf->h;
    SDL_FreeSurface(surf);
    return 1;
}

HEXLIB_API void hl_unload_texture(int slot) {
    destroy_texture_slot(slot);
}

HEXLIB_API void hl_clear_textures(void) {
    for (int i = 0; i < HL_MAX_TEXTURE_SLOTS; ++i) {
        destroy_texture_slot(i);
    }
}

HEXLIB_API void hl_set_tiles(const HL_TileInstance* tiles, int count) {
    if (g_instances) { free(g_instances); g_instances = NULL; g_instance_count = 0; }
    if (g_tiles) { free(g_tiles); g_tiles = NULL; g_tile_count = 0; }
    if (count <= 0 || !tiles) return;
    g_tiles = (HL_TileInstance*)malloc(sizeof(HL_TileInstance) * count);
    if (!g_tiles) return;
    memcpy(g_tiles, tiles, sizeof(HL_TileInstance) * count);
    g_tile_count = count;
}

HEXLIB_API void hl_clear_tiles(void) {
    if (g_tiles) { free(g_tiles); g_tiles = NULL; }
    g_tile_count = 0;
    if (g_labels) { free(g_labels); g_labels = NULL; g_label_count = 0; }
}

HEXLIB_API void hl_set_debug_labels(const HL_DebugLabel* labels, int count) {
    if (g_labels) { free(g_labels); g_labels = NULL; g_label_count = 0; }
    if (!labels || count <= 0) return;
    g_labels = (HL_DebugLabel*)malloc(sizeof(HL_DebugLabel) * count);
    if (!g_labels) return;
    memcpy(g_labels, labels, sizeof(HL_DebugLabel) * count);
    g_label_count = count;
}

HEXLIB_API int hl_query_texture(int slot, int* out_w, int* out_h) {
    if (slot < 0 || slot >= HL_MAX_TEXTURE_SLOTS) return 0;
    if (!g_textures[slot].texture) return 0;
    if (out_w) *out_w = g_textures[slot].w;
    if (out_h) *out_h = g_textures[slot].h;
    return 1;
}

HEXLIB_API void hl_set_clear_color(uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
    g_clear.r = r; g_clear.g = g; g_clear.b = b; g_clear.a = a;
}

static void draw_hex_filled(float cx, float cy, float size, SDL_Color c) {
#if SDL_VERSION_ATLEAST(2,0,18)
    SDL_FPoint p[6];
    hex_corners_flat(cx, cy, size, p);

    // Tri fan: (p0, p1, p2), (p0, p2, p3), ... (p0, p5, p0) (implicitly)
    const int tri_count = 4; // Actually 4? For hex it should be 4? It's 4 for quad—correct it:
    // For hex: triangles = 4? No, it's (n - 2) = 4. Yes, 6 corners => 4 triangles using fan.
    SDL_Vertex verts[12]; // 4 tris * 3 verts

    int vi = 0;
    for (int t = 0; t < 4; ++t) {
        SDL_FPoint a = p[0];
        SDL_FPoint b = p[t+1];
        SDL_FPoint d = p[t+2];
        SDL_Vertex v0 = { {a.x, a.y}, { c.r/255.0f, c.g/255.0f, c.b/255.0f, c.a/255.0f }, {0,0} };
        SDL_Vertex v1 = { {b.x, b.y}, { c.r/255.0f, c.g/255.0f, c.b/255.0f, c.a/255.0f }, {0,0} };
        SDL_Vertex v2 = { {d.x, d.y}, { c.r/255.0f, c.g/255.0f, c.b/255.0f, c.a/255.0f }, {0,0} };
        verts[vi++] = v0; verts[vi++] = v1; verts[vi++] = v2;
    }
    SDL_RenderGeometry(g_renderer, NULL, verts, vi, NULL, 0);

    // Outline
    SDL_SetRenderDrawColor(g_renderer, 0, 0, 0, 200);
    for (int i = 0; i < 6; ++i) {
        SDL_RenderDrawLineF(g_renderer, p[i].x, p[i].y, p[(i+1)%6].x, p[(i+1)%6].y);
    }
#else
    // Fallback: just outline (older SDL2)
    SDL_FPoint p[6];
    hex_corners_flat(cx, cy, size, p);
    SDL_SetRenderDrawColor(g_renderer, c.r, c.g, c.b, c.a);
    for (int i = 0; i < 6; ++i) {
        SDL_RenderDrawLineF(g_renderer, p[i].x, p[i].y, p[(i+1)%6].x, p[(i+1)%6].y);
    }
#endif
}

static void texture_dest_rect(const HL_TextureSlot* slot, float target_w, float target_h, float cx, float cy, float scale_mul, SDL_FRect* out_rect) {
    float w = target_w;
    float h = target_h;
    if (scale_mul <= 0.01f) scale_mul = 0.01f;
    if (slot && slot->texture && slot->w > 0 && slot->h > 0) {
        float scale = (target_w / (float)slot->w);
        w = target_w * scale_mul;
        h = (float)slot->h * scale * scale_mul;
        if (h < target_h * 0.92f) {
            float adjust = (target_h * 1.02f) / fmaxf(h, 1e-3f);
            w *= adjust;
            h *= adjust;
        }
    } else {
        w = target_w * scale_mul;
        h = target_h * scale_mul;
    }
    out_rect->w = w;
    out_rect->h = h;
    out_rect->x = cx - w * 0.5f;
    out_rect->y = cy - h * 0.5f;
}

HEXLIB_API void hl_step(float dt_seconds) {
    (void)dt_seconds;

    SDL_SetRenderDrawColor(g_renderer, g_clear.r, g_clear.g, g_clear.b, g_clear.a);
    SDL_RenderClear(g_renderer);

    int win_w = 0, win_h = 0;
    SDL_GetWindowSize(g_window, &win_w, &win_h);
    float zoom = g_camera_zoom < 0.05f ? 0.05f : g_camera_zoom;
    float base_hex_width = g_grid.size * 2.0f;
    float base_hex_height = sqrtf(3.0f) * g_grid.size;
    float scaled_hex_width = base_hex_width * zoom;
    float scaled_hex_height = base_hex_height * zoom;
    float scaled_hex_size = g_grid.size * zoom;

    if (g_tile_count > 0) {
        for (int i = 0; i < g_tile_count; ++i) {
            const HL_TileInstance* tile = &g_tiles[i];
            float cx, cy;
            axial_to_pixel_flat(tile->q, tile->r, g_grid.size, &cx, &cy);
            cx += tile->offset_x;
            cy += tile->offset_y;
            world_to_screen(&cx, &cy, win_w, win_h);

            const HL_TextureSlot* terrain_slot = NULL;
            if (tile->terrain_tex >= 0 && tile->terrain_tex < HL_MAX_TEXTURE_SLOTS) {
                terrain_slot = &g_textures[tile->terrain_tex];
            }
            if (terrain_slot && terrain_slot->texture) {
                SDL_FRect dest;
                float terrain_scale = tile->terrain_scale > 0.0f ? tile->terrain_scale : 1.0f;
                texture_dest_rect(terrain_slot, scaled_hex_width, scaled_hex_height, cx, cy, terrain_scale, &dest);
                SDL_RenderCopyF(g_renderer, terrain_slot->texture, NULL, &dest);
            } else {
                SDL_Color fallback = { 70, 90, 110, 255 };
                draw_hex_filled(cx, cy, scaled_hex_size, fallback);
            }

            if (tile->overlay.a > 0) {
                SDL_Color overlay = { tile->overlay.r, tile->overlay.g, tile->overlay.b, tile->overlay.a };
                draw_hex_filled(cx, cy, scaled_hex_size, overlay);
            }

            const HL_TextureSlot* unit_slot = NULL;
            if (tile->unit_tex >= 0 && tile->unit_tex < HL_MAX_TEXTURE_SLOTS) {
                unit_slot = &g_textures[tile->unit_tex];
            }
            if (unit_slot && unit_slot->texture) {
                float unit_scale = tile->unit_scale > 0.0f ? tile->unit_scale : 0.7f;
                SDL_FRect dest;
                texture_dest_rect(unit_slot, scaled_hex_width, scaled_hex_height, cx, cy, unit_scale, &dest);
                SDL_RenderCopyF(g_renderer, unit_slot->texture, NULL, &dest);
            }
        }
    } else {
        // Draw color-only instances (legacy path)
        for (int i = 0; i < g_instance_count; ++i) {
            float cx, cy;
            axial_to_pixel_flat(g_instances[i].q, g_instances[i].r, g_grid.size, &cx, &cy);
            world_to_screen(&cx, &cy, win_w, win_h);
            SDL_Color c = { g_instances[i].color.r, g_instances[i].color.g, g_instances[i].color.b, g_instances[i].color.a };
            draw_hex_filled(cx, cy, scaled_hex_size, c);
        }
    }

    if (g_label_count > 0) {
        float label_scale = fmaxf(3.0f, 4.5f * zoom);
        for (int i = 0; i < g_label_count; ++i) {
            float cx, cy;
            axial_to_pixel_flat(g_labels[i].q, g_labels[i].r, g_grid.size, &cx, &cy);
            world_to_screen(&cx, &cy, win_w, win_h);
            draw_label(g_renderer, cx, cy, g_labels[i].text, label_scale);
        }
    }

    SDL_RenderPresent(g_renderer);
}

HEXLIB_API int hl_poll_event(int* out_q, int* out_r) {
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
        switch (e.type) {
            case SDL_QUIT: return 1;
            case SDL_MOUSEBUTTONDOWN: {
                int mx = e.button.x, my = e.button.y;
                float fx = (float)mx;
                float fy = (float)my;
                screen_to_world(&fx, &fy);
                int q=0, r=0;
                pixel_to_axial_flat(fx, fy, g_grid.size, &q, &r);
                if (out_q) *out_q = q;
                if (out_r) *out_r = r;
                if (e.button.button == SDL_BUTTON_RIGHT) {
                    return 4;
                }
                if (e.button.button == SDL_BUTTON_LEFT) {
                    return 2;
                }
                break;
            }
            case SDL_MOUSEMOTION: {
                int mx = e.motion.x, my = e.motion.y;
                float fx = (float)mx;
                float fy = (float)my;
                screen_to_world(&fx, &fy);
                int q=0, r=0;
                pixel_to_axial_flat(fx, fy, g_grid.size, &q, &r);
                if (out_q) *out_q = q;
                if (out_r) *out_r = r;
                return 3;
            }
            case SDL_KEYDOWN: {
                if (e.key.repeat) break;
                if (out_q) *out_q = (int)e.key.keysym.sym;
                if (out_r) *out_r = 0;
                return 5;
            }
            case SDL_KEYUP: {
                if (out_q) *out_q = (int)e.key.keysym.sym;
                if (out_r) *out_r = 0;
                return 6;
            }
            default: break;
        }
    }
    return 0;
}
