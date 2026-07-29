/*
 * Canonical PicoCalc BSP.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 */

#include "picocalc/sdcard.h"

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "picocalc/board.h"

namespace picocalc::sdcard {
namespace {

constexpr uint32_t kBlockSize = 512;
constexpr uint8_t kCmdWriteSingleBlock = 24;

spi_inst_t* const kSpi = spi0;
bool g_initialized = false;
bool g_sdhc = false;
bool g_present_valid = false;
bool g_present_cached = false;
bool g_detect_gpio_ready = false;
LogCallback g_log_callback = nullptr;

uint8_t spi_xfer(uint8_t value) {
    uint8_t rx = 0xff;
    spi_write_read_blocking(kSpi, &value, &rx, 1);
    return rx;
}

void detect_gpio_init() {
    if (g_detect_gpio_ready) {
        return;
    }
    gpio_init(board::kSdDetect);
    gpio_set_dir(board::kSdDetect, GPIO_IN);
    gpio_pull_up(board::kSdDetect);
    g_detect_gpio_ready = true;
}

bool poll_present() {
    detect_gpio_init();
    g_present_cached = !gpio_get(board::kSdDetect);
    g_present_valid = true;
    log("detect", g_present_cached ? "present" : "not_present",
        gpio_get(board::kSdDetect));
    return g_present_cached;
}

void select_card() {
    gpio_put(board::kSdCs, 0);
    (void)spi_xfer(0xff);
}

void deselect_card() {
    gpio_put(board::kSdCs, 1);
    (void)spi_xfer(0xff);
}

void clock_idle(int count) {
    while (count-- > 0) {
        (void)spi_xfer(0xff);
    }
}

bool wait_ready(uint32_t timeout_ms) {
    const absolute_time_t until = make_timeout_time_ms(static_cast<int>(timeout_ms));
    while (absolute_time_diff_us(get_absolute_time(), until) > 0) {
        if (spi_xfer(0xff) == 0xff) {
            return true;
        }
    }
    return false;
}

uint8_t command(uint8_t cmd, uint32_t arg, uint8_t crc, uint8_t* extra, int extra_len) {
    uint8_t response = 0xff;

    deselect_card();
    if (!wait_ready(20)) {
        return 0xff;
    }

    select_card();
    if (!wait_ready(20)) {
        deselect_card();
        return 0xff;
    }

    spi_xfer(static_cast<uint8_t>(0x40u | cmd));
    spi_xfer(static_cast<uint8_t>(arg >> 24));
    spi_xfer(static_cast<uint8_t>(arg >> 16));
    spi_xfer(static_cast<uint8_t>(arg >> 8));
    spi_xfer(static_cast<uint8_t>(arg));
    spi_xfer(crc);

    for (int i = 0; i < 10; ++i) {
        response = spi_xfer(0xff);
        if ((response & 0x80u) == 0) {
            break;
        }
    }

    for (int i = 0; i < extra_len; ++i) {
        extra[i] = spi_xfer(0xff);
    }
    return response;
}

bool read_data_block(uint8_t* buffer, uint32_t len) {
    uint8_t token = 0xff;
    for (int i = 0; i < 20000; ++i) {
        token = spi_xfer(0xff);
        if (token == 0xfe) {
            break;
        }
    }
    if (token != 0xfe) {
        return false;
    }

    for (uint32_t i = 0; i < len; ++i) {
        buffer[i] = spi_xfer(0xff);
    }
    (void)spi_xfer(0xff);
    (void)spi_xfer(0xff);
    return true;
}

bool write_data_block(const uint8_t* buffer, uint8_t token) {
    if (!wait_ready(500)) {
        return false;
    }

    spi_xfer(token);
    if (token == 0xfd) {
        return true;
    }

    for (uint32_t i = 0; i < kBlockSize; ++i) {
        spi_xfer(buffer[i]);
    }
    (void)spi_xfer(0xff);
    (void)spi_xfer(0xff);

    const uint8_t response = spi_xfer(0xff);
    return (response & 0x1fu) == 0x05u;
}

bool read_csd(uint8_t csd[16]) {
    const uint8_t r1 = command(9, 0, 0x01, nullptr, 0);
    if (r1 != 0x00 || !read_data_block(csd, 16)) {
        deselect_card();
        (void)spi_xfer(0xff);
        return false;
    }
    deselect_card();
    (void)spi_xfer(0xff);
    return true;
}

}  // namespace

void set_log_callback(LogCallback callback) {
    g_log_callback = callback;
}

void log(const char* component, const char* status, uint32_t detail) {
    if (g_log_callback != nullptr) {
        g_log_callback(component, status, detail);
    }
}

bool is_present() {
    if (g_present_valid) {
        return g_present_cached;
    }
    return poll_present();
}

bool init() {
    uint8_t r7[4] = {};
    uint8_t ocr[4] = {};

    if (g_initialized) {
        return true;
    }
    if (!poll_present()) {
        log("init", "no_card");
        return false;
    }

    log("init", "begin");
    spi_init(kSpi, board::kSdInitHz);
    spi_set_format(kSpi, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(board::kSdSck, GPIO_FUNC_SPI);
    gpio_set_function(board::kSdMosi, GPIO_FUNC_SPI);
    gpio_set_function(board::kSdMiso, GPIO_FUNC_SPI);
    gpio_pull_up(board::kSdMiso);

    gpio_init(board::kSdCs);
    gpio_set_dir(board::kSdCs, GPIO_OUT);
    deselect_card();
    clock_idle(10);

    bool idle = false;
    for (int i = 0; i < 20; ++i) {
        const uint8_t r1 = command(0, 0, 0x95, nullptr, 0);
        deselect_card();
        (void)spi_xfer(0xff);
        if (r1 == 0x01) {
            idle = true;
            break;
        }
        sleep_ms(10);
    }
    if (!idle) {
        log("init", "cmd0_fail");
        return false;
    }

    uint8_t r1 = command(8, 0x000001aau, 0x87, r7, 4);
    deselect_card();
    (void)spi_xfer(0xff);
    if (r1 != 0x01 || r7[2] != 0x01 || r7[3] != 0xaa) {
        log("init", "cmd8_fail", r1);
        return false;
    }

    bool ready = false;
    for (int i = 0; i < 200; ++i) {
        r1 = command(55, 0, 0x01, nullptr, 0);
        deselect_card();
        (void)spi_xfer(0xff);
        if (r1 > 0x01) {
            log("init", "cmd55_fail", r1);
            return false;
        }

        r1 = command(41, 0x40000000u, 0x01, nullptr, 0);
        deselect_card();
        (void)spi_xfer(0xff);
        if (r1 == 0x00) {
            ready = true;
            break;
        }
        sleep_ms(10);
    }
    if (!ready) {
        log("init", "acmd41_timeout");
        return false;
    }

    r1 = command(58, 0, 0x01, ocr, 4);
    deselect_card();
    (void)spi_xfer(0xff);
    if (r1 != 0x00) {
        log("init", "cmd58_fail", r1);
        return false;
    }

    g_sdhc = (ocr[0] & 0x40u) != 0;
    spi_set_baudrate(kSpi, board::kSdRunHz);
    g_initialized = true;
    log("init", "ok", g_sdhc ? 1u : 0u);
    return true;
}

bool is_initialized() {
    return g_initialized;
}

bool read_sectors(uint32_t lba, uint8_t* buffer, uint32_t count) {
    if (buffer == nullptr || count == 0 || !init()) {
        return false;
    }

    while (count-- > 0) {
        const uint32_t addr = g_sdhc ? lba : (lba * kBlockSize);
        const uint8_t r1 = command(17, addr, 0x01, nullptr, 0);
        if (r1 != 0x00 || !read_data_block(buffer, kBlockSize)) {
            deselect_card();
            (void)spi_xfer(0xff);
            return false;
        }
        deselect_card();
        (void)spi_xfer(0xff);
        buffer += kBlockSize;
        ++lba;
    }
    return true;
}

bool write_sectors(uint32_t lba, const uint8_t* buffer, uint32_t count) {
    if (buffer == nullptr || count == 0 || !init()) {
        return false;
    }

    while (count-- > 0) {
        const uint32_t addr = g_sdhc ? lba : (lba * kBlockSize);
        const uint8_t r1 = command(kCmdWriteSingleBlock, addr, 0x01, nullptr, 0);
        if (r1 != 0x00 || !write_data_block(buffer, 0xfe) || !wait_ready(500)) {
            deselect_card();
            (void)spi_xfer(0xff);
            return false;
        }
        deselect_card();
        (void)spi_xfer(0xff);
        buffer += kBlockSize;
        ++lba;
    }
    return true;
}

bool get_sector_count(uint32_t* sector_count) {
    uint8_t csd[16] = {};
    uint32_t c_size = 0;

    if (sector_count == nullptr || !init() || !read_csd(csd)) {
        return false;
    }

    if ((csd[0] >> 6) == 1) {
        c_size = (static_cast<uint32_t>(csd[7] & 0x3fu) << 16) |
                 (static_cast<uint32_t>(csd[8]) << 8) |
                 static_cast<uint32_t>(csd[9]);
        *sector_count = (c_size + 1u) * 1024u;
        return true;
    }

    const uint32_t read_bl_len = static_cast<uint32_t>(csd[5] & 0x0fu);
    const uint32_t c_size_mult =
        static_cast<uint32_t>(((csd[9] & 0x03u) << 1) | ((csd[10] >> 7) & 0x01u));
    c_size = (static_cast<uint32_t>(csd[6] & 0x03u) << 10) |
             (static_cast<uint32_t>(csd[7]) << 2) |
             (static_cast<uint32_t>((csd[8] >> 6) & 0x03u));
    *sector_count =
        (c_size + 1u) * (1u << (c_size_mult + 2u)) * (1u << read_bl_len) / 512u;
    return true;
}

void reset() {
    g_initialized = false;
    g_sdhc = false;
    g_present_valid = false;
}

}  // namespace picocalc::sdcard
