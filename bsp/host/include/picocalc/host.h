/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <stddef.h>
#include <stdint.h>

#include <string>

/// Test-side controls for the host backend.
///
/// Applications never include this: it is the handle a test holds to
/// drive an app that was written against the ordinary `picocalc::` API.
/// Nothing here exists on the device, which is why it lives in its own
/// namespace and its own header — an app that reaches for it will fail
/// to build for the RP2040, and that is the intended answer.
///
/// # What the host backend is for
///
/// Testing application logic without building an RP2040 image. The
/// firmware backend runs the real binary and is the authority on
/// hardware behaviour; this runs the same *application* code natively,
/// in a fraction of a second, so a test can call into it, feed it keys,
/// and read the screen back.
///
/// # What it is not
///
/// It is not a model of the chip. There is no PIO, no DMA, no I2C
/// transaction, no interrupt. A display write lands in an array
/// immediately. Anything whose correctness depends on hardware timing or
/// on a peripheral's wire protocol has to be checked on the firmware
/// backend; this one cannot see those questions, let alone answer them.
namespace picocalc::host {

// --- virtual time -----------------------------------------------------

/// Microseconds since the run began. Advanced only by `sleep_ms` /
/// `sleep_us`; no wall clock is ever read, so a run is reproducible and
/// takes no real time.
uint64_t now_us();

/// Advance the clock without going through `sleep_ms`.
void advance_us(uint64_t us);

/// Put the clock back to zero.
void reset_time();

// --- keyboard ---------------------------------------------------------

/// Queue a press followed by a release, as a real keystroke would.
///
/// Bounded like the hardware controller: see `max_queued_events`.
/// Overflow is counted, not silently absorbed.
void queue_key(uint8_t code);

/// Queue every character of `text` as a keystroke.
void queue_keys(const char* text);

/// Events waiting to be read.
size_t keys_queued();

/// Events discarded because the controller was already full.
uint64_t keys_dropped();

/// The controller holds this many events and no more.
///
/// ClockworkPi's official STM32 firmware defines `FIFO_SIZE 31` and
/// `KEY_COUNT_MASK 0x1F`; the BSP reads the same mask. The firmware backend
/// models that primary-source constraint too, so a host test that overruns
/// the queue is reproducing the controller's default behavior.
constexpr size_t max_queued_events = 31;

// --- display ----------------------------------------------------------

/// The 320x320 viewport, row-major RGB565. Borrowed, not owned.
const uint16_t* framebuffer();

/// One pixel, or 0 if the coordinates are outside the viewport.
uint16_t pixel(int x, int y);

/// Pixels that are not black.
size_t non_black_pixels();

/// Non-black pixels inside a rectangle, clipped to the viewport.
size_t non_black_pixels_in(int x, int y, int w, int h);

/// SHA-256 of the framebuffer as row-major little-endian RGB565 bytes,
/// lowercase hex.
///
/// **The same canonical form the firmware backend hashes.** An app that
/// draws the same picture on both backends produces the same digest
/// here and in `picocalc-run`'s `framebuffer.rgb565_sha256`, so the two
/// can be compared directly. That comparison is the point: it is how a
/// cheap host run earns the right to stand in for a slow firmware one.
std::string framebuffer_sha256();

/// SHA-256 of a rectangle, in the same canonical form.
std::string region_sha256(int x, int y, int w, int h);

/// Write the viewport as a binary PPM (P6). Chosen over PNG so the host
/// build needs no image library; `tools/picocalc.py` converts when a PNG
/// is wanted. Returns false if the file could not be written.
bool write_ppm(const char* path);

// --- storage ----------------------------------------------------------

/// Sectors the card holds. Backed by host memory, not a real device.
uint32_t sd_sector_count();

/// Sector reads and writes since the run began.
uint64_t sd_sectors_read();
uint64_t sd_sectors_written();

/// Filesystem profile written to the in-memory SD card.
enum class SdFormat : uint8_t {
    Fat32,
    Fat16,
};

/// Wipe the card and lay down the default fresh empty FAT32 profile.
///
/// The card starts this way, because the BSP mounts and never formats —
/// same reasoning as the emulator's card model. Kept as a no-argument
/// overload so existing host tests continue to compile.
void format_sd();

/// Wipe the card and lay down an explicitly selected filesystem profile.
void format_sd(SdFormat format);

// --- audio ------------------------------------------------------------

/// Samples the application has written. There is no output device; the
/// host backend counts what an app produced so a test can check that it
/// produced it.
uint64_t audio_samples_written();

/// True while the stream is running.
bool audio_running();

// --- whole-run control ------------------------------------------------

/// Put every host model back to its initial state: clock at zero, blank
/// screen, empty key queue, freshly formatted card, silent audio.
///
/// Call between tests in one process. Without it, a test would inherit
/// whatever the previous one left behind, and the order of tests would
/// start to matter.
void reset_all();

}  // namespace picocalc::host
