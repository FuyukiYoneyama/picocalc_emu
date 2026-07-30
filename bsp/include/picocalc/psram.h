#pragma once

#include <stddef.h>
#include <stdint.h>

namespace picocalc::psram {

constexpr uint32_t capacity_bytes = 8u * 1024u * 1024u;
constexpr size_t max_transfer_chunk_bytes = 24u;

struct Info {
    bool initialized;
    uint32_t system_clock_khz;
    float clkdiv;
    uint32_t spi_hz;
    bool fudge;
    uint8_t id[8];
};

struct VerifyResult {
    bool ok;
    uint32_t address;
    size_t bytes;
    size_t mismatches;
};

// PSRAM is optional for applications. Failure leaves it unavailable and is
// reported in the boot log; it must never be silently treated as SRAM.
bool init();
bool available();
const Info& info();
VerifyResult self_test();
bool read(uint32_t address, void* destination, size_t bytes);
bool write(uint32_t address, const void* source, size_t bytes);

}  // namespace picocalc::psram
