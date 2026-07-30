#pragma once

#include <stddef.h>
#include <stdint.h>

#include "picocalc/psram.h"

namespace picocalc::psram {

// A small bounds-checked view over a PSRAM region. The object does not own
// memory; it only makes the address and length explicit for copyable app code.
class Buffer {
public:
    Buffer(uint32_t address, size_t bytes) : address_(address), bytes_(bytes) {}

    uint32_t address() const { return address_; }
    size_t size() const { return bytes_; }
    bool valid() const {
        return address_ <= capacity_bytes && bytes_ <= capacity_bytes - address_;
    }

    bool read(size_t offset, void* destination, size_t bytes) const {
        if (!valid() || destination == nullptr || offset > bytes_ ||
            bytes > bytes_ - offset) {
            return false;
        }
        return psram::read(address_ + static_cast<uint32_t>(offset), destination, bytes);
    }

    bool write(size_t offset, const void* source, size_t bytes) const {
        if (!valid() || source == nullptr || offset > bytes_ ||
            bytes > bytes_ - offset) {
            return false;
        }
        return psram::write(address_ + static_cast<uint32_t>(offset), source, bytes);
    }

private:
    uint32_t address_;
    size_t bytes_;
};

}  // namespace picocalc::psram
