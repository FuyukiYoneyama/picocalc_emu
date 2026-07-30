#include <stdio.h>

#include "picocalc/display.h"

void copy_lcd_example() {
    constexpr uint16_t kRed = 0xf800;
    constexpr uint16_t kGreen = 0x07e0;
    constexpr uint16_t kBlue = 0x001f;
    const uint16_t pixels[] = {kRed, kGreen, kBlue, 0xffff};

    picocalc::display::clear(0x0000);
    picocalc::display::fill_rect(16, 16, 288, 80, kRed);
    picocalc::display::set_window(32, 120, 2, 2);
    picocalc::display::write_pixels(pixels, 4);

    const auto result = picocalc::display::verify_pixels(
        32, 120, 2, 2, pixels, 4);
    printf("[PICOCALC][EXAMPLE][LCD] status=%s pixels=%lu mismatches=%lu\n",
           result.ok() ? "pass" : "fail",
           static_cast<unsigned long>(result.pixels),
           static_cast<unsigned long>(result.mismatches));
}
