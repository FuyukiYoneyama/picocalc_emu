#pragma once

#include <stddef.h>
#include <stdint.h>

namespace picocalc::vendor::lcd_hwspi_rgb888 {

constexpr size_t kMaxReadbackPixels = 16;

struct ReadbackResult {
    uint8_t id[3] = {};
    uint8_t status[4] = {};
    uint8_t dummy = 0;
    uint8_t raw[kMaxReadbackPixels * 3] = {};
};

void init();

// Begins the loader-style transaction and leaves CS asserted. The caller must
// complete it with write_pixels_rgb565() or write_solid_rgb565().
bool begin_window(int x, int y, int w, int h);
void write_pixels_rgb565(const uint16_t* pixels, size_t count);
void write_solid_rgb565(uint16_t color, size_t count);

bool readback_rgb888(int x, int y, int w, int h, ReadbackResult* result);

}  // namespace picocalc::vendor::lcd_hwspi_rgb888
