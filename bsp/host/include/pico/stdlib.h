/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * The slice of `pico/stdlib.h` that PicoCalc applications actually use.
 *
 * Deliberately not a general Pico SDK emulation. Every application in
 * this repository — the template, its copyable examples, and PicoTetris
 * — reaches for exactly two things: `stdio_init_all` and `sleep_ms`. A
 * broader shim would invite host builds of code that cannot honestly run
 * here, and the compile error is the useful outcome: it says the host
 * backend does not model that part of the chip.
 *
 * `sleep_ms` does not sleep. It advances a virtual clock, so a host run
 * takes no wall time and always produces the same timeline. See
 * `picocalc/host.h`.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/// No-op: the host's stdout is already open.
void stdio_init_all(void);

/// Advance the virtual clock. Nothing blocks and no wall time passes.
void sleep_ms(uint32_t ms);

/// Advance the virtual clock by microseconds.
void sleep_us(uint64_t us);

/// Microseconds since the run began, on the virtual clock.
uint64_t time_us_64(void);
uint32_t time_us_32(void);

#ifdef __cplusplus
}  // extern "C"
#endif
