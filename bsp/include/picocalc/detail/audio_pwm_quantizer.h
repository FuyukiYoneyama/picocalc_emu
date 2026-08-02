#pragma once

#include <cstdint>

namespace picocalc::detail {

template <uint32_t PwmWrap>
constexpr uint32_t reconstruct_pwm_level(uint32_t duty) {
    static_assert(PwmWrap != 0u, "PWM wrap must be non-zero");
    if constexpr (PwmWrap == 255u) {
        // 65535 == 255 * 257, so this is bit-identical to the rounded
        // division for every valid 8-bit PWM duty value.
        return duty * 257u;
    }
    return (duty * 65535u + (PwmWrap / 2u)) / PwmWrap;
}

}  // namespace picocalc::detail
