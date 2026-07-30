#include "picocalc/display.h"

#include <algorithm>
#include <cstdio>

#include "picocalc/board.h"
#include "vendor/lcd_hwspi_rgb888.h"

namespace picocalc::display {
namespace {

constexpr size_t kMaxReadbackPixels = 16;
size_t g_window_pixels_remaining = 0;

bool clip_rect(int* x, int* y, int* w, int* h) {
    if (*x < 0) { *w += *x; *x = 0; }
    if (*y < 0) { *h += *y; *y = 0; }
    if (*x >= width || *y >= height || *w <= 0 || *h <= 0) return false;
    *w = std::min(*w, width - *x);
    *h = std::min(*h, height - *y);
    return *w > 0 && *h > 0;
}

uint16_t rgb888_to_rgb565(const uint8_t* rgb888) {
    return static_cast<uint16_t>(
        (static_cast<uint16_t>(rgb888[0] >> 3) << 11) |
        (static_cast<uint16_t>(rgb888[1] >> 2) << 5) |
        static_cast<uint16_t>(rgb888[2] >> 3));
}

bool readback_pixels(int x, int y, int w, int h, uint16_t* output) {
    const size_t pixels = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (output == nullptr || w <= 0 || h <= 0 || pixels > kMaxReadbackPixels) {
        return false;
    }
    vendor::lcd_hwspi_rgb888::ReadbackResult result;
    if (!vendor::lcd_hwspi_rgb888::readback_rgb888(x, y, w, h, &result)) {
        return false;
    }
    std::printf("[PICOCALC][LCD][READ] transport=hardware_spi1 "
                "reference=picocalc_helloworld read_hz=6000000 "
                "miso=spi rddid=0x%02x%02x%02x "
                "rddst=0x%02x%02x%02x%02x ramrd_dummy=0x%02x "
                "format=rgb888 pixels=%lu\n",
                result.id[0], result.id[1], result.id[2], result.status[0],
                result.status[1], result.status[2], result.status[3],
                result.dummy, static_cast<unsigned long>(pixels));
    for (size_t i = 0; i < pixels; ++i) {
        const uint8_t* raw = &result.raw[i * 3];
        output[i] = rgb888_to_rgb565(raw);
        std::printf("[PICOCALC][LCD][READ] pixel=%lu raw=0x%02x%02x%02x "
                    "value=0x%04x\n",
                    static_cast<unsigned long>(i), raw[0], raw[1], raw[2],
                    output[i]);
    }
    return true;
}

}  // namespace

void init() {
    vendor::lcd_hwspi_rgb888::init();
    std::printf("[PICOCALC][LCD][SPI] transport=hardware_spi1 "
                "driver=vendor/lcd_hwspi_rgb888.cpp "
                "reference=general-lcd-hwspi-rgb888-probe+picocalc-helloworld "
                "hz=25000000 read_hz=6000000 colmod=0x66 wire=rgb888 "
                "window_cs=held_from_caset_through_ramwr\n");
}

void set_window(int x, int y, int w, int h) {
    if (!clip_rect(&x, &y, &w, &h) ||
        !vendor::lcd_hwspi_rgb888::begin_window(x, y, w, h)) {
        g_window_pixels_remaining = 0;
        return;
    }
    g_window_pixels_remaining = static_cast<size_t>(w) * static_cast<size_t>(h);
}

void write_pixels(const uint16_t* pixels, size_t count) {
    if (pixels == nullptr || count == 0 || g_window_pixels_remaining == 0) return;
    count = std::min(count, g_window_pixels_remaining);
    vendor::lcd_hwspi_rgb888::write_pixels_rgb565(pixels, count);
    g_window_pixels_remaining -= count;
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    if (!clip_rect(&x, &y, &w, &h)) return;
    set_window(x, y, w, h);
    if (g_window_pixels_remaining == 0) return;
    vendor::lcd_hwspi_rgb888::write_solid_rgb565(
        rgb565, static_cast<size_t>(w) * static_cast<size_t>(h));
    g_window_pixels_remaining = 0;
}

void clear(uint16_t rgb565) { fill_rect(0, 0, width, height, rgb565); }

void draw_test_pattern() {
    clear(0x0000);
    fill_rect(0, 0, width, 24, 0x07e0);
    fill_rect(0, height - 24, width, 24, 0x001f);
    fill_rect(16, 48, width - 32, height - 96, 0xffff);
    fill_rect(20, 52, width - 40, height - 104, 0x0000);
    fill_rect(32, 72, 80, 80, 0xf800);
    fill_rect(120, 72, 80, 80, 0x07e0);
    fill_rect(208, 72, 80, 80, 0x001f);
}

PixelVerifyResult verify_pixels(int x, int y, int w, int h,
                                const uint16_t* expected, size_t count) {
    const size_t pixels = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (expected == nullptr || w <= 0 || h <= 0 || count != pixels ||
        count > kMaxReadbackPixels) {
        return {false, 0, 0};
    }
    uint16_t actual[kMaxReadbackPixels] = {};
    if (!readback_pixels(x, y, w, h, actual)) return {false, pixels, 0};
    size_t mismatches = 0;
    for (size_t i = 0; i < pixels; ++i) {
        if (actual[i] != expected[i]) {
            ++mismatches;
            std::printf("[PICOCALC][LCD][VERIFY] mismatch index=%lu "
                        "expected=0x%04x actual=0x%04x\n",
                        static_cast<unsigned long>(i), expected[i], actual[i]);
        }
    }
    std::printf("[PICOCALC][LCD][VERIFY] status=%s pixels=%lu mismatches=%lu\n",
                mismatches == 0 ? "pass" : "fail",
                static_cast<unsigned long>(pixels),
                static_cast<unsigned long>(mismatches));
    return {true, pixels, mismatches};
}

}  // namespace picocalc::display
