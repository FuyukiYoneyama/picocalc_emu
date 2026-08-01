#pragma once

#include <stdint.h>

namespace picocalc::detail {

template <uint32_t Capacity>
struct AudioRingSpsc {
    static_assert(Capacity != 0u && (Capacity & (Capacity - 1u)) == 0u,
                  "audio SPSC ring capacity must be a power of two");

    static constexpr uint32_t kMask = Capacity - 1u;

    static constexpr uint32_t level(uint32_t write, uint32_t read) {
        return write - read;
    }

    static constexpr bool empty(uint32_t write, uint32_t read) {
        return level(write, read) == 0u;
    }

    static constexpr bool full(uint32_t write, uint32_t read) {
        return level(write, read) >= Capacity;
    }

    static constexpr uint32_t slot(uint32_t cursor) {
        return cursor & kMask;
    }
};

}  // namespace picocalc::detail
