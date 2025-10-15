#include "../include/hexlib.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static void fill_demo_instances(int rows, int cols) {
    int count = rows * cols;
    HL_HexInstance* arr = (HL_HexInstance*)malloc(sizeof(HL_HexInstance) * count);
    int i = 0;
    for (int r = 0; r < rows; ++r) {
        for (int q = 0; q < cols; ++q) {
            // Offset axial grid: convert grid indices to axial coords (q, r)
            HL_HexInstance hi;
            hi.q = q;
            hi.r = r - q/2; // simple “odd-q” offset -> axial-ish
            hi.color.r = 40 + (uint8_t)(rand()%128);
            hi.color.g = 80 + (uint8_t)(rand()%128);
            hi.color.b = 120 + (uint8_t)(rand()%128);
            hi.color.a = 255;
            arr[i++] = hi;
        }
    }
    hl_set_instances(arr, count);
    free(arr);
}

int main(void) {
    srand((unsigned)time(NULL));
    if (!hl_init(1280, 800, "HexLib (Standalone Demo)")) return 1;
    hl_set_grid(20, 28, 22.0f, 1);
    hl_set_clear_color(14, 14, 18, 255);
    fill_demo_instances(20, 28);

    int running = 1;
    while (running) {
        int q=0, r=0;
        int ev = hl_poll_event(&q, &r);
        if (ev == 1) running = 0; // QUIT
        else if (ev == 2) { // click = pulse the clicked hex to white
            HL_HexInstance one = { q, r, {255,255,255,255} };
            hl_set_instances(&one, 1);
        }
        hl_step(0.0f);
    }

    hl_shutdown();
    return 0;
}
