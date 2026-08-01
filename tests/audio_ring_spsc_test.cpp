#include <stdint.h>

#include <array>
#include <cstdlib>
#include <iostream>

#include "picocalc/detail/audio_ring_spsc.h"

namespace {

using Ring = picocalc::detail::AudioRingSpsc<512>;

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void run_sequence(uint32_t start) {
    std::array<uint32_t, 512> values{};
    uint32_t write = start;
    uint32_t read = start;
    uint32_t next_value = 0;
    uint32_t next_read = 0;

    for (uint32_t step = 0; step < 12000; ++step) {
        const bool should_write = (step % 7u) != 0u || Ring::empty(write, read);
        if (should_write && !Ring::full(write, read)) {
            values[Ring::slot(write)] = next_value++;
            ++write;
        } else if (!Ring::empty(write, read)) {
            require(values[Ring::slot(read)] == next_read++,
                    "audio SPSC order mismatch");
            ++read;
        }
        require(Ring::level(write, read) <= 512u, "audio SPSC level out of range");
    }

    while (!Ring::empty(write, read)) {
        ++read;
    }
    require(Ring::level(write, read) == 0u, "audio SPSC did not drain");
}

}  // namespace

int main() {
    static_assert(Ring::kMask == 511u);
    static_assert(Ring::slot(UINT32_MAX) == 511u);

    uint32_t write = 0;
    uint32_t read = 0;
    std::array<uint32_t, 512> values{};
    for (uint32_t index = 0; index < 512u; ++index) {
        require(!Ring::full(write, read), "audio SPSC filled too early");
        values[Ring::slot(write)] = index;
        ++write;
    }
    require(Ring::level(write, read) == 512u, "audio SPSC full level mismatch");
    require(Ring::full(write, read), "audio SPSC full state missing");
    require(Ring::level(write + 1u, read) == 513u, "audio SPSC overflow arithmetic changed");
    for (uint32_t index = 0; index < 512u; ++index) {
        require(values[Ring::slot(read)] == index, "audio SPSC FIFO order mismatch");
        ++read;
    }
    require(Ring::empty(write, read), "audio SPSC empty state missing");

    run_sequence(UINT32_MAX - 200u);
    std::cout << "audio SPSC ring test passed\n";
    return 0;
}
