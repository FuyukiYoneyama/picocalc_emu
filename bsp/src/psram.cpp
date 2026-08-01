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

struct Candidate {
    float clkdiv;
    bool fudge;
};

struct CandidateList {
    const Candidate* values;
    size_t count;
    const char* description;
};

constexpr Candidate kAllCandidates[] = {
    {1.0f, true},  {1.5f, true},  {2.0f, true},  {3.0f, true},  {4.0f, true},
    {1.0f, false}, {1.5f, false}, {2.0f, false}, {3.0f, false}, {4.0f, false},
};

// These are the hardware-validated normal-operation candidates. The
// exhaustive list above remains available only to the coexistence sweep.
constexpr Candidate k250MHzCandidates[] = {
    // 62.5 MHz is the first normal-operation choice after the 83.3 MHz
    // candidate showed one startup mismatch in the standard smoke test.
    {2.0f, false}, {3.0f, false}, {1.5f, true},
};
constexpr Candidate k125MHzCandidates[] = {
    {1.0f, false}, {1.5f, false}, {2.0f, false}, {3.0f, false}, {4.0f, false},
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

bool configure_candidate(float clkdiv, bool fudge) {
    uninit();
    g_psram = psram_spi_init_clkdiv(pio1, -1, clkdiv, fudge);
    g_initialized = true;
    g_info.clkdiv = clkdiv;
    g_info.spi_hz = spi_hz_for(clkdiv);
    g_info.fudge = fudge;
    memset(g_info.id, 0, sizeof(g_info.id));
    read_id(g_info.id);
    return true;
}

bool coexistence_roundtrip(uint32_t frame, size_t* mismatches) {
    constexpr uint32_t kTestAddress = 320u * 320u + 128u;
    uint8_t pattern[max_transfer_chunk_bytes] = {};
    uint8_t readback[max_transfer_chunk_bytes] = {};
    for (size_t i = 0; i < sizeof(pattern); ++i) {
        pattern[i] = static_cast<uint8_t>((frame * 13u + i * 29u) & 0xffu);
    }
    write_raw(kTestAddress, pattern, sizeof(pattern));
    read_raw(kTestAddress, readback, sizeof(readback));
    size_t count = 0;
    for (size_t i = 0; i < sizeof(pattern); ++i) {
        if (pattern[i] != readback[i]) ++count;
    }
    if (mismatches != nullptr) *mismatches = count;
    return count == 0;
}

CandidateList normal_candidates(uint32_t system_clock_khz) {
    if (system_clock_khz == 250000u) {
        return {k250MHzCandidates,
                sizeof(k250MHzCandidates) / sizeof(k250MHzCandidates[0]),
                "2.00/0,3.00/0,1.50/1"};
    }
    return {k125MHzCandidates,
            sizeof(k125MHzCandidates) / sizeof(k125MHzCandidates[0]),
            "1.00/0,1.50/0,2.00/0,3.00/0,4.00/0"};
}

}  // namespace

bool init() {
    if (g_initialized) {
        return true;
    }

    g_info = {};
    g_info.system_clock_khz = clock_get_hz(clk_sys) / 1000u;
    const CandidateList policy = normal_candidates(g_info.system_clock_khz);
    printf("[PICOCALC][PSRAM][POLICY] reference=pico_rescue sysclk_khz=%lu "
           "pins=cs20,sck21,mosi2,miso3 driver=pio1 candidates="
           "%s\n",
           static_cast<unsigned long>(g_info.system_clock_khz),
           policy.description);

    // The candidate order is now limited to the hardware-validated policy for
    // the active system clock. The coexistence test uses kAllCandidates to
    // measure the rejected combinations explicitly.

    for (size_t index = 0; index < policy.count; ++index) {
        const Candidate& candidate = policy.values[index];
        if (try_config(candidate.clkdiv, candidate.fudge)) {
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
    const uint32_t write_begin = time_us_32();
    write_raw(kTestAddress, pattern, sizeof(pattern));
    const uint32_t write_us = time_us_32() - write_begin;
    const uint32_t read_begin = time_us_32();
    read_raw(kTestAddress, readback, sizeof(readback));
    const uint32_t read_us = time_us_32() - read_begin;
    size_t mismatches = 0;
    for (size_t i = 0; i < kTestBytes; ++i) {
        if (pattern[i] != readback[i]) {
            ++mismatches;
        }
    }
    printf("[PICOCALC][PSRAM][VERIFY] status=%s address=0x%06lx bytes=%lu "
           "mismatches=%lu write_us=%lu read_us=%lu\n",
           mismatches == 0u ? "pass" : "fail",
           static_cast<unsigned long>(kTestAddress),
           static_cast<unsigned long>(kTestBytes),
           static_cast<unsigned long>(mismatches),
           static_cast<unsigned long>(write_us),
           static_cast<unsigned long>(read_us));
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

CoexistenceResult probe_lcd_coexistence(CoexistenceDisplayStep display_step,
                                        uint32_t frames_per_candidate) {
    if (frames_per_candidate == 0u) frames_per_candidate = 1u;

    const uint32_t sysclk_khz = clock_get_hz(clk_sys) / 1000u;
    const CandidateList sweep = {
        kAllCandidates,
        sizeof(kAllCandidates) / sizeof(kAllCandidates[0]),
        "1.00/1,1.50/1,2.00/1,3.00/1,4.00/1,1.00/0,1.50/0,2.00/0,3.00/0,4.00/0",
    };
    uint32_t passed = 0;
    Candidate selected = {};
    bool have_selected = false;
    for (size_t index = 0; index < sweep.count; ++index) {
        const Candidate& candidate = sweep.values[index];
        configure_candidate(candidate.clkdiv, candidate.fudge);
        const uint32_t begin = time_us_32();
        uint32_t display_steps = 0;
        uint32_t display_failures = 0;
        uint32_t psram_failures = 0;
        for (uint32_t frame = 0; frame < frames_per_candidate; ++frame) {
            if (display_step != nullptr) {
                ++display_steps;
                if (!display_step(frame)) ++display_failures;
            }
            size_t mismatches = 0;
            if (!coexistence_roundtrip(frame, &mismatches)) {
                psram_failures += static_cast<uint32_t>(mismatches == 0u ? 1u : mismatches);
            }
        }
        const bool ok = display_failures == 0u && psram_failures == 0u;
        if (ok) {
            ++passed;
            if (!have_selected) {
                selected = candidate;
                have_selected = true;
            }
        }
        printf("[PICOCALC][PSRAM][COEX] sysclk_khz=%lu clkdiv=%.2f "
               "spi_hz=%lu fudge=%u frames=%lu display_steps=%lu "
               "display_failures=%lu psram_failures=%lu elapsed_us=%lu status=%s\n",
               static_cast<unsigned long>(sysclk_khz),
               static_cast<double>(candidate.clkdiv),
               static_cast<unsigned long>(spi_hz_for(candidate.clkdiv)),
               candidate.fudge ? 1u : 0u,
               static_cast<unsigned long>(frames_per_candidate),
               static_cast<unsigned long>(display_steps),
               static_cast<unsigned long>(display_failures),
               static_cast<unsigned long>(psram_failures),
               static_cast<unsigned long>(time_us_32() - begin),
               ok ? "pass" : "fail");
        uninit();
    }

    bool restored = false;
    if (have_selected) {
        configure_candidate(selected.clkdiv, selected.fudge);
        g_info.initialized = true;
        restored = true;
        printf("[PICOCALC][PSRAM][COEX] selected clkdiv=%.2f spi_hz=%lu "
               "fudge=%u reason=first_coexistence_pass\n",
               static_cast<double>(selected.clkdiv),
               static_cast<unsigned long>(spi_hz_for(selected.clkdiv)),
               selected.fudge ? 1u : 0u);
    }
    printf("[PICOCALC][PSRAM][COEX] summary candidates=%lu passed=%lu "
           "restored=%s status=%s\n",
           static_cast<unsigned long>(sweep.count),
           static_cast<unsigned long>(passed),
           restored ? "ok" : "fail",
           passed != 0u && restored ? "pass" : "fail");
    return {
        passed != 0u && restored,
        static_cast<uint32_t>(sweep.count),
        passed,
        restored,
    };
}

}  // namespace picocalc::psram
