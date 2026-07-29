/*
 * Canonical PicoCalc BSP.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <stdbool.h>
#include <stdint.h>

namespace picocalc::sdcard {

using LogCallback = void (*)(const char* component,
                             const char* status,
                             uint32_t detail);

void set_log_callback(LogCallback callback);
void log(const char* component, const char* status, uint32_t detail = 0);

bool is_present();
bool init();
bool is_initialized();
bool read_sectors(uint32_t lba, uint8_t* buffer, uint32_t count);
bool write_sectors(uint32_t lba, const uint8_t* buffer, uint32_t count);
bool get_sector_count(uint32_t* sector_count);
void reset();

}  // namespace picocalc::sdcard
