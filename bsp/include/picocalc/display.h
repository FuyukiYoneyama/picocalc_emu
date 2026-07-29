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

}  // namespace picocalc::display
