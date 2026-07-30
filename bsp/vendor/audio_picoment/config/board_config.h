#pragma once

#include <stdint.h>

namespace picoment::board {

constexpr uint32_t kTargetSampleRate = 48000;
constexpr unsigned kAudioPwmLeft = 26;
constexpr unsigned kAudioPwmRight = 27;
constexpr uint16_t kAudioPwmWrap = 255;

}  // namespace picoment::board
