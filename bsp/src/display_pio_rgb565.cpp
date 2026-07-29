#include "picocalc/display.h"

#include <algorithm>
#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "lcd_spi_min.pio.h"

namespace picocalc::display {
namespace {

constexpr float kPioClockDivider = 2.0f;
constexpr size_t kMaxReadbackPixels = 16;
PIO g_pio = pio0;
uint g_sm = 0;
uint g_program_offset = 0;
size_t g_window_pixels_remaining = 0;

void select() { gpio_put(board::kLcdCs, 0); }
void deselect() { gpio_put(board::kLcdCs, 1); }
void set_dc(bool data) { gpio_put(board::kLcdDc, data ? 1 : 0); }

void write_bytes(const uint8_t* data, size_t length) {
    while (length-- > 0) {
        lcd_spi_min_put(g_pio, g_sm, *data++);
    }
}

void wait_idle() { lcd_spi_min_wait_idle(g_pio, g_sm); }

void write_command(uint8_t command) {
    select();
    set_dc(false);
    write_bytes(&command, 1);
    wait_idle();
    deselect();
}

void write_data(const uint8_t* data, size_t length) {
    if (length == 0) return;
    select();
    set_dc(true);
    write_bytes(data, length);
    wait_idle();
    deselect();
}

void write_command1(uint8_t command, uint8_t value) {
    write_command(command);
    write_data(&value, 1);
}

void write_command_data(uint8_t command, const uint8_t* data, size_t length) {
    write_command(command);
    write_data(data, length);
}

void reset_panel() {
    gpio_put(board::kLcdReset, 1);
    sleep_ms(1);
    gpio_put(board::kLcdReset, 0);
    sleep_ms(10);
    gpio_put(board::kLcdReset, 1);
    sleep_ms(10);
}

void initialize_controller() {
    static const uint8_t b9[] = {0x02, 0xe0};
    static const uint8_t c0[] = {0x80, 0x06};
    static const uint8_t e8[] = {0x40, 0x8a, 0x00, 0x00, 0x29, 0x19, 0xaa, 0x33};
    static const uint8_t e0[] = {0xf0, 0x06, 0x0f, 0x05, 0x04, 0x20, 0x37, 0x33,
                                 0x4c, 0x37, 0x13, 0x14, 0x2b, 0x31};
    static const uint8_t e1[] = {0xf0, 0x11, 0x1b, 0x11, 0x0f, 0x0a, 0x37, 0x43,
                                 0x4c, 0x37, 0x13, 0x13, 0x2c, 0x32};

    reset_panel();
    write_command1(0xf0, 0xc3);
    write_command1(0xf0, 0x96);
    write_command1(0x36, 0x48);
    write_command1(0x3a, 0x65);
    write_command1(0xb1, 0xa0);
    write_command1(0xb4, 0x00);
    write_command1(0xb7, 0xc6);
    write_command_data(0xb9, b9, sizeof(b9));
    write_command_data(0xc0, c0, sizeof(c0));
    write_command1(0xc1, 0x15);
    write_command1(0xc2, 0xa7);
    write_command1(0xc5, 0x04);
    write_command_data(0xe8, e8, sizeof(e8));
    write_command_data(0xe0, e0, sizeof(e0));
    write_command_data(0xe1, e1, sizeof(e1));
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

bool clip_rect(int* x, int* y, int* w, int* h) {
    if (*x < 0) { *w += *x; *x = 0; }
    if (*y < 0) { *h += *y; *y = 0; }
    if (*x >= width || *y >= height || *w <= 0 || *h <= 0) return false;
    *w = std::min(*w, width - *x);
    *h = std::min(*h, height - *y);
    return *w > 0 && *h > 0;
}

void set_window_unclipped(int x, int y, int w, int h) {
    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {static_cast<uint8_t>(x >> 8), static_cast<uint8_t>(x),
                               static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1)};
    const uint8_t rows[] = {static_cast<uint8_t>(y >> 8), static_cast<uint8_t>(y),
                            static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1)};
    write_command_data(0x2a, columns, sizeof(columns));
    write_command_data(0x2b, rows, sizeof(rows));
    write_command(0x2c);
    g_window_pixels_remaining = static_cast<size_t>(w) * static_cast<size_t>(h);
}

void send_solid_pixels(uint16_t color, size_t count) {
    const uint8_t bytes[] = {static_cast<uint8_t>(color >> 8),
                             static_cast<uint8_t>(color & 0xff)};
    select();
    set_dc(true);
    while (count-- > 0) write_bytes(bytes, sizeof(bytes));
    wait_idle();
    deselect();
    g_window_pixels_remaining = 0;
}

void read_io_delay() { busy_wait_us_32(1); }

void set_bitbang_mode(bool enabled) {
    if (enabled) {
        pio_sm_set_enabled(g_pio, g_sm, false);
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
    pio_sm_set_enabled(g_pio, g_sm, true);
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

void write_bytes_sio(const uint8_t* data, size_t length) {
    while (length-- > 0) bitbang_write_byte(*data++);
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

void bitbang_set_read_window(int x, int y, int w, int h) {
    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {static_cast<uint8_t>(x >> 8), static_cast<uint8_t>(x),
                               static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1)};
    const uint8_t rows[] = {static_cast<uint8_t>(y >> 8), static_cast<uint8_t>(y),
                            static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1)};
    set_dc(false); bitbang_write_byte(0x2a); set_dc(true); write_bytes_sio(columns, sizeof(columns));
    set_dc(false); bitbang_write_byte(0x2b); set_dc(true); write_bytes_sio(rows, sizeof(rows));
}

bool readback_pixels(int x, int y, int w, int h, uint16_t* output) {
    const size_t pixel_count = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (output == nullptr || w <= 0 || h <= 0 || pixel_count > kMaxReadbackPixels ||
        x < 0 || y < 0 || x + w > width || y + h > height) return false;
    set_bitbang_mode(true);
    select();
    bitbang_set_read_window(x, y, w, h);
    set_dc(false); bitbang_write_byte(0x2e); set_dc(true);
    const uint8_t dummy = bitbang_read_byte_falling();
    printf("[PICOCALC][LCD][READ] transport=pio_sio ramrd dummy=0x%02x format=rgb565 pixels=%lu\n",
           dummy, static_cast<unsigned long>(pixel_count));
    for (size_t i = 0; i < pixel_count; ++i) {
        const uint8_t hi = bitbang_read_byte_falling();
        const uint8_t lo = bitbang_read_byte_falling();
        output[i] = static_cast<uint16_t>((static_cast<uint16_t>(hi) << 8) | lo);
        printf("[PICOCALC][LCD][READ] pixel=%lu raw=0x%02x%02x value=0x%04x\n",
               static_cast<unsigned long>(i), hi, lo, output[i]);
    }
    deselect();
    set_bitbang_mode(false);
    return true;
}

}  // namespace

void init() {
    gpio_init(board::kLcdSck); gpio_init(board::kLcdMosi); gpio_init(board::kLcdMiso);
    gpio_init(board::kLcdCs); gpio_init(board::kLcdDc); gpio_init(board::kLcdReset);
    gpio_init(board::kPsramSck);
    gpio_set_dir(board::kLcdCs, GPIO_OUT); gpio_set_dir(board::kLcdDc, GPIO_OUT);
    gpio_set_dir(board::kLcdReset, GPIO_OUT); gpio_set_dir(board::kLcdMiso, GPIO_IN);
    gpio_set_dir(board::kPsramSck, GPIO_OUT);
    gpio_disable_pulls(board::kLcdMiso);
    gpio_put(board::kLcdCs, 1); gpio_put(board::kLcdDc, 1);
    gpio_put(board::kLcdReset, 1); gpio_put(board::kPsramSck, 1);
    g_program_offset = pio_add_program(g_pio, &lcd_spi_min_program);
    lcd_spi_min_program_init(g_pio, g_sm, g_program_offset,
                             board::kLcdMosi, board::kLcdSck,
                             kPioClockDivider);
    initialize_controller();
    printf("[PICOCALC][LCD][PIO] transport=pio0_blocking sm=0 clkdiv=%.2f "
           "hz=62500000 colmod=0x65 wire=rgb565\n",
           static_cast<double>(kPioClockDivider));
}

void set_window(int x, int y, int w, int h) {
    if (!clip_rect(&x, &y, &w, &h)) { g_window_pixels_remaining = 0; return; }
    set_window_unclipped(x, y, w, h);
}

void write_pixels(const uint16_t* pixels, size_t count) {
    if (pixels == nullptr || count == 0 || g_window_pixels_remaining == 0) return;
    count = std::min(count, g_window_pixels_remaining);
    select(); set_dc(true);
    for (size_t i = 0; i < count; ++i) {
        const uint8_t bytes[] = {static_cast<uint8_t>(pixels[i] >> 8),
                                 static_cast<uint8_t>(pixels[i] & 0xff)};
        write_bytes(bytes, sizeof(bytes));
    }
    wait_idle(); deselect(); g_window_pixels_remaining -= count;
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    if (!clip_rect(&x, &y, &w, &h)) return;
    set_window_unclipped(x, y, w, h);
    send_solid_pixels(rgb565, static_cast<size_t>(w) * static_cast<size_t>(h));
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
