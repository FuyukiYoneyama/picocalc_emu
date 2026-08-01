#pragma once

#include "picocalc/audio.h"
#include "picocalc/board.h"
#include "picocalc/display.h"
#include "picocalc/filesystem.h"
#include "picocalc/keyboard.h"
#include "picocalc/psram.h"
#include "picocalc/psram_buffer.h"
#include "picocalc/sdcard.h"

namespace picocalc {

// Initializes the selected, hardware-proven BSP. Applications must call this
// once before using display, keyboard, filesystem, audio, or PSRAM APIs.
// The selected LCD wire protocol is an implementation detail of the build
// variant; application pixels remain RGB565.
bool init();

}  // namespace picocalc
