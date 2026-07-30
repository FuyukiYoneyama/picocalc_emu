#include "picocalc/display.h"

#include <algorithm>
#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "vendor/lcd_rgb565_pio.h"

// LCD BSP B (pio-rgb565).
//
// This file is an adapter, not a driver. Every LCD signal, timing and transfer
// decision lives in bsp/vendor/lcd_rgb565_pio.cpp, which is an unmodified copy of
// general/lcd/src/lcd_rgb565_pio.cpp. game/pico_skyace displayed on real hardware
// by copying that same file unmodified and calling it at one granularity:
// one set_window per 160x160 quadrant, then 160 pixel write_blocking calls.
// This adapter reproduces that call pattern and adds nothing else.
//
// Earlier revisions of this BSP re-implemented the transport by hand and did not
// display. Do not move transport logic back into this file.
namespace picocalc::display {
namespace {

// The vendored driver hardcodes the PicoCalc LCD pins. Fail the build if the
// generated board profile ever disagrees with it.
static_assert(board::kLcdSck == 10 && board::kLcdMosi == 11 &&
                  board::kLcdMiso == 12 && board::kLcdCs == 13 &&
                  board::kLcdDc == 14 && board::kLcdReset == 15,
              "Vendored lcd_rgb565_pio.cpp pins disagree with the board profile");
static_assert(width == 320 && height == 320,
              "Vendored lcd_rgb565_pio.cpp is a 320x320 driver");

// Call granularity copied from pico_skyace: 160 pixel transfer units and
// 160x160 windows.
constexpr int kTileSide = board::kLcdMaxPixelsPerCs;
constexpr size_t kPixelsPerCall = static_cast<size_t>(board::kLcdMaxPixelsPerCs);
constexpr size_t kMaxReadbackPixels = 16;

// The vendored driver owns pio0 state machine 0 for writes. RAMRD borrows the
// pins the way the life screenshot-capture build does.
constexpr uint kSm = 0;

uint16_t g_line[kTileSide] = {};
size_t g_window_pixels_remaining = 0;

void select() { gpio_put(board::kLcdCs, 0); }
void deselect() { gpio_put(board::kLcdCs, 1); }
void set_dc(bool data) { gpio_put(board::kLcdDc, data ? 1 : 0); }

bool clip_rect(int* x, int* y, int* w, int* h) {
    if (*x < 0) { *w += *x; *x = 0; }
    if (*y < 0) { *h += *y; *y = 0; }
    if (*x >= width || *y >= height || *w <= 0 || *h <= 0) return false;
    *w = std::min(*w, width - *x);
    *h = std::min(*h, height - *y);
    return *w > 0 && *h > 0;
}

// ---------------------------------------------------------------------------
// RAMRD. This is life/src/platform/picocalc_display.cpp's capture-build
// procedure: stop the PIO state machine, take SCK/MOSI/MISO as SIO, send
// CASET/RASET/RAMRD by hand with CS held, read one dummy byte and then two bytes
// per pixel on the falling edge, then give the pins back. That build produces
// correct PicoCalc screenshots, so the sequence is kept identical here.
// ---------------------------------------------------------------------------
void read_io_delay() { busy_wait_us_32(1); }

void set_bitbang_mode(bool enabled) {
    if (enabled) {
        pio_sm_set_enabled(pio0, kSm, false);
        gpio_set_function(board::kLcdSck, GPIO_FUNC_SIO);
        gpio_set_function(board::kLcdMosi, GPIO_FUNC_SIO);
        gpio_set_function(board::kLcdMiso, GPIO_FUNC_SIO);
        gpio_set_dir(board::kLcdSck, GPIO_OUT);
        gpio_set_dir(board::kLcdMosi, GPIO_OUT);
        gpio_set_dir(board::kLcdMiso, GPIO_IN);
        gpio_disable_pulls(board::kLcdMiso);
        gpio_put(board::kLcdSck, 0);
        gpio_put(board::kLcdMosi, 0);
        return;
    }
    gpio_set_function(board::kLcdSck, GPIO_FUNC_PIO0);
    gpio_set_function(board::kLcdMosi, GPIO_FUNC_PIO0);
    gpio_set_function(board::kLcdMiso, GPIO_FUNC_SIO);
    gpio_set_dir(board::kLcdMiso, GPIO_IN);
    gpio_disable_pulls(board::kLcdMiso);
    pio_sm_set_enabled(pio0, kSm, true);
}

void bitbang_write_byte(uint8_t value) {
    for (int bit = 7; bit >= 0; --bit) {
        gpio_put(board::kLcdSck, 0);
        gpio_put(board::kLcdMosi, (value >> bit) & 1u);
        read_io_delay();
        gpio_put(board::kLcdSck, 1);
        read_io_delay();
    }
    gpio_put(board::kLcdSck, 0);
}

uint8_t bitbang_read_byte_falling() {
    uint8_t value = 0;
    for (int bit = 7; bit >= 0; --bit) {
        gpio_put(board::kLcdSck, 0);
        read_io_delay();
        if (gpio_get(board::kLcdMiso)) value |= static_cast<uint8_t>(1u << bit);
        gpio_put(board::kLcdSck, 1);
        read_io_delay();
    }
    gpio_put(board::kLcdSck, 0);
    return value;
}

void bitbang_write_commandn_held(uint8_t command, const uint8_t* data, size_t length) {
    set_dc(false);
    bitbang_write_byte(command);
    if (data == nullptr || length == 0) return;
    set_dc(true);
    while (length-- > 0) bitbang_write_byte(*data++);
}

void bitbang_set_read_window(int x, int y, int w, int h) {
    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {static_cast<uint8_t>(x >> 8), static_cast<uint8_t>(x),
                               static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1)};
    const uint8_t rows[] = {static_cast<uint8_t>(y >> 8), static_cast<uint8_t>(y),
                            static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1)};
    bitbang_write_commandn_held(0x2a, columns, sizeof(columns));
    bitbang_write_commandn_held(0x2b, rows, sizeof(rows));
}

bool readback_pixels(int x, int y, int w, int h, uint16_t* output) {
    const size_t pixel_count = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (output == nullptr || w <= 0 || h <= 0 || pixel_count > kMaxReadbackPixels ||
        x < 0 || y < 0 || x + w > width || y + h > height) return false;

    lcd_rgb565_pio_wait_dma();
    set_bitbang_mode(true);
    select();
    bitbang_set_read_window(x, y, w, h);
    set_dc(false);
    bitbang_write_byte(0x2e);
    set_dc(true);
    const uint8_t dummy = bitbang_read_byte_falling();
    uint8_t raw[kMaxReadbackPixels * 2] = {};
    for (size_t i = 0; i < pixel_count * 2; ++i) raw[i] = bitbang_read_byte_falling();
    deselect();
    set_bitbang_mode(false);

    printf("[PICOCALC][LCD][READ] transport=bitbang_sio reference=life-capture "
           "ramrd dummy=0x%02x format=rgb565 pixels=%lu\n",
           dummy, static_cast<unsigned long>(pixel_count));
    for (size_t i = 0; i < pixel_count; ++i) {
        output[i] = static_cast<uint16_t>(
            (static_cast<uint16_t>(raw[i * 2]) << 8) | raw[i * 2 + 1]);
        printf("[PICOCALC][LCD][READ] pixel=%lu raw=0x%02x%02x value=0x%04x\n",
               static_cast<unsigned long>(i), raw[i * 2], raw[i * 2 + 1], output[i]);
    }
    return true;
}

// Fills one window that is already set, in 160 pixel units.
void write_line_units(int pixels_per_row, int rows) {
    for (int row = 0; row < rows; ++row) {
        lcd_rgb565_pio_write_blocking(g_line, pixels_per_row);
    }
}

}  // namespace

void init() {
    // The vendored driver initializes GPIO, PIO, the panel and clears to black.
    lcd_rgb565_pio_init(false);
    printf("[PICOCALC][LCD][PIO] transport=pio0_blocking driver=vendor/lcd_rgb565_pio.cpp "
           "reference=general-lcd-pico_skyace colmod=0x65 wire=rgb565 clkdiv=2.00 "
           "window_max=%dx%d call_unit=%lu_pixels\n",
           kTileSide, kTileSide, static_cast<unsigned long>(kPixelsPerCall));
}

void set_window(int x, int y, int w, int h) {
    if (!clip_rect(&x, &y, &w, &h)) { g_window_pixels_remaining = 0; return; }
    lcd_rgb565_pio_set_window(x, y, w, h);
    g_window_pixels_remaining = static_cast<size_t>(w) * static_cast<size_t>(h);
}

void write_pixels(const uint16_t* pixels, size_t count) {
    if (pixels == nullptr || count == 0 || g_window_pixels_remaining == 0) return;
    count = std::min(count, g_window_pixels_remaining);
    size_t offset = 0;
    while (offset < count) {
        const size_t chunk = std::min(count - offset, kPixelsPerCall);
        lcd_rgb565_pio_write_blocking(pixels + offset, static_cast<int>(chunk));
        offset += chunk;
        g_window_pixels_remaining -= chunk;
    }
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    if (!clip_rect(&x, &y, &w, &h)) return;
    for (int i = 0; i < kTileSide; ++i) g_line[i] = rgb565;
    // One window per 160x160 tile, then 160 pixel transfer units: the quadrant
    // pattern that pico_skyace uses.
    for (int tile_y = y; tile_y < y + h; tile_y += kTileSide) {
        const int tile_h = std::min(kTileSide, y + h - tile_y);
        for (int tile_x = x; tile_x < x + w; tile_x += kTileSide) {
            const int tile_w = std::min(kTileSide, x + w - tile_x);
            lcd_rgb565_pio_set_window(tile_x, tile_y, tile_w, tile_h);
            write_line_units(tile_w, tile_h);
        }
    }
    g_window_pixels_remaining = 0;
}

void clear(uint16_t rgb565) { fill_rect(0, 0, width, height, rgb565); }

void draw_test_pattern() {
    clear(0x0000);
    fill_rect(0, 0, width, 24, 0x07e0); fill_rect(0, height - 24, width, 24, 0x001f);
    fill_rect(16, 48, width - 32, height - 96, 0xffff);
    fill_rect(20, 52, width - 40, height - 104, 0x0000);
    fill_rect(32, 72, 80, 80, 0xf800); fill_rect(120, 72, 80, 80, 0x07e0);
    fill_rect(208, 72, 80, 80, 0x001f);
}

PixelVerifyResult verify_pixels(int x, int y, int w, int h,
                                const uint16_t* expected, size_t count) {
    const size_t pixels = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (expected == nullptr || w <= 0 || h <= 0 || count != pixels ||
        count > kMaxReadbackPixels) return {false, 0, 0};
    uint16_t actual[kMaxReadbackPixels] = {};
    if (!readback_pixels(x, y, w, h, actual)) return {false, pixels, 0};
    size_t mismatches = 0;
    for (size_t i = 0; i < pixels; ++i) {
        if (actual[i] != expected[i]) {
            ++mismatches;
            printf("[PICOCALC][LCD][VERIFY] mismatch index=%lu expected=0x%04x actual=0x%04x\n",
                   static_cast<unsigned long>(i), expected[i], actual[i]);
        }
    }
    printf("[PICOCALC][LCD][VERIFY] status=%s pixels=%lu mismatches=%lu\n",
           mismatches == 0 ? "pass" : "fail", static_cast<unsigned long>(pixels),
           static_cast<unsigned long>(mismatches));
    return {true, pixels, mismatches};
}

}  // namespace picocalc::display
