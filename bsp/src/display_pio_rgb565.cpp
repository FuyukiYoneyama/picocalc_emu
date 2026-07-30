#include "picocalc/display.h"

#include <algorithm>
#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"
#include "lcd_spi_min.pio.h"

#ifndef PICOCALC_LCD_PIO_BRINGUP
#define PICOCALC_LCD_PIO_BRINGUP 0
#endif

#if PICOCALC_LCD_PIO_BRINGUP
#include "hardware/structs/iobank0.h"
#include "hardware/structs/padsbank0.h"
#endif

namespace picocalc::display {
namespace {

// This is the blocking PIO/RGB565 path used by the proven life/pico_rescue
// projects. It remains independent from the hardware-SPI/RGB888 transport.
//
// Electrical contract. Each line is taken from a project that displayed on real
// hardware; do not mix in a different value without a new hardware record.
//   * sysclk 250 MHz and clkdiv 4.0 -> 31.25 MHz SCK (life).
//   * reset: High 10 ms -> Low 10 ms -> High 200 ms, then send commands
//     (life, Picocalc_Clock, Picocalc_ment, Picocalc_BVWCVolleyball).
//   * CASET/RASET/RAMWR once per window, window limited to 160x160, and RAMWR
//     data sent in 160 pixel (320 byte) units with CS released between units
//     (pico_skyace, general/lcd main_pio_blocking_rgb565). general/01_DISPLAY_LCD.md
//     section 8.1 records that holding CS across a long burst corrupts the panel
//     while the same window size with short CS units works.
constexpr float kPioClockDivider = 4.0f;
constexpr uint32_t kResetHighBeforeMs = 10;
constexpr uint32_t kResetLowMs = 10;
constexpr uint32_t kResetSettleMs = 200;
constexpr uint32_t kWriteToReadRecoveryMs = 200;
constexpr size_t kPixelsPerCs = static_cast<size_t>(board::kLcdMaxPixelsPerCs);
constexpr int kWindowTileSide = board::kLcdMaxPixelsPerCs;
constexpr size_t kChunkBufferBytes = kPixelsPerCs * 2;
constexpr size_t kMaxReadbackPixels = 16;
PIO g_pio = pio0;
uint g_sm = 0;
uint g_program_offset = 0;
size_t g_window_pixels_remaining = 0;
uint8_t g_chunk_buffer[kChunkBufferBytes] = {};

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
    // life/Clock/ment/BVWCVolleyball all hold reset high 10 ms, low 10 ms, then
    // wait 200 ms before the first command. A 10 ms settle is not enough for this
    // panel to accept the initialization sequence.
    gpio_put(board::kLcdReset, 1);
    sleep_ms(kResetHighBeforeMs);
    gpio_put(board::kLcdReset, 0);
    sleep_ms(kResetLowMs);
    gpio_put(board::kLcdReset, 1);
    sleep_ms(kResetSettleMs);
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

// One RAMWR data unit: assert CS, stream at most 160 pixels, wait for the PIO to
// drain, release CS. The GRAM address pointer keeps counting across units, so the
// window commands are not resent here.
void send_pixel_chunk(const uint8_t* bytes, size_t pixels) {
    select();
    set_dc(true);
    write_bytes(bytes, pixels * 2);
    wait_idle();
    deselect();
    g_window_pixels_remaining =
        g_window_pixels_remaining > pixels ? g_window_pixels_remaining - pixels : 0;
}

void send_solid_pixels(uint16_t color, size_t count) {
    const uint8_t hi = static_cast<uint8_t>(color >> 8);
    const uint8_t lo = static_cast<uint8_t>(color & 0xff);
    for (size_t i = 0; i < kPixelsPerCs; ++i) {
        g_chunk_buffer[i * 2] = hi;
        g_chunk_buffer[i * 2 + 1] = lo;
    }
    while (count > 0) {
        const size_t chunk = std::min(count, kPixelsPerCs);
        send_pixel_chunk(g_chunk_buffer, chunk);
        count -= chunk;
    }
}

void read_io_delay() { busy_wait_us_32(1); }

void set_bitbang_mode(bool enabled) {
    if (enabled) {
        // Callers drain the shifter through wait_for_write_to_read_recovery()
        // before switching pin ownership.
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
    // Disabling the state machine keeps its FIFO, OSR and shift counter. Restart
    // the byte engine from a known state so a readback cannot leave later writes
    // shifted by a partial byte.
    pio_sm_clear_fifos(g_pio, g_sm);
    pio_sm_restart(g_pio, g_sm);
    pio_sm_clkdiv_restart(g_pio, g_sm);
    pio_sm_exec(g_pio, g_sm, pio_encode_jmp(g_program_offset));
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

void wait_for_write_to_read_recovery() {
    // PIO idle only proves that the RP2040 has shifted the last byte. Keep CS
    // inactive and give the panel time to finish accepting the GRAM write
    // before changing SCK/MOSI/MISO ownership for RAMRD.
    wait_idle();
    deselect();
    printf("[PICOCALC][LCD][RECOVERY] phase=write_to_read wait_ms=%lu\n",
           static_cast<unsigned long>(kWriteToReadRecoveryMs));
    sleep_ms(kWriteToReadRecoveryMs);
}

bool readback_pixels(int x, int y, int w, int h, uint16_t* output) {
    const size_t pixel_count = static_cast<size_t>(w) * static_cast<size_t>(h);
    if (output == nullptr || w <= 0 || h <= 0 || pixel_count > kMaxReadbackPixels ||
        x < 0 || y < 0 || x + w > width || y + h > height) return false;
    wait_for_write_to_read_recovery();
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

#if PICOCALC_LCD_PIO_BRINGUP
// Bring-up build only. These stages exist to separate three questions that the
// normal smoke test cannot separate on a panel whose RAMRD returns the retained
// image: does PIO0 drive SCK/MOSI at all, does the panel accept GRAM writes over
// bit-banged SIO, and does it accept them over PIO at 15.6 MHz and at 31.25 MHz.
// Each stage paints one 160x160 quadrant, so the screen alone reports the result.
constexpr float kBringupSlowClockDivider = 12500.0f;  // 250 MHz -> ~10 kHz SCK
constexpr float kBringupInSpecClockDivider = 8.0f;    // 250 MHz -> 15.625 MHz SCK

void bringup_report_registers(const char* phase) {
    printf("[PICOCALC][LCD][BRINGUP] phase=%s sck_funcsel=%lu mosi_funcsel=%lu "
           "sck_pad=0x%08lx mosi_pad=0x%08lx\n",
           phase,
           static_cast<unsigned long>(iobank0_hw->io[board::kLcdSck].ctrl &
                                      IO_BANK0_GPIO0_CTRL_FUNCSEL_BITS),
           static_cast<unsigned long>(iobank0_hw->io[board::kLcdMosi].ctrl &
                                      IO_BANK0_GPIO0_CTRL_FUNCSEL_BITS),
           static_cast<unsigned long>(padsbank0_hw->io[board::kLcdSck]),
           static_cast<unsigned long>(padsbank0_hw->io[board::kLcdMosi]));
    printf("[PICOCALC][LCD][BRINGUP] phase=%s pio_ctrl=0x%08lx flevel=0x%08lx "
           "fdebug=0x%08lx pinctrl=0x%08lx shiftctrl=0x%08lx execctrl=0x%08lx "
           "clkdiv=0x%08lx addr=%lu offset=%lu\n",
           phase,
           static_cast<unsigned long>(g_pio->ctrl),
           static_cast<unsigned long>(g_pio->flevel),
           static_cast<unsigned long>(g_pio->fdebug),
           static_cast<unsigned long>(g_pio->sm[g_sm].pinctrl),
           static_cast<unsigned long>(g_pio->sm[g_sm].shiftctrl),
           static_cast<unsigned long>(g_pio->sm[g_sm].execctrl),
           static_cast<unsigned long>(g_pio->sm[g_sm].clkdiv),
           static_cast<unsigned long>(g_pio->sm[g_sm].addr),
           static_cast<unsigned long>(g_program_offset));
}

// Stage 0: does PIO0 actually move SCK/MOSI? Runs with CS inactive so the panel
// ignores the traffic. The state machine is slowed to ~10 kHz so a CPU polling
// loop can count pad transitions; one byte must produce 16 SCK edges.
void bringup_check_pio_pins() {
    bringup_report_registers("pins_before");
    pio_sm_set_clkdiv(g_pio, g_sm, kBringupSlowClockDivider);
    pio_sm_clkdiv_restart(g_pio, g_sm);
    deselect();
    set_dc(true);
    unsigned sck_edges = 0;
    unsigned mosi_edges = 0;
    int last_sck = gpio_get(board::kLcdSck) ? 1 : 0;
    int last_mosi = gpio_get(board::kLcdMosi) ? 1 : 0;
    const int idle_sck = last_sck;
    const uint8_t probe = 0xa5;
    lcd_spi_min_put(g_pio, g_sm, probe);
    const absolute_time_t deadline = make_timeout_time_ms(50);
    while (!time_reached(deadline)) {
        const int sck = gpio_get(board::kLcdSck) ? 1 : 0;
        const int mosi = gpio_get(board::kLcdMosi) ? 1 : 0;
        if (sck != last_sck) { ++sck_edges; last_sck = sck; }
        if (mosi != last_mosi) { ++mosi_edges; last_mosi = mosi; }
    }
    printf("[PICOCALC][LCD][BRINGUP] stage=0 name=pio_pin_edges probe=0x%02x "
           "idle_sck=%d sck_edges=%u mosi_edges=%u expect_sck_edges=16 verdict=%s\n",
           probe, idle_sck, sck_edges, mosi_edges,
           sck_edges >= 16 ? "pio_drives_pins" : "pio_output_missing");
    bringup_report_registers("pins_after");
    pio_sm_set_clkdiv(g_pio, g_sm, kPioClockDivider);
    pio_sm_clkdiv_restart(g_pio, g_sm);
}

void bitbang_write_window(int x, int y, int w, int h) {
    bitbang_set_read_window(x, y, w, h);
    set_dc(false);
    bitbang_write_byte(0x2c);
    set_dc(true);
}

// Stage 2: fill through the bit-banged SIO path, which is the same path that
// already reaches this panel during RAMRD.
void bringup_fill_rect_sio(int x, int y, int w, int h, uint16_t color) {
    const uint8_t bytes[] = {static_cast<uint8_t>(color >> 8),
                             static_cast<uint8_t>(color & 0xff)};
    wait_idle();
    deselect();
    set_bitbang_mode(true);
    select();
    bitbang_write_window(x, y, w, h);
    for (int pixel = 0; pixel < w * h; ++pixel) {
        write_bytes_sio(bytes, sizeof(bytes));
    }
    deselect();
    set_bitbang_mode(false);
}

void bringup_fill_rect_pio(int x, int y, int w, int h, uint16_t color,
                           float clock_divider) {
    pio_sm_set_clkdiv(g_pio, g_sm, clock_divider);
    pio_sm_clkdiv_restart(g_pio, g_sm);
    for (int tile_y = y; tile_y < y + h; tile_y += kWindowTileSide) {
        const int tile_h = std::min(kWindowTileSide, y + h - tile_y);
        for (int tile_x = x; tile_x < x + w; tile_x += kWindowTileSide) {
            const int tile_w = std::min(kWindowTileSide, x + w - tile_x);
            set_window_unclipped(tile_x, tile_y, tile_w, tile_h);
            send_solid_pixels(color,
                              static_cast<size_t>(tile_w) * static_cast<size_t>(tile_h));
        }
    }
    pio_sm_set_clkdiv(g_pio, g_sm, kPioClockDivider);
    pio_sm_clkdiv_restart(g_pio, g_sm);
}

void bringup_report_stage(int stage, const char* name, const char* transport,
                          double mhz, int x, int y, uint16_t expected) {
    uint16_t actual[kMaxReadbackPixels] = {};
    const bool read_ok = readback_pixels(x, y, 1, 1, actual);
    // RAMRD on this panel has never returned trustworthy data, so the quadrant
    // colours on screen are the verdict and readback_match is only a hint.
    printf("[PICOCALC][LCD][BRINGUP] stage=%d name=%s transport=%s sck_mhz=%.2f "
           "probe=%d,%d expected=0x%04x actual=0x%04x read=%s readback_match=%s "
           "judge=screen_quadrant\n",
           stage, name, transport, mhz, x, y, expected, actual[0],
           read_ok ? "ok" : "invalid",
           (read_ok && actual[0] == expected) ? "yes" : "no");
}

void run_bringup_stages() {
    printf("[PICOCALC][LCD][BRINGUP] mode=quadrant_stages "
           "layout=tl:sio_red,tr:pio_15mhz_green,bl:pio_31mhz_blue\n");
    bringup_fill_rect_sio(0, 0, kWindowTileSide, kWindowTileSide, 0xf800);
    bringup_report_stage(2, "sio_bitbang_fill", "bitbang_sio", 0.5, 8, 8, 0xf800);
    bringup_fill_rect_pio(kWindowTileSide, 0, kWindowTileSide, kWindowTileSide,
                          0x07e0, kBringupInSpecClockDivider);
    bringup_report_stage(3, "pio_fill_in_spec", "pio0_blocking", 15.625,
                         kWindowTileSide + 8, 8, 0x07e0);
    bringup_fill_rect_pio(0, kWindowTileSide, kWindowTileSide, kWindowTileSide,
                          0x001f, kPioClockDivider);
    bringup_report_stage(4, "pio_fill_current", "pio0_blocking", 31.25, 8,
                         kWindowTileSide + 8, 0x001f);
    printf("[PICOCALC][LCD][BRINGUP] stage=end action=halt "
           "read_screen=tl_red_means_sio_ok,tr_green_means_pio_15mhz_ok,"
           "bl_blue_means_pio_31mhz_ok\n");
    while (true) {
        tight_loop_contents();
    }
}
#endif  // PICOCALC_LCD_PIO_BRINGUP

}  // namespace

void init() {
    // Match pico_rescue: SCK/MOSI are initialized by the PIO helper, while
    // the real PSRAM CS (GP20) is held inactive. GP21 is PSRAM SCK, not CS.
    gpio_init(board::kLcdCs); gpio_init(board::kLcdDc); gpio_init(board::kLcdReset);
    gpio_init(board::kPsramCs); gpio_init(board::kLcdMiso);
    gpio_set_dir(board::kLcdCs, GPIO_OUT); gpio_set_dir(board::kLcdDc, GPIO_OUT);
    gpio_set_dir(board::kLcdReset, GPIO_OUT); gpio_set_dir(board::kPsramCs, GPIO_OUT);
    gpio_set_dir(board::kLcdMiso, GPIO_IN);
    gpio_disable_pulls(board::kLcdMiso);
    gpio_put(board::kLcdCs, 1); gpio_put(board::kLcdDc, 1);
    gpio_put(board::kLcdReset, 1); gpio_put(board::kPsramCs, 1);
    g_program_offset = pio_add_program(g_pio, &lcd_spi_min_program);
    lcd_spi_min_program_init(g_pio, g_sm, g_program_offset,
                             board::kLcdMosi, board::kLcdSck,
                             kPioClockDivider);
#if PICOCALC_LCD_PIO_BRINGUP
    bringup_check_pio_pins();
#endif
    initialize_controller();
    printf("[PICOCALC][LCD][PIO] transport=pio0_blocking sm=0 clkdiv=%.2f "
           "hz=31250000 colmod=0x65 wire=rgb565 reference=life-pico_rescue "
           "reset_ms=%lu/%lu/%lu window_max=%dx%d cs=released_per_%lu_pixels\n",
           static_cast<double>(kPioClockDivider),
           static_cast<unsigned long>(kResetHighBeforeMs),
           static_cast<unsigned long>(kResetLowMs),
           static_cast<unsigned long>(kResetSettleMs),
           kWindowTileSide, kWindowTileSide,
           static_cast<unsigned long>(kPixelsPerCs));
#if PICOCALC_LCD_PIO_BRINGUP
    run_bringup_stages();
#endif
}

void set_window(int x, int y, int w, int h) {
    if (!clip_rect(&x, &y, &w, &h)) { g_window_pixels_remaining = 0; return; }
    set_window_unclipped(x, y, w, h);
}

void write_pixels(const uint16_t* pixels, size_t count) {
    if (pixels == nullptr || count == 0 || g_window_pixels_remaining == 0) return;
    count = std::min(count, g_window_pixels_remaining);
    size_t offset = 0;
    while (offset < count) {
        const size_t chunk = std::min(count - offset, kPixelsPerCs);
        for (size_t i = 0; i < chunk; ++i) {
            const uint16_t pixel = pixels[offset + i];
            g_chunk_buffer[i * 2] = static_cast<uint8_t>(pixel >> 8);
            g_chunk_buffer[i * 2 + 1] = static_cast<uint8_t>(pixel & 0xff);
        }
        send_pixel_chunk(g_chunk_buffer, chunk);
        offset += chunk;
    }
}

void fill_rect(int x, int y, int w, int h, uint16_t rgb565) {
    if (!clip_rect(&x, &y, &w, &h)) return;
    // One window per 160x160 tile, exactly like the quadrant pattern of
    // main_pio_blocking_rgb565.cpp / pico_skyace.
    for (int tile_y = y; tile_y < y + h; tile_y += kWindowTileSide) {
        const int tile_h = std::min(kWindowTileSide, y + h - tile_y);
        for (int tile_x = x; tile_x < x + w; tile_x += kWindowTileSide) {
            const int tile_w = std::min(kWindowTileSide, x + w - tile_x);
            set_window_unclipped(tile_x, tile_y, tile_w, tile_h);
            send_solid_pixels(
                rgb565, static_cast<size_t>(tile_w) * static_cast<size_t>(tile_h));
        }
    }
    g_window_pixels_remaining = 0;
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
