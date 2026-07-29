#include "picocalc/display.h"

#include <algorithm>
#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "picocalc/detail/lcd_protocol.h"
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

class PioTransport {
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
        write_bytes_raw(data, len);
    }

    void wait_idle() {
        picocalc::display::wait_idle();
    }
};

PioTransport g_transport;

void write_command(uint8_t command) {
    detail::lcd::write_command(g_transport, command);
}

void write_commandn(uint8_t command, const uint8_t* values, size_t len) {
    detail::lcd::write_command_data(g_transport, command, values, len);
}

void reset_panel() {
    printf("[PICOCALC][LCD] reset phase=assert_high delay_ms=10\n");
    gpio_put(board::kLcdReset, 1);
    sleep_ms(10);
    printf("[PICOCALC][LCD] reset phase=low delay_ms=10\n");
    gpio_put(board::kLcdReset, 0);
    sleep_ms(10);
    printf("[PICOCALC][LCD] reset phase=release delay_ms=200\n");
    gpio_put(board::kLcdReset, 1);
    sleep_ms(200);
}

void read_io_delay() {
    busy_wait_us_32(1);
}

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

void bitbang_write_commandn_held(uint8_t command,
                                 const uint8_t* data,
                                 size_t length) {
    set_dc(false);
    bitbang_write_byte(command);
    set_dc(true);
    while (length-- > 0) {
        bitbang_write_byte(*data++);
    }
}

void set_read_window_held(int x, int y, int w, int h) {
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
    bitbang_write_commandn_held(0x2a, columns, sizeof(columns));
    bitbang_write_commandn_held(0x2b, rows, sizeof(rows));
}

void read_command_bytes(uint8_t command,
                        int dummy_bytes,
                        uint8_t* output,
                        size_t output_length) {
    set_dc(false);
    bitbang_write_byte(command);
    set_dc(true);
    for (int i = 0; i < dummy_bytes; ++i) {
        (void)bitbang_read_byte_falling();
    }
    for (size_t i = 0; i < output_length; ++i) {
        output[i] = bitbang_read_byte_falling();
    }
}

void log_readback_bus_diagnostics() {
    const int idle_samples[] = {gpio_get(board::kLcdMiso) ? 1 : 0,
                                gpio_get(board::kLcdMiso) ? 1 : 0,
                                gpio_get(board::kLcdMiso) ? 1 : 0};
    printf("[PICOCALC][LCD][READ] bus mode=bitbang miso_idle=%d,%d,%d\n",
           idle_samples[0], idle_samples[1], idle_samples[2]);

    uint8_t id[3] = {};
    uint8_t status[4] = {};
    select();
    read_command_bytes(0x04, 1, id, sizeof(id));
    deselect();
    select();
    read_command_bytes(0x09, 1, status, sizeof(status));
    deselect();
    printf("[PICOCALC][LCD][READ] rddid=0x%02x%02x%02x rddst=0x%02x%02x%02x%02x\n",
           id[0], id[1], id[2], status[0], status[1], status[2], status[3]);
}

bool readback_pixels(int x, int y, int w, int h, uint16_t* output) {
    if (w <= 0 || h <= 0 || output == nullptr ||
        x < 0 || y < 0 || x + w > width || y + h > height) {
        return false;
    }

    wait_idle();
    set_bitbang_mode(true);
    log_readback_bus_diagnostics();
    select();
    set_read_window_held(x, y, w, h);
    set_dc(false);
    bitbang_write_byte(0x2e);  // RAMRD
    set_dc(true);
    const uint8_t dummy = bitbang_read_byte_falling();  // controller dummy byte
    uint8_t raw_red[16] = {};
    uint8_t raw_green[16] = {};
    uint8_t raw_blue[16] = {};

    const int pixel_count = w * h;
    for (int i = 0; i < pixel_count; ++i) {
        const uint8_t red = bitbang_read_byte_falling();
        const uint8_t green = bitbang_read_byte_falling();
        const uint8_t blue = bitbang_read_byte_falling();
        raw_red[i] = red;
        raw_green[i] = green;
        raw_blue[i] = blue;
        output[i] = static_cast<uint16_t>(
            ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3));
    }

    deselect();
    set_bitbang_mode(false);
    printf("[PICOCALC][LCD][READ] ramrd dummy=0x%02x pixels=%d\n",
           dummy, w * h);
    for (int i = 0; i < pixel_count; ++i) {
        printf("[PICOCALC][LCD][READ] pixel=%d raw=0x%02x%02x%02x value=0x%04x\n",
               i, raw_red[i], raw_green[i], raw_blue[i], output[i]);
    }
    return true;
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
    for (int i = 0; i < board::kLcdMaxPixelsPerCs; ++i) {
        const uint8_t red = static_cast<uint8_t>(((color >> 11) & 0x1f) << 3);
        const uint8_t green = static_cast<uint8_t>(((color >> 5) & 0x3f) << 2);
        const uint8_t blue = static_cast<uint8_t>((color & 0x1f) << 3);
        bytes[i * 3] = red;
        bytes[i * 3 + 1] = green;
        bytes[i * 3 + 2] = blue;
    }

    detail::lcd::for_each_chunk(
        count,
        static_cast<size_t>(board::kLcdMaxPixelsPerCs),
        [&](size_t pixels) {
            detail::lcd::write_data(g_transport, bytes, pixels * 3);
        });
}

}  // namespace

void init() {
    printf("[PICOCALC][LCD] gpio status=begin cs=%u dc=%u reset=%u ram_cs=%u sck=%u mosi=%u miso=%u\n",
           board::kLcdCs, board::kLcdDc, board::kLcdReset, board::kLcdRamCs,
           board::kLcdSck, board::kLcdMosi, board::kLcdMiso);
    gpio_init(board::kLcdCs);
    gpio_init(board::kLcdDc);
    gpio_init(board::kLcdReset);
    gpio_init(board::kLcdRamCs);
    gpio_init(board::kLcdMiso);
    gpio_set_dir(board::kLcdCs, GPIO_OUT);
    gpio_set_dir(board::kLcdDc, GPIO_OUT);
    gpio_set_dir(board::kLcdReset, GPIO_OUT);
    gpio_set_dir(board::kLcdRamCs, GPIO_OUT);
    gpio_set_dir(board::kLcdMiso, GPIO_IN);
    gpio_disable_pulls(board::kLcdMiso);
    gpio_put(board::kLcdCs, 1);
    gpio_put(board::kLcdDc, 1);
    gpio_put(board::kLcdReset, 1);
    gpio_put(board::kLcdRamCs, 1);
    printf("[PICOCALC][LCD] gpio status=ok cs=1 dc=1 reset=1 ram_cs=1\n");

    printf("[PICOCALC][LCD] pio status=begin divider=%.1f\n",
           static_cast<double>(board::kLcdPioClockDivider));
    g_offset = pio_add_program(g_pio, &lcd_spi_min_program);
    lcd_spi_min_program_init(g_pio,
                             g_sm,
                             g_offset,
                             board::kLcdMosi,
                             board::kLcdSck,
                             board::kLcdPioClockDivider);
    printf("[PICOCALC][LCD] pio status=ok\n");

    reset_panel();
    printf("[PICOCALC][LCD] controller phase=commands begin\n");

    detail::lcd::initialize_controller(
        g_transport,
        [](uint32_t milliseconds) {
            printf("[PICOCALC][LCD] controller phase=delay ms=%lu\n",
                   static_cast<unsigned long>(milliseconds));
            sleep_ms(milliseconds);
        },
        []() {
            printf("[PICOCALC][LCD] controller phase=clear begin\n");
            clear(0xf800);
            printf("[PICOCALC][LCD] controller phase=clear end\n");
        });
    printf("[PICOCALC][LCD] controller phase=commands end status=ok\n");
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
    detail::lcd::for_each_chunk(
        count,
        static_cast<size_t>(board::kLcdMaxPixelsPerCs),
        [&](size_t chunk) {
            for (size_t i = 0; i < chunk; ++i) {
                const uint16_t pixel = pixels[offset + i];
                bytes[i * 3] =
                    static_cast<uint8_t>(((pixel >> 11) & 0x1f) << 3);
                bytes[i * 3 + 1] =
                    static_cast<uint8_t>(((pixel >> 5) & 0x3f) << 2);
                bytes[i * 3 + 2] =
                    static_cast<uint8_t>((pixel & 0x1f) << 3);
            }
            detail::lcd::write_data(g_transport, bytes, chunk * 3);
            offset += chunk;
            g_window_pixels_remaining -= chunk;
        });
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    if (!clip_rect(&x, &y, &w, &h)) {
        return;
    }
    printf("[PICOCALC][LCD] fill phase=begin x=%d y=%d w=%d h=%d color=0x%04x\n",
           x, y, w, h, rgb565);
    set_window(x, y, w, h);
    const size_t count = static_cast<size_t>(w) * static_cast<size_t>(h);
    send_solid_pixels(rgb565, count);
    g_window_pixels_remaining = 0;
    printf("[PICOCALC][LCD] fill phase=end status=ok pixels=%lu\n",
           static_cast<unsigned long>(count));
}

void clear(uint16_t rgb565) {
    fill_rect(0, 0, width, height, rgb565);
}

void draw_test_pattern() {
    printf("[PICOCALC][LCD] test_pattern phase=begin\n");
    clear(0x0000);
    fill_rect(0, 0, width, 24, 0x07e0);
    fill_rect(0, height - 24, width, 24, 0x001f);
    fill_rect(16, 48, width - 32, height - 96, 0xffff);
    fill_rect(20, 52, width - 40, height - 104, 0x0000);
    fill_rect(32, 72, 80, 80, 0xf800);
    fill_rect(120, 72, 80, 80, 0x07e0);
    fill_rect(208, 72, 80, 80, 0x001f);
    printf("[PICOCALC][LCD] test_pattern phase=end status=ok\n");
}

bool verify_pixels(int x, int y, int w, int h,
                   const uint16_t* expected, size_t count) {
    if (expected == nullptr || count != static_cast<size_t>(w * h)) {
        printf("[PICOCALC][LCD][VERIFY] status=invalid\n");
        return false;
    }

    uint16_t actual[16] = {};
    if (count > 16 || !readback_pixels(x, y, w, h, actual)) {
        printf("[PICOCALC][LCD][VERIFY] status=readback_failed x=%d y=%d w=%d h=%d\n",
               x, y, w, h);
        return false;
    }

    size_t mismatches = 0;
    for (size_t i = 0; i < count; ++i) {
        if (actual[i] != expected[i]) {
            ++mismatches;
            printf("[PICOCALC][LCD][VERIFY] mismatch index=%lu expected=0x%04x actual=0x%04x\n",
                   static_cast<unsigned long>(i), expected[i], actual[i]);
        }
    }
    printf("[PICOCALC][LCD][VERIFY] status=%s pixels=%lu mismatches=%lu\n",
           mismatches == 0 ? "pass" : "fail",
           static_cast<unsigned long>(count),
           static_cast<unsigned long>(mismatches));
    return mismatches == 0;
}

}  // namespace picocalc::display
