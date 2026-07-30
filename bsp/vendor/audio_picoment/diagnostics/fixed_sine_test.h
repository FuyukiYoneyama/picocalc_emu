/* Copied from synth/Picocalc_ment/src/diagnostics/fixed_sine_test.h. */
#pragma once

#include <stdint.h>

#include "config/board_config.h"

namespace picoment::diagnostics::fixed_sine {

constexpr uint32_t kToneHz = 1000;
constexpr uint32_t kPeriodSamples = picoment::board::kTargetSampleRate / kToneHz;
constexpr int kAmplitudeDb = -6;

static_assert(kPeriodSamples == 48, "fixed sine table assumes 48 samples per period");

constexpr int16_t kTable[kPeriodSamples] = {
       0,   2144,  4250,  6284,  8211,  9997, 11612, 13028,
   14222, 15172, 15862, 16282, 16422, 16282, 15862, 15172,
   14222, 13028, 11612,  9997,  8211,  6284,  4250,  2144,
       0,  -2144, -4250, -6284, -8211, -9997,-11612,-13028,
  -14222,-15172,-15862,-16282,-16422,-16282,-15862,-15172,
  -14222,-13028,-11612, -9997, -8211, -6284, -4250, -2144,
};

inline int16_t sample_at(uint32_t index) {
    return kTable[index % kPeriodSamples];
}

}  // namespace picoment::diagnostics::fixed_sine
