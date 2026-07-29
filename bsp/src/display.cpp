#include "picocalc/display.h"

#include <algorithm>

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "picocalc/detail/lcd_protocol.h"

namespace picocalc::display {
namespace {

size_t g_window_pixels_remaining = 0;

void select() {
    gpio_put(board::kLcdCs, 0);
}

void deselect() {
    gpio_put(board::kLcdCs, 1);
}

void set_dc(bool data) {
    gpio_put(board::kLcdDc, data ? 1 : 0);
}

void wait_idle() {
    while (spi_is_busy(spi1)) {
        tight_loop_contents();
    }
}

class HardwareSpiTransport {
public:
    void select() {
        picocalc::display::select();
    }

    void deselect() {
        picocalc::display::deselect();
    }

    void set_data_mode(bool data) {
        set_dc(data);
    }

    void write(const uint8_t* data, size_t len) {
        spi_write_blocking(spi1, data, len);
    }

    void wait_idle() {
        picocalc::display::wait_idle();
    }
};

HardwareSpiTransport g_transport;

void write_command(uint8_t command) {
    detail::lcd::write_command(g_transport, command);
}

void write_commandn(uint8_t command, const uint8_t* values, size_t len) {
    detail::lcd::write_command_data(g_transport, command, values, len);
}

void reset_panel() {
    gpio_put(board::kLcdReset, 1);
    sleep_ms(10);
    gpio_put(board::kLcdReset, 0);
    sleep_ms(10);
    gpio_put(board::kLcdReset, 1);
    sleep_ms(200);
}

bool clip_rect(int* x, int* y, int* w, int* h) {
    if (*x < 0) {
        *w += *x;
        *x = 0;
    }
    if (*y < 0) {
        *h += *y;
        *y = 0;
    }
    if (*x >= width || *y >= height || *w <= 0 || *h <= 0) {
        return false;
    }
    *w = std::min(*w, width - *x);
    *h = std::min(*h, height - *y);
    return *w > 0 && *h > 0;
}

void send_solid_pixels(uint16_t color, size_t count) {
    uint8_t bytes[board::kLcdMaxPixelsPerCs * 3];
    const uint8_t r5 = static_cast<uint8_t>((color >> 11) & 0x1f);
    const uint8_t g6 = static_cast<uint8_t>((color >> 5) & 0x3f);
    const uint8_t b5 = static_cast<uint8_t>(color & 0x1f);
    const uint8_t red = static_cast<uint8_t>((r5 << 3) | (r5 >> 2));
    const uint8_t green = static_cast<uint8_t>((g6 << 2) | (g6 >> 4));
    const uint8_t blue = static_cast<uint8_t>((b5 << 3) | (b5 >> 2));
    for (int i = 0; i < board::kLcdMaxPixelsPerCs; ++i) {
        bytes[i * 3] = red;
        bytes[i * 3 + 1] = green;
        bytes[i * 3 + 2] = blue;
    }

    set_dc(true);
    select();
    detail::lcd::for_each_chunk(
        count,
        static_cast<size_t>(board::kLcdMaxPixelsPerCs),
        [&](size_t pixels) {
            spi_write_blocking(spi1, bytes, pixels * 3);
        });
    wait_idle();
    deselect();
}

}  // namespace

void init() {
    gpio_init(board::kLcdCs);
    gpio_init(board::kLcdDc);
    gpio_init(board::kLcdReset);
    gpio_init(board::kLcdMiso);
    gpio_set_dir(board::kLcdCs, GPIO_OUT);
    gpio_set_dir(board::kLcdDc, GPIO_OUT);
    gpio_set_dir(board::kLcdReset, GPIO_OUT);
    gpio_set_dir(board::kLcdMiso, GPIO_IN);
    gpio_disable_pulls(board::kLcdMiso);
    gpio_put(board::kLcdCs, 1);
    gpio_put(board::kLcdDc, 1);
    gpio_put(board::kLcdReset, 1);

    gpio_set_drive_strength(board::kLcdCs, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_drive_strength(board::kLcdDc, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_drive_strength(board::kLcdReset, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_function(board::kLcdSck, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMosi, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMiso, GPIO_FUNC_SPI);
    gpio_set_input_hysteresis_enabled(board::kLcdMiso, true);
    spi_init(spi1, board::kLcdSpiHz);

    reset_panel();

    detail::lcd::initialize_controller(
        g_transport,
        [](uint32_t milliseconds) { sleep_ms(milliseconds); },
        []() { clear(0x0000); });
}

void set_window(int x, int y, int w, int h) {
    if (!clip_rect(&x, &y, &w, &h)) {
        g_window_pixels_remaining = 0;
        return;
    }

    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {
        static_cast<uint8_t>(x >> 8),
        static_cast<uint8_t>(x),
        static_cast<uint8_t>(x1 >> 8),
        static_cast<uint8_t>(x1),
    };
    const uint8_t rows[] = {
        static_cast<uint8_t>(y >> 8),
        static_cast<uint8_t>(y),
        static_cast<uint8_t>(y1 >> 8),
        static_cast<uint8_t>(y1),
    };
    write_commandn(0x2a, columns, sizeof(columns));
    write_commandn(0x2b, rows, sizeof(rows));
    write_command(0x2c);
    g_window_pixels_remaining = static_cast<size_t>(w) * static_cast<size_t>(h);
}

void write_pixels(const uint16_t* pixels, size_t count) {
    if (pixels == nullptr || count == 0 || g_window_pixels_remaining == 0) {
        return;
    }
    count = std::min(count, g_window_pixels_remaining);
    uint8_t bytes[board::kLcdMaxPixelsPerCs * 3];
    size_t offset = 0;
    set_dc(true);
    select();
    detail::lcd::for_each_chunk(
        count,
        static_cast<size_t>(board::kLcdMaxPixelsPerCs),
        [&](size_t chunk) {
            for (size_t i = 0; i < chunk; ++i) {
                const uint16_t color = pixels[offset + i];
                const uint8_t r5 = static_cast<uint8_t>((color >> 11) & 0x1f);
                const uint8_t g6 = static_cast<uint8_t>((color >> 5) & 0x3f);
                const uint8_t b5 = static_cast<uint8_t>(color & 0x1f);
                bytes[i * 3] = static_cast<uint8_t>((r5 << 3) | (r5 >> 2));
                bytes[i * 3 + 1] =
                    static_cast<uint8_t>((g6 << 2) | (g6 >> 4));
                bytes[i * 3 + 2] = static_cast<uint8_t>((b5 << 3) | (b5 >> 2));
            }
            spi_write_blocking(spi1, bytes, chunk * 3);
            offset += chunk;
            g_window_pixels_remaining -= chunk;
        });
    wait_idle();
    deselect();
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    if (!clip_rect(&x, &y, &w, &h)) {
        return;
    }
    set_window(x, y, w, h);
    const size_t count = static_cast<size_t>(w) * static_cast<size_t>(h);
    send_solid_pixels(rgb565, count);
    g_window_pixels_remaining = 0;
}

void clear(uint16_t rgb565) {
    fill_rect(0, 0, width, height, rgb565);
}

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

}  // namespace picocalc::display
