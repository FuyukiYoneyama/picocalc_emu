/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * The display as an array.
 *
 * On the device this file's counterpart drives a panel over SPI or PIO
 * and reads pixels back out of the controller's GRAM. Here a write lands
 * in memory and `verify_pixels` reads the same memory, so the check can
 * only ever confirm what the application drew. That is the honest limit
 * of a host backend: it answers "did the app compute the right picture",
 * never "did the picture reach the panel". The second question belongs
 * to the firmware backend, which models the wire.
 *
 * The window/write_pixels pair keeps the device's semantics exactly,
 * including the write pointer wrapping within the window, because
 * applications rely on that shape.
 */

#include "picocalc/display.h"

#include <string.h>

#include "picocalc/host.h"

namespace picocalc::display::detail {
// Named rather than anonymous so the host-side accessors below, and the
// digest/PPM code in framebuffer_out.cpp, can reach the same array.
uint16_t g_framebuffer[width * height];
}  // namespace picocalc::display::detail

namespace picocalc::display {
namespace {

using detail::g_framebuffer;

// The active window, as CASET/RASET would set it on the controller.
int g_win_x = 0;
int g_win_y = 0;
int g_win_w = width;
int g_win_h = height;
// Where the next pixel goes, relative to the window origin.
int g_cursor = 0;

bool inside(int x, int y) {
    return x >= 0 && y >= 0 && x < width && y < height;
}

}  // namespace

void init() {
    memset(g_framebuffer, 0, sizeof(g_framebuffer));
    set_window(0, 0, width, height);
}

void clear(uint16_t rgb565) {
    for (int i = 0; i < width * height; ++i) {
        g_framebuffer[i] = rgb565;
    }
}

void set_window(int x, int y, int w, int h) {
    g_win_x = x;
    g_win_y = y;
    g_win_w = w;
    g_win_h = h;
    g_cursor = 0;
}

void write_pixels(const uint16_t* pixels, size_t count) {
    if (pixels == nullptr || g_win_w <= 0 || g_win_h <= 0) {
        return;
    }
    for (size_t i = 0; i < count; ++i) {
        const int x = g_win_x + (g_cursor % g_win_w);
        const int y = g_win_y + (g_cursor / g_win_w);
        if (inside(x, y)) {
            g_framebuffer[y * width + x] = pixels[i];
        }
        // The controller wraps back to the window origin when the write
        // pointer runs past the end, rather than spilling into the rows
        // below. Off-viewport pixels are dropped, not clamped: clamping
        // would paint a stripe down the edge that hardware never shows.
        ++g_cursor;
        if (g_cursor >= g_win_w * g_win_h) {
            g_cursor = 0;
        }
    }
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    for (int row = y; row < y + h; ++row) {
        for (int col = x; col < x + w; ++col) {
            if (inside(col, row)) {
                g_framebuffer[row * width + col] = rgb565;
            }
        }
    }
}

void draw_test_pattern() {
    // Same four quadrants plus a white border the device draws, so a
    // host run and a firmware run of the same app are comparable by
    // digest.
    static constexpr uint16_t kQuadrant[4] = {0xF800, 0x07E0, 0x001F, 0xFFE0};
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const int q = (y < height / 2 ? 0 : 2) + (x < width / 2 ? 0 : 1);
            g_framebuffer[y * width + x] = kQuadrant[q];
        }
    }
    fill_rect(0, 0, width, 2, 0xFFFF);
    fill_rect(0, height - 2, width, 2, 0xFFFF);
    fill_rect(0, 0, 2, height, 0xFFFF);
    fill_rect(width - 2, 0, 2, height, 0xFFFF);
}

PixelVerifyResult verify_pixels(int x, int y, int w, int h,
                                const uint16_t* expected, size_t count) {
    PixelVerifyResult result{};
    // There is no transport to fail. Reporting it as ok would be a lie
    // of a useful kind only if a test could tell the difference -- it
    // cannot, so the field says what is true here: nothing went wrong
    // between the application and the array, because there is nothing
    // in between.
    result.transport_ok = true;
    if (expected == nullptr) {
        return result;
    }
    size_t index = 0;
    for (int row = y; row < y + h && index < count; ++row) {
        for (int col = x; col < x + w && index < count; ++col, ++index) {
            const uint16_t got = inside(col, row) ? g_framebuffer[row * width + col] : 0;
            ++result.pixels;
            if (got != expected[index]) {
                ++result.mismatches;
            }
        }
    }
    return result;
}

}  // namespace picocalc::display

namespace picocalc::host {

const uint16_t* framebuffer() {
    return picocalc::display::detail::g_framebuffer;
}

uint16_t pixel(int x, int y) {
    if (x < 0 || y < 0 || x >= picocalc::display::width ||
        y >= picocalc::display::height) {
        return 0;
    }
    return picocalc::display::detail::g_framebuffer[y * picocalc::display::width + x];
}

size_t non_black_pixels() {
    return non_black_pixels_in(0, 0, picocalc::display::width,
                               picocalc::display::height);
}

size_t non_black_pixels_in(int x, int y, int w, int h) {
    size_t n = 0;
    for (int row = y; row < y + h; ++row) {
        for (int col = x; col < x + w; ++col) {
            if (pixel(col, row) != 0) {
                ++n;
            }
        }
    }
    return n;
}

}  // namespace picocalc::host
