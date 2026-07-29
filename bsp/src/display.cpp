#include "picocalc/display.h"

#include <algorithm>

#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "lcd_spi_min.pio.h"

namespace picocalc::display {
namespace {

PIO g_pio = pio0;
uint g_sm = 0;
uint g_offset = 0;
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

void write_bytes_raw(const uint8_t* data, size_t len) {
    while (len-- > 0) {
        lcd_spi_min_put(g_pio, g_sm, *data++);
    }
}

void wait_idle() {
    lcd_spi_min_wait_idle(g_pio, g_sm);
}

void write_command(uint8_t command) {
    select();
    set_dc(false);
    write_bytes_raw(&command, 1);
    wait_idle();
    deselect();
}

void write_data(const uint8_t* data, size_t len) {
    if (data == nullptr || len == 0) {
        return;
    }
    select();
    set_dc(true);
    write_bytes_raw(data, len);
    wait_idle();
    deselect();
}

void write_command1(uint8_t command, uint8_t value) {
    write_command(command);
    write_data(&value, 1);
}

void write_commandn(uint8_t command, const uint8_t* values, size_t len) {
    write_command(command);
    write_data(values, len);
}

void reset_panel() {
    gpio_put(board::kLcdReset, 1);
    sleep_ms(1);
    gpio_put(board::kLcdReset, 0);
    sleep_ms(10);
    gpio_put(board::kLcdReset, 1);
    sleep_ms(10);
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
    uint8_t bytes[board::kLcdMaxPixelsPerCs * 2];
    for (int i = 0; i < board::kLcdMaxPixelsPerCs; ++i) {
        bytes[i * 2] = static_cast<uint8_t>(color >> 8);
        bytes[i * 2 + 1] = static_cast<uint8_t>(color);
    }

    while (count > 0) {
        const size_t pixels =
            std::min(count, static_cast<size_t>(board::kLcdMaxPixelsPerCs));
        select();
        set_dc(true);
        write_bytes_raw(bytes, pixels * 2);
        wait_idle();
        deselect();
        count -= pixels;
    }
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

    g_offset = pio_add_program(g_pio, &lcd_spi_min_program);
    lcd_spi_min_program_init(g_pio,
                             g_sm,
                             g_offset,
                             board::kLcdMosi,
                             board::kLcdSck,
                             board::kLcdPioClockDivider);

    reset_panel();

    static const uint8_t b9[] = {0x02, 0xe0};
    static const uint8_t c0[] = {0x80, 0x06};
    static const uint8_t e8[] = {0x40, 0x8a, 0x00, 0x00, 0x29, 0x19, 0xaa, 0x33};
    static const uint8_t e0[] = {0xf0, 0x06, 0x0f, 0x05, 0x04, 0x20, 0x37,
                                 0x33, 0x4c, 0x37, 0x13, 0x14, 0x2b, 0x31};
    static const uint8_t e1[] = {0xf0, 0x11, 0x1b, 0x11, 0x0f, 0x0a, 0x37,
                                 0x43, 0x4c, 0x37, 0x13, 0x13, 0x2c, 0x32};

    // This sequence and COLMOD=0x65 come from the working PicoCalc projects.
    write_command1(0xf0, 0xc3);
    write_command1(0xf0, 0x96);
    write_command1(0x36, 0x48);
    write_command1(0x3a, 0x65);
    write_command1(0xb1, 0xa0);
    write_command1(0xb4, 0x00);
    write_command1(0xb7, 0xc6);
    write_commandn(0xb9, b9, sizeof(b9));
    write_commandn(0xc0, c0, sizeof(c0));
    write_command1(0xc1, 0x15);
    write_command1(0xc2, 0xa7);
    write_command1(0xc5, 0x04);
    write_commandn(0xe8, e8, sizeof(e8));
    write_commandn(0xe0, e0, sizeof(e0));
    write_commandn(0xe1, e1, sizeof(e1));
    write_command1(0xf0, 0x3c);
    write_command1(0xf0, 0x69);
    write_command1(0x35, 0x00);
    write_command(0x11);
    sleep_ms(120);
    write_command(0x21);
    clear(0x0000);
    write_command(0x29);
    sleep_ms(120);
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
    uint8_t bytes[board::kLcdMaxPixelsPerCs * 2];
    while (count > 0) {
        const size_t chunk =
            std::min(count, static_cast<size_t>(board::kLcdMaxPixelsPerCs));
        for (size_t i = 0; i < chunk; ++i) {
            bytes[i * 2] = static_cast<uint8_t>(pixels[i] >> 8);
            bytes[i * 2 + 1] = static_cast<uint8_t>(pixels[i]);
        }
        select();
        set_dc(true);
        write_bytes_raw(bytes, chunk * 2);
        wait_idle();
        deselect();
        pixels += chunk;
        count -= chunk;
        g_window_pixels_remaining -= chunk;
    }
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
