/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * Bring-up, and the whole-run reset a test uses between cases.
 *
 * The device's `init` probes clocks, walks PSRAM candidates, and reports
 * which of them the hardware tolerated. None of that has an answer here,
 * so this file does not pretend to give one: it prints the same boot
 * lines with `backend=host` in them, so nobody reading a log can mistake
 * a host run for a device run.
 */

#include "picocalc/bsp.h"

#include <stdio.h>

#include "picocalc/host.h"

namespace picocalc {

bool init() {
    printf("[PICOCALC][BOOT] backend=host bsp=%s app=%s\n",
#ifdef PICOCALC_BSP_VERSION
           PICOCALC_BSP_VERSION,
#else
           "unknown",
#endif
#ifdef PICOCALC_APP_VERSION
           PICOCALC_APP_VERSION
#else
           "unknown"
#endif
    );

    display::init();
    keyboard::init();
    psram::init();
    sdcard::init();
    audio::init();

    printf("[PICOCALC][BOOT] backend=host display=ok keyboard=ok psram=ok sd=ok audio=ok\n");
    return true;
}

}  // namespace picocalc

namespace picocalc::host {

void reset_all() {
    reset_time();
    picocalc::display::init();
    picocalc::keyboard::init();
    picocalc::audio::init();
    picocalc::sdcard::reset();
    format_sd();
    picocalc::sdcard::init();
}

}  // namespace picocalc::host
