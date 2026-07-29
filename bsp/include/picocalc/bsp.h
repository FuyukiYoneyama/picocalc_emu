#pragma once

#include "picocalc/board.h"
#include "picocalc/display.h"
#include "picocalc/filesystem.h"
#include "picocalc/keyboard.h"
#include "picocalc/sdcard.h"

namespace picocalc {

bool init();
bool init_backlight_only();

}  // namespace picocalc
