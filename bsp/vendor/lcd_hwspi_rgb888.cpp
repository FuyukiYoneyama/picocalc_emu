#include "lcd_hwspi_rgb888.h"

#include <algorithm>
#include <cstdio>

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"

namespace picocalc::vendor::lcd_hwspi_rgb888 {
namespace {

constexpr int kWidth = 320;
constexpr int kHeight = 320;
constexpr uint32_t kReadbackSpiHz = 6000000;
constexpr size_t kPixelsPerBuffer = 160;

bool g_window_open = false;
uint8_t g_line[kPixelsPerBuffer * 3] = {};

void select() { gpio_put(board::kLcdCs, 0); }
void deselect() { gpio_put(board::kLcdCs, 1); }
void set_dc(bool data) { gpio_put(board::kLcdDc, data ? 1 : 0); }

void wait_idle() {
    while (spi_is_busy(spi1)) {
        tight_loop_contents();
    }
}

void write_command(uint8_t command) {
    set_dc(false);
    select();
    spi_write_blocking(spi1, &command, 1);
    wait_idle();
    deselect();
}

void write_data(const uint8_t* data, size_t length) {
    if (data == nullptr || length == 0) return;
    set_dc(true);
    select();
    spi_write_blocking(spi1, data, length);
    wait_idle();
    deselect();
}

void write_data1(uint8_t value) { write_data(&value, 1); }

void reset_controller() {
    gpio_put(board::kLcdReset, 1);
    sleep_ms(10);
    gpio_put(board::kLcdReset, 0);
    sleep_ms(10);
    gpio_put(board::kLcdReset, 1);
    sleep_ms(200);
}

void init_gpio_spi() {
    gpio_init(board::kLcdSck);
    gpio_init(board::kLcdMosi);
    gpio_init(board::kLcdMiso);
    gpio_init(board::kLcdCs);
    gpio_init(board::kLcdDc);
    gpio_init(board::kLcdReset);

    gpio_set_dir(board::kLcdCs, GPIO_OUT);
    gpio_set_dir(board::kLcdDc, GPIO_OUT);
    gpio_set_dir(board::kLcdReset, GPIO_OUT);
    gpio_set_drive_strength(board::kLcdCs, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_drive_strength(board::kLcdDc, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_drive_strength(board::kLcdReset, GPIO_DRIVE_STRENGTH_12MA);

    deselect();
    set_dc(true);
    gpio_put(board::kLcdReset, 1);

    spi_init(spi1, board::kLcdSpiHz);
    gpio_set_function(board::kLcdSck, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMosi, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMiso, GPIO_FUNC_SPI);
    gpio_set_input_hysteresis_enabled(board::kLcdMiso, true);
}

void init_controller() {
    reset_controller();

    static const uint8_t e0[] = {0x00, 0x03, 0x09, 0x08, 0x16, 0x0a, 0x3f, 0x78,
                                 0x4c, 0x09, 0x0a, 0x08, 0x16, 0x1a, 0x0f};
    static const uint8_t e1[] = {0x00, 0x16, 0x19, 0x03, 0x0f, 0x05, 0x32, 0x45,
                                 0x46, 0x04, 0x0e, 0x0d, 0x35, 0x37, 0x0f};
    static const uint8_t c0[] = {0x17, 0x15};
    static const uint8_t c5[] = {0x00, 0x12, 0x80};
    static const uint8_t b6[] = {0x02, 0x02, 0x3b};
    static const uint8_t f7[] = {0xa9, 0x51, 0x2c, 0x82};

    write_command(0xe0); write_data(e0, sizeof(e0));
    write_command(0xe1); write_data(e1, sizeof(e1));
    write_command(0xc0); write_data(c0, sizeof(c0));
    write_command(0xc1); write_data1(0x41);
    write_command(0xc5); write_data(c5, sizeof(c5));
    write_command(0x36); write_data1(0x48);
    write_command(0x3a); write_data1(0x66);
    write_command(0xb0); write_data1(0x00);
    write_command(0xb1); write_data1(0xa0);
    write_command(0x21);
    write_command(0xb4); write_data1(0x02);
    write_command(0xb6); write_data(b6, sizeof(b6));
    write_command(0xb7); write_data1(0xc6);
    write_command(0xe9); write_data1(0x00);
    write_command(0xf7); write_data(f7, sizeof(f7));
    write_command(0x11);
    sleep_ms(120);
    write_command(0x29);
    sleep_ms(120);
    write_command(0x36);
    write_data1(0x48);
}

void rgb565_to_rgb888(uint16_t color, uint8_t* red, uint8_t* green, uint8_t* blue) {
    const uint8_t r5 = static_cast<uint8_t>((color >> 11) & 0x1f);
    const uint8_t g6 = static_cast<uint8_t>((color >> 5) & 0x3f);
    const uint8_t b5 = static_cast<uint8_t>(color & 0x1f);
    *red = static_cast<uint8_t>((r5 << 3) | (r5 >> 2));
    *green = static_cast<uint8_t>((g6 << 2) | (g6 >> 4));
    *blue = static_cast<uint8_t>((b5 << 3) | (b5 >> 2));
}

void write_rgb888_bytes(const uint8_t* data, size_t pixels) {
    spi_write_blocking(spi1, data, pixels * 3);
}

bool read_command(uint8_t command, size_t dummy_bytes, uint8_t* output, size_t length) {
    set_dc(false);
    select();
    spi_write_blocking(spi1, &command, 1);
    wait_idle();
    set_dc(true);
    uint8_t discarded = 0;
    for (size_t i = 0; i < dummy_bytes; ++i) {
        spi_read_blocking(spi1, 0xff, &discarded, 1);
    }
    if (output != nullptr && length > 0) {
        spi_read_blocking(spi1, 0xff, output, length);
    }
    wait_idle();
    deselect();
    return true;
}

}  // namespace

void init() {
    init_gpio_spi();
    init_controller();
    std::printf("LCD loader-style init sequence sent 0x3A=0x66 RGB888\r\n");
}

bool begin_window(int x, int y, int w, int h) {
    if (g_window_open || w <= 0 || h <= 0 || x < 0 || y < 0 ||
        x + w > kWidth || y + h > kHeight) {
        return false;
    }
    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {static_cast<uint8_t>(x >> 8), static_cast<uint8_t>(x),
                               static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1)};
    const uint8_t rows[] = {static_cast<uint8_t>(y >> 8), static_cast<uint8_t>(y),
                            static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1)};

    // This is the loader/helloworld transaction contract: CASET, RASET,
    // RAMWR and every pixel remain in one CS-low interval.
    set_dc(false);
    select();
    const uint8_t column_command = 0x2a;
    spi_write_blocking(spi1, &column_command, 1);
    set_dc(true);
    spi_write_blocking(spi1, columns, sizeof(columns));
    set_dc(false);
    const uint8_t row_command = 0x2b;
    spi_write_blocking(spi1, &row_command, 1);
    set_dc(true);
    spi_write_blocking(spi1, rows, sizeof(rows));
    set_dc(false);
    const uint8_t memory_write = 0x2c;
    spi_write_blocking(spi1, &memory_write, 1);
    wait_idle();
    set_dc(true);
    g_window_open = true;
    return true;
}

void write_pixels_rgb565(const uint16_t* pixels, size_t count) {
    if (!g_window_open || pixels == nullptr || count == 0) return;
    size_t offset = 0;
    while (offset < count) {
        const size_t chunk = std::min(count - offset, kPixelsPerBuffer);
        for (size_t i = 0; i < chunk; ++i) {
            rgb565_to_rgb888(pixels[offset + i], &g_line[i * 3],
                             &g_line[i * 3 + 1], &g_line[i * 3 + 2]);
        }
        write_rgb888_bytes(g_line, chunk);
        offset += chunk;
    }
    wait_idle();
    deselect();
    g_window_open = false;
}

void write_solid_rgb565(uint16_t color, size_t count) {
    if (!g_window_open || count == 0) return;
    uint8_t red = 0;
    uint8_t green = 0;
    uint8_t blue = 0;
    rgb565_to_rgb888(color, &red, &green, &blue);
    for (size_t i = 0; i < kPixelsPerBuffer; ++i) {
        g_line[i * 3] = red;
        g_line[i * 3 + 1] = green;
        g_line[i * 3 + 2] = blue;
    }
    size_t remaining = count;
    while (remaining > 0) {
        const size_t chunk = std::min(remaining, kPixelsPerBuffer);
        write_rgb888_bytes(g_line, chunk);
        remaining -= chunk;
    }
    wait_idle();
    deselect();
    g_window_open = false;
}

bool readback_rgb888(int x, int y, int w, int h, ReadbackResult* result) {
    const size_t pixels = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (result == nullptr || w <= 0 || h <= 0 || pixels > kMaxReadbackPixels ||
        x < 0 || y < 0 || x + w > kWidth || y + h > kHeight || g_window_open) {
        return false;
    }

    const uint32_t actual_hz = spi_set_baudrate(spi1, kReadbackSpiHz);
    read_command(0x04, 1, result->id, sizeof(result->id));
    read_command(0x09, 1, result->status, sizeof(result->status));

    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {static_cast<uint8_t>(x >> 8), static_cast<uint8_t>(x),
                               static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1)};
    const uint8_t rows[] = {static_cast<uint8_t>(y >> 8), static_cast<uint8_t>(y),
                            static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1)};
    const uint8_t column_command = 0x2a;
    const uint8_t row_command = 0x2b;
    const uint8_t memory_read = 0x2e;
    set_dc(false);
    select();
    spi_write_blocking(spi1, &column_command, 1);
    set_dc(true);
    spi_write_blocking(spi1, columns, sizeof(columns));
    set_dc(false);
    spi_write_blocking(spi1, &row_command, 1);
    set_dc(true);
    spi_write_blocking(spi1, rows, sizeof(rows));
    set_dc(false);
    spi_write_blocking(spi1, &memory_read, 1);
    set_dc(true);
    spi_read_blocking(spi1, 0xff, &result->dummy, 1);
    spi_read_blocking(spi1, 0xff, result->raw, pixels * 3);
    wait_idle();
    deselect();
    spi_set_baudrate(spi1, board::kLcdSpiHz);
    std::printf("[PICOCALC][LCD][SPI] readback_hz=%lu\r\n",
                static_cast<unsigned long>(actual_hz));
    return true;
}

}  // namespace picocalc::vendor::lcd_hwspi_rgb888
