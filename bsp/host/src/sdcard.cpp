/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * The SD card as an array of sectors, arriving formatted.
 *
 * No SPI, no CMD0/ACMD41 bring-up: `init` succeeds and sectors are host
 * memory. What matters is that `src/filesystem.cpp`, `src/fatfs_diskio.cpp`
 * and ChanFatFS itself are the *same sources* the device builds, so a
 * host test exercises the real filesystem layer rather than a stand-in.
 * Only the block device underneath is swapped.
 *
 * # Why the card has to arrive formatted
 *
 * The BSP mounts and never formats, and this build cannot format either:
 * ChanFatFS is configured with `FF_USE_MKFS 0`, and that configuration is
 * part of the hardware-verified device build — changing it to make the
 * host convenient would change what ships. So the layout is written
 * here, byte by byte.
 *
 * The default profile is FAT32, matching the filesystem used on current
 * hardware validation cards. FAT16 remains available explicitly for
 * compatibility tests. Both layouts are written directly and mounted by
 * the shared ChanFatFS sources.
 */

#include "picocalc/sdcard.h"

#include <stdio.h>
#include <string.h>

#include <vector>

#include "picocalc/host.h"

namespace picocalc::host::detail {
// Counters the block layer bumps and the host API reports. Declared
// before use, defined at the bottom of this file.
extern uint64_t g_sd_sectors_read;
extern uint64_t g_sd_sectors_written;
}  // namespace picocalc::host::detail

namespace picocalc::sdcard::detail {
// Named so `host::format_sd` can re-lay the volume between tests.
void format_fat16();
void format_fat32();
}  // namespace picocalc::sdcard::detail

namespace picocalc::sdcard {
namespace {

constexpr uint32_t kSectorSize = 512;
// 64 MiB: room to work in, small enough to allocate without thought.
constexpr uint32_t kSectorCount = (64u << 20) / kSectorSize;

std::vector<uint8_t> g_sectors;
bool g_initialized = false;
LogCallback g_log_callback = nullptr;

void put16(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v & 0xFF);
    p[1] = static_cast<uint8_t>(v >> 8);
}

void put32(uint8_t* p, uint32_t v) {
    for (int i = 0; i < 4; ++i) {
        p[i] = static_cast<uint8_t>((v >> (i * 8)) & 0xFF);
    }
}

}  // namespace

namespace detail {

void format_fat16() {
    constexpr uint8_t kSectorsPerCluster = 4;
    constexpr uint16_t kReservedSectors = 1;
    constexpr uint8_t kNumFats = 2;
    constexpr uint16_t kRootEntries = 512;

    g_sectors.assign(static_cast<size_t>(kSectorCount) * kSectorSize, 0);

    const uint32_t root_sectors = (kRootEntries * 32u) / kSectorSize;
    // Size the allocation table from the data area it describes. One
    // pass is enough: the table is small relative to the volume, so
    // folding its own size back in does not move the cluster count
    // across a boundary.
    const uint32_t usable = kSectorCount - kReservedSectors - root_sectors;
    const uint32_t approx_clusters = usable / kSectorsPerCluster;
    const uint32_t fat_sectors =
        ((approx_clusters + 2) * 2 + kSectorSize - 1) / kSectorSize;

    uint8_t* boot = g_sectors.data();
    // Jump over the BPB, as a bootable volume would.
    boot[0] = 0xEB;
    boot[1] = 0x3C;
    boot[2] = 0x90;
    memcpy(boot + 3, "MSWIN4.1", 8);
    put16(boot + 11, kSectorSize);
    boot[13] = kSectorsPerCluster;
    put16(boot + 14, kReservedSectors);
    boot[16] = kNumFats;
    put16(boot + 17, kRootEntries);
    // The 16-bit sector count cannot hold a card worth modelling, so the
    // 32-bit field carries it.
    if (kSectorCount < 0x10000u) {
        put16(boot + 19, static_cast<uint16_t>(kSectorCount));
    } else {
        put32(boot + 32, kSectorCount);
    }
    boot[21] = 0xF8;  // fixed disk
    put16(boot + 22, static_cast<uint16_t>(fat_sectors));
    put16(boot + 24, 63);   // sectors per track
    put16(boot + 26, 255);  // heads
    boot[36] = 0x80;        // drive number
    boot[38] = 0x29;        // extended boot signature
    put32(boot + 39, 0x12345678u);
    memcpy(boot + 43, "PICOCALC   ", 11);
    memcpy(boot + 54, "FAT16   ", 8);
    put16(boot + 510, 0xAA55);

    // Both allocation tables start with the media descriptor and the
    // end-of-chain marker; every data cluster is free.
    for (uint8_t fat = 0; fat < kNumFats; ++fat) {
        const size_t off =
            (static_cast<size_t>(kReservedSectors) + fat * fat_sectors) * kSectorSize;
        g_sectors[off + 0] = 0xF8;
        g_sectors[off + 1] = 0xFF;
        g_sectors[off + 2] = 0xFF;
        g_sectors[off + 3] = 0xFF;
    }
}

void format_fat32() {
    constexpr uint8_t kSectorsPerCluster = 1;
    constexpr uint16_t kReservedSectors = 32;
    constexpr uint8_t kNumFats = 2;
    constexpr uint32_t kFatSectors = 1009;
    constexpr uint32_t kRootCluster = 2;
    constexpr uint16_t kFsInfoSector = 1;
    constexpr uint16_t kBackupBootSector = 6;

    g_sectors.assign(static_cast<size_t>(kSectorCount) * kSectorSize, 0);

    const uint32_t data_sectors =
        kSectorCount - kReservedSectors - kNumFats * kFatSectors;
    const uint32_t cluster_count = data_sectors / kSectorsPerCluster;

    uint8_t* boot = g_sectors.data();
    boot[0] = 0xEB;
    boot[1] = 0x58;
    boot[2] = 0x90;
    memcpy(boot + 3, "MSWIN4.1", 8);
    put16(boot + 11, kSectorSize);
    boot[13] = kSectorsPerCluster;
    put16(boot + 14, kReservedSectors);
    boot[16] = kNumFats;
    put16(boot + 17, 0);  // FAT32 has no fixed root directory.
    put16(boot + 19, 0);
    boot[21] = 0xF8;
    put16(boot + 22, 0);  // FAT size is in BPB_FATSz32.
    put16(boot + 24, 63);
    put16(boot + 26, 255);
    put32(boot + 28, 0);
    put32(boot + 32, kSectorCount);
    put32(boot + 36, kFatSectors);
    put16(boot + 40, 0);  // Both FATs are active and mirrored.
    put16(boot + 42, 0);  // FAT32 version 0.0.
    put32(boot + 44, kRootCluster);
    put16(boot + 48, kFsInfoSector);
    put16(boot + 50, kBackupBootSector);
    boot[64] = 0x80;
    boot[66] = 0x29;
    put32(boot + 67, 0x87654321u);
    memcpy(boot + 71, "PICOCALC   ", 11);
    memcpy(boot + 82, "FAT32   ", 8);
    put16(boot + 510, 0xAA55);

    uint8_t* fsinfo = g_sectors.data() +
                      static_cast<size_t>(kFsInfoSector) * kSectorSize;
    put32(fsinfo + 0, 0x41615252u);
    put32(fsinfo + 484, 0x61417272u);
    // Cluster 2 is allocated to the empty root directory.
    put32(fsinfo + 488, cluster_count - 1);
    put32(fsinfo + 492, 3);
    put32(fsinfo + 508, 0xAA550000u);

    memcpy(g_sectors.data() +
               static_cast<size_t>(kBackupBootSector) * kSectorSize,
           boot, kSectorSize);
    memcpy(g_sectors.data() +
               static_cast<size_t>(kBackupBootSector + kFsInfoSector) * kSectorSize,
           fsinfo, kSectorSize);

    for (uint8_t fat = 0; fat < kNumFats; ++fat) {
        const size_t off =
            (static_cast<size_t>(kReservedSectors) + fat * kFatSectors) * kSectorSize;
        put32(g_sectors.data() + off + 0, 0x0FFFFFF8u);
        put32(g_sectors.data() + off + 4, 0xFFFFFFFFu);
        put32(g_sectors.data() + off + 8, 0x0FFFFFFFu);  // Root cluster EOC.
    }
}

}  // namespace detail

namespace {
using detail::format_fat16;
using detail::format_fat32;
}  // namespace

void set_log_callback(LogCallback callback) {
    g_log_callback = callback;
}

void log(const char* component, const char* status, uint32_t detail) {
    if (g_log_callback != nullptr) {
        g_log_callback(component, status, detail);
        return;
    }
    printf("[PICOCALC][SD] component=%s status=%s detail=%lu\n", component, status,
           static_cast<unsigned long>(detail));
}

bool is_present() {
    return true;
}

bool init() {
    if (g_sectors.empty()) {
        format_fat32();
    }
    g_initialized = true;
    return true;
}

bool is_initialized() {
    return g_initialized;
}

bool read_sectors(uint32_t lba, uint8_t* buffer, uint32_t count) {
    if (!g_initialized || buffer == nullptr || count == 0) {
        return false;
    }
    if (lba > kSectorCount || count > kSectorCount - lba) {
        return false;
    }
    memcpy(buffer, g_sectors.data() + static_cast<size_t>(lba) * kSectorSize,
           static_cast<size_t>(count) * kSectorSize);
    picocalc::host::detail::g_sd_sectors_read += count;
    return true;
}

bool write_sectors(uint32_t lba, const uint8_t* buffer, uint32_t count) {
    if (!g_initialized || buffer == nullptr || count == 0) {
        return false;
    }
    if (lba > kSectorCount || count > kSectorCount - lba) {
        return false;
    }
    memcpy(g_sectors.data() + static_cast<size_t>(lba) * kSectorSize, buffer,
           static_cast<size_t>(count) * kSectorSize);
    picocalc::host::detail::g_sd_sectors_written += count;
    return true;
}

bool get_sector_count(uint32_t* sector_count) {
    if (sector_count == nullptr) {
        return false;
    }
    *sector_count = kSectorCount;
    return true;
}

void reset() {
    g_initialized = false;
}

}  // namespace picocalc::sdcard

namespace picocalc::host {

namespace detail {
uint64_t g_sd_sectors_read = 0;
uint64_t g_sd_sectors_written = 0;
}  // namespace detail

uint32_t sd_sector_count() {
    uint32_t count = 0;
    picocalc::sdcard::get_sector_count(&count);
    return count;
}

uint64_t sd_sectors_read() {
    return detail::g_sd_sectors_read;
}

uint64_t sd_sectors_written() {
    return detail::g_sd_sectors_written;
}

void format_sd() {
    format_sd(SdFormat::Fat32);
}

void format_sd(SdFormat format) {
    switch (format) {
        case SdFormat::Fat32:
            picocalc::sdcard::detail::format_fat32();
            break;
        case SdFormat::Fat16:
            picocalc::sdcard::detail::format_fat16();
            break;
    }
    detail::g_sd_sectors_read = 0;
    detail::g_sd_sectors_written = 0;
}

}  // namespace picocalc::host
