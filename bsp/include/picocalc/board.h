#pragma once

#include <stdint.h>

namespace picocalc::board {

constexpr uint32_t kSystemClockKhz = 250000;
constexpr uint32_t kUartBaudRate = 115200;

constexpr unsigned kLcdSck = 10;
constexpr unsigned kLcdMosi = 11;
constexpr unsigned kLcdMiso = 12;
constexpr unsigned kLcdCs = 13;
constexpr unsigned kLcdDc = 14;
constexpr unsigned kLcdReset = 15;

constexpr unsigned kSdMiso = 16;
constexpr unsigned kSdCs = 17;
constexpr unsigned kSdSck = 18;
constexpr unsigned kSdMosi = 19;
constexpr unsigned kSdDetect = 22;
constexpr uint32_t kSdInitHz = 400000;
constexpr uint32_t kSdRunHz = 12000000;

constexpr unsigned kPsramCs = 20;
constexpr unsigned kPsramSck = 21;
constexpr unsigned kPsramMosi = 2;
constexpr unsigned kPsramMiso = 3;

constexpr unsigned kKeyboardSda = 6;
constexpr unsigned kKeyboardScl = 7;
constexpr uint32_t kKeyboardHz = 400000;
constexpr uint8_t kKeyboardAddress = 0x1f;

constexpr unsigned kAudioLeft = 26;
constexpr unsigned kAudioRight = 27;

constexpr int kDisplayWidth = 320;
constexpr int kDisplayHeight = 320;
constexpr int kDisplayGramWidth = 320;
constexpr int kDisplayGramHeight = 480;

// pico_skyace の実機 bring-up で、長い CS Low の連続転送が表示崩れの
// 原因になった。既知の成功条件と同じ 160 pixels (320 bytes) を上限にする。
constexpr int kLcdMaxPixelsPerCs = 160;
constexpr float kLcdPioClockDivider = 2.0f;

static_assert(kLcdCs != kSdCs, "LCD and SD chip-select pins must differ");
static_assert(kLcdSck != kSdSck, "LCD and SD use independent buses");
static_assert(kLcdSck == 10 && kLcdMosi == 11 && kLcdMiso == 12,
              "Canonical PicoCalc LCD data pins changed");
static_assert(kLcdCs == 13 && kLcdDc == 14 && kLcdReset == 15,
              "Canonical PicoCalc LCD control pins changed");
static_assert(kSdMiso == 16 && kSdCs == 17 && kSdSck == 18 &&
                  kSdMosi == 19 && kSdDetect == 22,
              "Canonical PicoCalc SD pins changed");
static_assert(kKeyboardSda == 6 && kKeyboardScl == 7 &&
                  kKeyboardAddress == 0x1f,
              "Canonical PicoCalc keyboard contract changed");
static_assert(kAudioLeft == 26 && kAudioRight == 27,
              "Canonical PicoCalc audio pins changed");
static_assert(kLcdMaxPixelsPerCs == 160,
              "Hardware-proven LCD CS transfer boundary changed");

}  // namespace picocalc::board
