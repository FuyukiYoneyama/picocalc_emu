#include "picocalc/psram.h"

#include <algorithm>
#include <string.h>
#include <stdio.h>

#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "pico/stdlib.h"
#include "vendor/rp2040-psram/psram_spi.h"

namespace picocalc::psram {
namespace {

constexpr uint32_t kMaxSystemClockKhz = 250000u;
constexpr float kSafeClkdivAt250Mhz = 1.5f;
constexpr float kSafeClkdivAt125Mhz = 1.0f;
constexpr float kFallbackClkdivs[] = {1.5f, 2.0f, 3.0f, 4.0f};

struct Candidate {
    float clkdiv;
    bool fudge;
};

psram_spi_inst_t g_psram = {};
Info g_info = {};
bool g_initialized = false;

uint32_t spi_hz_for(float clkdiv) {
    const uint32_t sys_hz = clock_get_hz(clk_sys);
    return static_cast<uint32_t>(static_cast<float>(sys_hz) / (2.0f * clkdiv));
}

void read_id(uint8_t id[8]) {
    uint8_t command[] = {
        32, 64, 0x9fu, 0x00, 0x00, 0x00,
    };
    pio_spi_write_read_dma_blocking(&g_psram, command, sizeof(command), id, 8);
}

void uninit() {
    if (!g_initialized) {
        return;
    }
    psram_spi_uninit(g_psram, g_info.fudge);
    g_psram = {};
    g_initialized = false;
}

bool range_valid(uint32_t address, size_t bytes) {
    return address <= capacity_bytes && bytes <= capacity_bytes - address;
}

void write_raw(uint32_t address, const uint8_t* source, size_t bytes) {
    while (bytes != 0u) {
        const size_t chunk = std::min(bytes, max_transfer_chunk_bytes);
        psram_write(&g_psram, address, source, chunk);
        address += static_cast<uint32_t>(chunk);
        source += chunk;
        bytes -= chunk;
    }
}

void read_raw(uint32_t address, uint8_t* destination, size_t bytes) {
    while (bytes != 0u) {
        const size_t chunk = std::min(bytes, max_transfer_chunk_bytes);
        psram_read(&g_psram, address, destination, chunk);
        address += static_cast<uint32_t>(chunk);
        destination += chunk;
        bytes -= chunk;
    }
}

bool try_config(float clkdiv, bool fudge) {
    uninit();
    g_psram = psram_spi_init_clkdiv(pio1, -1, clkdiv, fudge);
    g_initialized = true;
    g_info.clkdiv = clkdiv;
    g_info.spi_hz = spi_hz_for(clkdiv);
    g_info.fudge = fudge;
    memset(g_info.id, 0, sizeof(g_info.id));
    read_id(g_info.id);

    const VerifyResult result = self_test();
    printf("[PICOCALC][PSRAM][PROBE] status=%s pio=1 sm=%d sysclk_khz=%lu "
           "clkdiv=%.2f spi_hz=%lu fudge=%u id=%02x%02x%02x%02x%02x%02x%02x%02x\n",
           result.ok ? "pass" : "fail",
           g_psram.sm,
           static_cast<unsigned long>(g_info.system_clock_khz),
           static_cast<double>(g_info.clkdiv),
           static_cast<unsigned long>(g_info.spi_hz),
           fudge ? 1u : 0u,
           g_info.id[0], g_info.id[1], g_info.id[2], g_info.id[3],
           g_info.id[4], g_info.id[5], g_info.id[6], g_info.id[7]);
    if (!result.ok) {
        uninit();
    }
    return result.ok;
}

}  // namespace

bool init() {
    if (g_initialized) {
        return true;
    }

    g_info = {};
    g_info.system_clock_khz = clock_get_hz(clk_sys) / 1000u;
    printf("[PICOCALC][PSRAM][POLICY] sysclk_khz=%lu max_sysclk_khz=%lu "
           "pins=cs20,sck21,mosi2,miso3 driver=pio1 "
           "fudge=required_at_or_above_83mhz low_speed_fudge=disabled\n",
           static_cast<unsigned long>(g_info.system_clock_khz),
           static_cast<unsigned long>(kMaxSystemClockKhz));

    if (g_info.system_clock_khz > kMaxSystemClockKhz) {
        printf("[PICOCALC][PSRAM] status=unavailable reason=sysclk_above_safe_limit\n");
        return false;
    }

    // The 250 MHz / clkdiv 1.0 and 1.2 configurations are deliberately not
    // attempted: the reference hardware logs show READ8 failures there.
    Candidate candidates[sizeof(kFallbackClkdivs) / sizeof(kFallbackClkdivs[0]) + 1] = {};
    size_t candidate_count = 0u;
    if (g_info.system_clock_khz <= 125000u) {
        // The reference PIO driver samples on the normal edge below the
        // high-speed threshold. pico_rescue probes these low-speed settings
        // with fudge=false; retaining that distinction is required on A.
        candidates[candidate_count++] = {kSafeClkdivAt125Mhz, false};
    }
    for (const float candidate : kFallbackClkdivs) {
        bool duplicate = false;
        for (size_t i = 0; i < candidate_count; ++i) {
            duplicate = duplicate ||
                        (candidates[i].clkdiv == candidate &&
                         candidates[i].fudge == (g_info.system_clock_khz > 125000u));
        }
        if (!duplicate) {
            candidates[candidate_count++] = {candidate, g_info.system_clock_khz > 125000u};
        }
    }

    for (size_t i = 0; i < candidate_count; ++i) {
        if (try_config(candidates[i].clkdiv, candidates[i].fudge)) {
            g_info.initialized = true;
            printf("[PICOCALC][PSRAM] status=ok capacity=%lu clkdiv=%.2f "
                   "spi_hz=%lu self_test=pass\n",
                   static_cast<unsigned long>(capacity_bytes),
                   static_cast<double>(g_info.clkdiv),
                   static_cast<unsigned long>(g_info.spi_hz));
            return true;
        }
    }

    g_info = {};
    g_info.system_clock_khz = clock_get_hz(clk_sys) / 1000u;
    printf("[PICOCALC][PSRAM] status=unavailable reason=no_safe_configuration\n");
    return false;
}

bool available() {
    return g_initialized;
}

const Info& info() {
    return g_info;
}

VerifyResult self_test() {
    // This is the exact 24-byte probe used by pico_rescue: it exercises the
    // proven generic psram_write()/psram_read() path without inventing a new
    // transaction shape for the BSP self-test.
    constexpr uint32_t kTestAddress = 320u * 320u + 64u;
    const uint8_t pattern[] = {
        0x00, 0x55, 0xaa, 0xff, 0x3c, 0xc3, 0x12, 0x87,
        0x5a, 0xa5, 0x0f, 0xf0, 0x33, 0xcc, 0x69, 0x96,
        0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
    };
    constexpr size_t kTestBytes = sizeof(pattern);
    uint8_t readback[kTestBytes] = {};

    if (!g_initialized || !range_valid(kTestAddress, kTestBytes)) {
        return {false, kTestAddress, kTestBytes, kTestBytes};
    }
    write_raw(kTestAddress, pattern, sizeof(pattern));
    read_raw(kTestAddress, readback, sizeof(readback));
    size_t mismatches = 0;
    for (size_t i = 0; i < kTestBytes; ++i) {
        if (pattern[i] != readback[i]) {
            ++mismatches;
        }
    }
    printf("[PICOCALC][PSRAM][VERIFY] status=%s address=0x%06lx bytes=%lu "
           "mismatches=%lu\n",
           mismatches == 0u ? "pass" : "fail",
           static_cast<unsigned long>(kTestAddress),
           static_cast<unsigned long>(kTestBytes),
           static_cast<unsigned long>(mismatches));
    return {mismatches == 0u, kTestAddress, kTestBytes, mismatches};
}

bool read(uint32_t address, void* destination, size_t bytes) {
    if (!g_initialized || destination == nullptr || !range_valid(address, bytes)) {
        return false;
    }
    read_raw(address, static_cast<uint8_t*>(destination), bytes);
    return true;
}

bool write(uint32_t address, const void* source, size_t bytes) {
    if (!g_initialized || source == nullptr || !range_valid(address, bytes)) {
        return false;
    }
    write_raw(address, static_cast<const uint8_t*>(source), bytes);
    return true;
}

}  // namespace picocalc::psram
