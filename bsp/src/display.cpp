#include "picocalc/display.h"

#include <algorithm>
#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "picocalc/detail/lcd_protocol.h"

namespace picocalc::display {
namespace {

size_t g_window_pixels_remaining = 0;
constexpr size_t kMaxReadbackPixels = 16;

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

uint16_t rgb888_to_rgb565(const uint8_t* rgb888) {
    return static_cast<uint16_t>(
        (static_cast<uint16_t>(rgb888[0] >> 3) << 11) |
        (static_cast<uint16_t>(rgb888[1] >> 2) << 5) |
        static_cast<uint16_t>(rgb888[2] >> 3));
}

void read_io_delay() {
    busy_wait_us_32(1);
}

void set_bitbang_mode(bool enabled) {
    if (enabled) {
        spi_deinit(spi1);
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

    spi_init(spi1, board::kLcdSpiHz);
    gpio_set_function(board::kLcdSck, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMosi, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMiso, GPIO_FUNC_SPI);
    gpio_set_input_hysteresis_enabled(board::kLcdMiso, true);
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
        if (gpio_get(board::kLcdMiso)) {
            value |= static_cast<uint8_t>(1u << bit);
        }
        gpio_put(board::kLcdSck, 1);
        read_io_delay();
    }
    gpio_put(board::kLcdSck, 0);
    return value;
}

void bitbang_write_command_data(uint8_t command,
                                const uint8_t* data,
                                size_t length) {
    set_dc(false);
    bitbang_write_byte(command);
    if (data == nullptr || length == 0) {
        return;
    }
    set_dc(true);
    while (length-- > 0) {
        bitbang_write_byte(*data++);
    }
}

void bitbang_set_read_window(int x, int y, int w, int h) {
    const int x1 = x + w - 1;
    const int y1 = y + h - 1;
    const uint8_t columns[] = {
        static_cast<uint8_t>(x >> 8), static_cast<uint8_t>(x),
        static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1),
    };
    const uint8_t rows[] = {
        static_cast<uint8_t>(y >> 8), static_cast<uint8_t>(y),
        static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1),
    };
    bitbang_write_command_data(0x2a, columns, sizeof(columns));
    bitbang_write_command_data(0x2b, rows, sizeof(rows));
}

void bitbang_read_command(uint8_t command,
                          size_t dummy_bytes,
                          uint8_t* output,
                          size_t output_length) {
    select();
    set_dc(false);
    bitbang_write_byte(command);
    set_dc(true);
    while (dummy_bytes-- > 0) {
        (void)bitbang_read_byte_falling();
    }
    while (output_length-- > 0) {
        *output++ = bitbang_read_byte_falling();
    }
    deselect();
}

bool readback_pixels(int x, int y, int w, int h, uint16_t* output) {
    const size_t pixel_count = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (w <= 0 || h <= 0 || output == nullptr || pixel_count > kMaxReadbackPixels ||
        x < 0 || y < 0 || x + w > width || y + h > height) {
        return false;
    }

    set_bitbang_mode(true);
    const int idle_samples[] = {gpio_get(board::kLcdMiso) ? 1 : 0,
                                gpio_get(board::kLcdMiso) ? 1 : 0,
                                gpio_get(board::kLcdMiso) ? 1 : 0};
    printf("[PICOCALC][LCD][READ] transport=bitbang_sio read_hz=~500k "
           "miso_idle=%d,%d,%d\n",
           idle_samples[0], idle_samples[1], idle_samples[2]);

    uint8_t id[3] = {};
    uint8_t status[4] = {};
    bitbang_read_command(0x04, 1, id, sizeof(id));
    bitbang_read_command(0x09, 1, status, sizeof(status));
    printf("[PICOCALC][LCD][READ] rddid=0x%02x%02x%02x "
           "rddst=0x%02x%02x%02x%02x\n",
           id[0], id[1], id[2], status[0], status[1], status[2], status[3]);

    uint8_t raw[kMaxReadbackPixels * 3] = {};
    select();
    bitbang_set_read_window(x, y, w, h);
    set_dc(false);
    bitbang_write_byte(0x2e);
    set_dc(true);
    const uint8_t dummy = bitbang_read_byte_falling();
    for (size_t i = 0; i < pixel_count * 3; ++i) {
        raw[i] = bitbang_read_byte_falling();
    }
    deselect();
    set_bitbang_mode(false);
    printf("[PICOCALC][LCD][READ] ramrd dummy=0x%02x pixels=%lu format=rgb888\n",
           dummy, static_cast<unsigned long>(pixel_count));
    for (size_t i = 0; i < pixel_count; ++i) {
        output[i] = rgb888_to_rgb565(&raw[i * 3]);
        printf("[PICOCALC][LCD][READ] pixel=%lu raw=0x%02x%02x%02x value=0x%04x\n",
               static_cast<unsigned long>(i), raw[i * 3], raw[i * 3 + 1],
               raw[i * 3 + 2], output[i]);
    }
    return true;
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
    gpio_init(board::kLcdSck);
    gpio_init(board::kLcdMosi);
    gpio_init(board::kLcdMiso);
    gpio_init(board::kLcdCs);
    gpio_init(board::kLcdDc);
    gpio_init(board::kLcdReset);
    gpio_set_dir(board::kLcdCs, GPIO_OUT);
    gpio_set_dir(board::kLcdDc, GPIO_OUT);
    gpio_set_dir(board::kLcdReset, GPIO_OUT);
    gpio_set_dir(board::kLcdSck, GPIO_OUT);
    gpio_set_dir(board::kLcdMosi, GPIO_OUT);
    gpio_disable_pulls(board::kLcdMiso);
    gpio_put(board::kLcdCs, 1);
    gpio_put(board::kLcdDc, 1);
    gpio_put(board::kLcdReset, 1);

    gpio_set_drive_strength(board::kLcdCs, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_drive_strength(board::kLcdDc, GPIO_DRIVE_STRENGTH_12MA);
    gpio_set_drive_strength(board::kLcdReset, GPIO_DRIVE_STRENGTH_12MA);
    spi_init(spi1, board::kLcdSpiHz);
    gpio_set_function(board::kLcdSck, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMosi, GPIO_FUNC_SPI);
    gpio_set_function(board::kLcdMiso, GPIO_FUNC_SPI);
    gpio_set_input_hysteresis_enabled(board::kLcdMiso, true);

    reset_panel();

    detail::lcd::initialize_controller(
        g_transport, [](uint32_t milliseconds) { sleep_ms(milliseconds); });
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
    detail::lcd::write_command_data(g_transport, 0x2a, columns, sizeof(columns));
    detail::lcd::write_command_data(g_transport, 0x2b, rows, sizeof(rows));
    detail::lcd::write_command(g_transport, 0x2c);
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
    send_solid_pixels(rgb565, static_cast<size_t>(w) * static_cast<size_t>(h));
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

PixelVerifyResult verify_pixels(int x, int y, int w, int h,
                                const uint16_t* expected, size_t count) {
    const size_t pixel_count = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (expected == nullptr || w <= 0 || h <= 0 || count != pixel_count ||
        count > kMaxReadbackPixels) {
        printf("[PICOCALC][LCD][VERIFY] status=invalid x=%d y=%d w=%d h=%d count=%lu\n",
               x, y, w, h, static_cast<unsigned long>(count));
        return {false, 0, 0};
    }

    uint16_t actual[kMaxReadbackPixels] = {};
    if (!readback_pixels(x, y, w, h, actual)) {
        printf("[PICOCALC][LCD][VERIFY] status=readback_failed x=%d y=%d w=%d h=%d\n",
               x, y, w, h);
        return {false, pixel_count, 0};
    }

    size_t mismatches = 0;
    for (size_t i = 0; i < pixel_count; ++i) {
        if (actual[i] != expected[i]) {
            ++mismatches;
            printf("[PICOCALC][LCD][VERIFY] mismatch index=%lu expected=0x%04x "
                   "actual=0x%04x\n",
                   static_cast<unsigned long>(i), expected[i], actual[i]);
        }
    }
    printf("[PICOCALC][LCD][VERIFY] status=%s pixels=%lu mismatches=%lu\n",
           mismatches == 0 ? "pass" : "fail",
           static_cast<unsigned long>(pixel_count),
           static_cast<unsigned long>(mismatches));
    return {true, pixel_count, mismatches};
}

}  // namespace picocalc::display
