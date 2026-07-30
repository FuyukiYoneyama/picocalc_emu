#include "lcd_rgb565_pio.h"

#include <cstdio>
#include <cstring>

#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "lcd_spi_min.pio.h"

namespace {
constexpr uint kPinSck = 10;
constexpr uint kPinMosi = 11;
constexpr uint kPinMiso = 12;
constexpr uint kPinCs = 13;
constexpr uint kPinDc = 14;
constexpr uint kPinRst = 15;
constexpr uint kPinRamCs = 21;
constexpr int kWidth = 320;
constexpr int kHeight = 320;
constexpr int kMaxPixels = 320 * 16;
constexpr float kPioClkDiv = 2.0f;

PIO g_pio = pio0;
uint g_sm = 0;
uint g_offset = 0;
bool g_ready = false;
bool g_dma_enabled = false;
int g_dma_chan = -1;
bool g_dma_active = false;
dma_channel_config g_dma_cfg;
uint8_t g_dma_buf[2][kMaxPixels * 2];
int g_dma_buf_idx = 0;
int g_window_pixels = 0;

void select() { gpio_put(kPinCs, 0); }
void deselect() { gpio_put(kPinCs, 1); }
void set_dc(bool data) { gpio_put(kPinDc, data ? 1 : 0); }

void wait_idle() {
    if (!g_ready) return;
    lcd_spi_min_wait_idle(g_pio, g_sm);
}

void write_bytes_blocking_raw(const uint8_t* data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        lcd_spi_min_put(g_pio, g_sm, data[i]);
    }
}

void write_command(uint8_t cmd) {
    lcd_rgb565_pio_wait_dma();
    select();
    set_dc(false);
    write_bytes_blocking_raw(&cmd, 1);
    wait_idle();
    deselect();
}

void write_data(const uint8_t* data, size_t len) {
    if (len == 0) return;
    lcd_rgb565_pio_wait_dma();
    select();
    set_dc(true);
    write_bytes_blocking_raw(data, len);
    wait_idle();
    deselect();
}

void write_command1(uint8_t cmd, uint8_t value) {
    write_command(cmd);
    write_data(&value, 1);
}

void write_commandn(uint8_t cmd, const uint8_t* data, size_t len) {
    write_command(cmd);
    write_data(data, len);
}

void reset_panel() {
    gpio_put(kPinRst, 1);
    sleep_ms(1);
    gpio_put(kPinRst, 0);
    sleep_ms(10);
    gpio_put(kPinRst, 1);
    sleep_ms(10);
}

void init_gpio_pio() {
    gpio_init(kPinCs);
    gpio_init(kPinDc);
    gpio_init(kPinRst);
    gpio_init(kPinRamCs);
    gpio_init(kPinMiso);
    gpio_set_dir(kPinCs, GPIO_OUT);
    gpio_set_dir(kPinDc, GPIO_OUT);
    gpio_set_dir(kPinRst, GPIO_OUT);
    gpio_set_dir(kPinRamCs, GPIO_OUT);
    gpio_set_dir(kPinMiso, GPIO_IN);
    gpio_disable_pulls(kPinMiso);
    gpio_put(kPinCs, 1);
    gpio_put(kPinDc, 1);
    gpio_put(kPinRst, 1);
    gpio_put(kPinRamCs, 1);

    g_offset = pio_add_program(g_pio, &lcd_spi_min_program);
    lcd_spi_min_program_init(g_pio, g_sm, g_offset, kPinMosi, kPinSck, kPioClkDiv);
    g_ready = true;
}

void init_dma_if_needed(bool enable_dma) {
    g_dma_enabled = enable_dma;
    if (!enable_dma) return;
    g_dma_chan = dma_claim_unused_channel(true);
    g_dma_cfg = dma_channel_get_default_config(static_cast<uint>(g_dma_chan));
    channel_config_set_transfer_data_size(&g_dma_cfg, DMA_SIZE_8);
    channel_config_set_read_increment(&g_dma_cfg, true);
    channel_config_set_write_increment(&g_dma_cfg, false);
    channel_config_set_dreq(&g_dma_cfg, pio_get_dreq(g_pio, g_sm, true));
}

void init_lcd_nesco_rgb565() {
    reset_panel();

    static const uint8_t b9[] = {0x02, 0xe0};
    static const uint8_t c0[] = {0x80, 0x06};
    static const uint8_t e8[] = {0x40, 0x8a, 0x00, 0x00, 0x29, 0x19, 0xaa, 0x33};
    static const uint8_t e0[] = {0xf0, 0x06, 0x0f, 0x05, 0x04, 0x20, 0x37, 0x33,
                                 0x4c, 0x37, 0x13, 0x14, 0x2b, 0x31};
    static const uint8_t e1[] = {0xf0, 0x11, 0x1b, 0x11, 0x0f, 0x0a, 0x37, 0x43,
                                 0x4c, 0x37, 0x13, 0x13, 0x2c, 0x32};

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

    std::printf("LCD NESco-style init sequence sent 0x3A=0x65 RGB565\r\n");
    write_command(0x11);
    sleep_ms(120);
    write_command(0x21);
    lcd_rgb565_pio_fill_rect_blocking(0, 0, kWidth, kHeight, 0x0000);
    write_command(0x29);
    sleep_ms(120);
}

}  // namespace

void lcd_rgb565_pio_wait_dma(void) {
    if (!g_dma_active) return;
    dma_channel_wait_for_finish_blocking(static_cast<uint>(g_dma_chan));
    wait_idle();
    deselect();
    g_dma_active = false;
}

void lcd_rgb565_pio_init(bool enable_dma) {
    init_gpio_pio();
    init_dma_if_needed(enable_dma);
    init_lcd_nesco_rgb565();
}

void lcd_rgb565_pio_set_window(int x, int y, int w, int h) {
    if (w <= 0 || h <= 0) {
        g_window_pixels = 0;
        return;
    }
    int x0 = x < 0 ? 0 : x;
    int y0 = y < 0 ? 0 : y;
    int x1 = x + w - 1;
    int y1 = y + h - 1;
    if (x1 >= kWidth) x1 = kWidth - 1;
    if (y1 >= kHeight) y1 = kHeight - 1;
    if (x1 < x0 || y1 < y0) {
        g_window_pixels = 0;
        return;
    }
    g_window_pixels = (x1 - x0 + 1) * (y1 - y0 + 1);
    const uint8_t col[] = {static_cast<uint8_t>(x0 >> 8), static_cast<uint8_t>(x0),
                           static_cast<uint8_t>(x1 >> 8), static_cast<uint8_t>(x1)};
    const uint8_t row[] = {static_cast<uint8_t>(y0 >> 8), static_cast<uint8_t>(y0),
                           static_cast<uint8_t>(y1 >> 8), static_cast<uint8_t>(y1)};
    write_commandn(0x2a, col, sizeof(col));
    write_commandn(0x2b, row, sizeof(row));
    write_command(0x2c);
}

void lcd_rgb565_pio_write_blocking(const uint16_t* pixels, int n_pixels) {
    if (!pixels || n_pixels <= 0 || g_window_pixels <= 0) return;
    if (n_pixels > g_window_pixels) n_pixels = g_window_pixels;
    select();
    set_dc(true);
    for (int i = 0; i < n_pixels; ++i) {
        const uint8_t bytes[] = {static_cast<uint8_t>(pixels[i] >> 8),
                                 static_cast<uint8_t>(pixels[i] & 0xff)};
        write_bytes_blocking_raw(bytes, sizeof(bytes));
    }
    wait_idle();
    deselect();
    g_window_pixels -= n_pixels;
}

void lcd_rgb565_pio_write_dma(const uint16_t* pixels, int n_pixels) {
    if (!g_dma_enabled || g_dma_chan < 0) {
        lcd_rgb565_pio_write_blocking(pixels, n_pixels);
        return;
    }
    if (!pixels || n_pixels <= 0 || g_window_pixels <= 0) return;
    if (n_pixels > g_window_pixels) n_pixels = g_window_pixels;

    int remaining = n_pixels;
    const uint16_t* src = pixels;
    while (remaining > 0) {
        int chunk = remaining;
        if (chunk > kMaxPixels) chunk = kMaxPixels;
        lcd_rgb565_pio_wait_dma();
        uint8_t* dst = g_dma_buf[g_dma_buf_idx];
        for (int i = 0; i < chunk; ++i) {
            dst[i * 2 + 0] = static_cast<uint8_t>(src[i] >> 8);
            dst[i * 2 + 1] = static_cast<uint8_t>(src[i] & 0xff);
        }
        select();
        set_dc(true);
        dma_channel_configure(static_cast<uint>(g_dma_chan),
                              &g_dma_cfg,
                              &g_pio->txf[g_sm],
                              dst,
                              static_cast<size_t>(chunk * 2),
                              true);
        g_dma_active = true;
        g_window_pixels -= chunk;
        g_dma_buf_idx = 1 - g_dma_buf_idx;
        src += chunk;
        remaining -= chunk;
    }
}

void lcd_rgb565_pio_fill_rect_blocking(int x, int y, int w, int h, uint16_t color) {
    if (w <= 0 || h <= 0) return;
    lcd_rgb565_pio_set_window(x, y, w, h);
    select();
    set_dc(true);
    const uint8_t px[] = {static_cast<uint8_t>(color >> 8), static_cast<uint8_t>(color & 0xff)};
    for (int row = 0; row < h; ++row) {
        for (int col = 0; col < w; ++col) {
            write_bytes_blocking_raw(px, sizeof(px));
        }
    }
    wait_idle();
    deselect();
    g_window_pixels = 0;
}

void lcd_rgb565_pio_fill_rect_dma(int x, int y, int w, int h, uint16_t color) {
    if (w <= 0 || h <= 0) return;
    static uint16_t line[kWidth];
    for (int i = 0; i < w && i < kWidth; ++i) line[i] = color;
    lcd_rgb565_pio_set_window(x, y, w, h);
    for (int row = 0; row < h; ++row) {
        lcd_rgb565_pio_write_dma(line, w);
        lcd_rgb565_pio_wait_dma();
    }
}
