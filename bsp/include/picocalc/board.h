#pragma once

#include "picocalc/board_generated.h"

namespace picocalc::board {

// RGB565からRGB888へ変換する作業バッファの上限。hardware SPIの画面転送中は
// この境界ではCSを解放せず、LCD側のRAMWRストリームを維持する。
static_assert(kLcdCs != kSdCs, "LCD and SD chip-select pins must differ");
static_assert(kLcdSck != kSdSck, "LCD and SD use independent buses");
static_assert(kLcdSck == 10 && kLcdMosi == 11 && kLcdMiso == 12,
              "Canonical PicoCalc LCD data pins changed");
static_assert(kLcdCs == 13 && kLcdDc == 14 && kLcdReset == 15,
              "Canonical PicoCalc LCD control pins changed");
static_assert(kLcdMadctl == 0x48 && kLcdColmod == 0x66,
              "Canonical PicoCalc LCD register contract changed");
static_assert(kSdMiso == 16 && kSdCs == 17 && kSdSck == 18 &&
                  kSdMosi == 19 && kSdDetect == 22,
              "Canonical PicoCalc SD pins changed");
static_assert(kKeyboardSda == 6 && kKeyboardScl == 7 &&
                  kKeyboardAddress == 0x1f,
              "Canonical PicoCalc keyboard contract changed");
static_assert(kKeyboardStatusRegister == 0x04 &&
                  kKeyboardFifoRegister == 0x09,
              "Canonical PicoCalc keyboard registers changed");
static_assert(kAudioLeft == 26 && kAudioRight == 27,
              "Canonical PicoCalc audio pins changed");
static_assert(kLcdMaxPixelsPerCs == 160,
              "Canonical LCD conversion buffer size changed");

}  // namespace picocalc::board
