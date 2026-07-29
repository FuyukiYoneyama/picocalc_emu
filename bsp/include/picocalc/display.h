#pragma once

#include <stddef.h>
#include <stdint.h>

namespace picocalc::display {

constexpr int width = 320;
constexpr int height = 320;

void init();
void clear(uint16_t rgb565);
void set_window(int x, int y, int w, int h);
void write_pixels(const uint16_t* pixels, size_t count);
void fill_rect(int x, int y, int w, int h, uint16_t rgb565);
void draw_test_pattern();

struct PixelVerifyResult {
    bool transport_ok;
    size_t pixels;
    size_t mismatches;

    bool ok() const {
        return transport_ok && mismatches == 0;
    }
};

// The public pixel type is RGB565. Each independent LCD BSP selects its own
// proven wire format: A sends RGB888 and B sends RGB565. RAMRD is decoded by
// that selected BSP and compared in this public RGB565 representation.
PixelVerifyResult verify_pixels(int x, int y, int w, int h,
                                const uint16_t* expected, size_t count);

}  // namespace picocalc::display
