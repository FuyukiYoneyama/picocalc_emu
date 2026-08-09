/*
 * Canonical PicoCalc BSP — host SD format tests.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <array>

#include "picocalc/filesystem.h"
#include "picocalc/host.h"
#include "picocalc/sdcard.h"

namespace {

constexpr uint32_t kSectorSize = 512;
int g_failures = 0;

uint16_t get16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) |
           static_cast<uint16_t>(static_cast<uint16_t>(p[1]) << 8);
}

uint32_t get32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) |
           (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) |
           (static_cast<uint32_t>(p[3]) << 24);
}

void check(bool ok, const char* what) {
    printf("[%s] %s\n", ok ? "pass" : "FAIL", what);
    if (!ok) {
        ++g_failures;
    }
}

std::array<uint8_t, kSectorSize> read_sector(uint32_t lba) {
    std::array<uint8_t, kSectorSize> sector{};
    check(picocalc::sdcard::read_sectors(lba, sector.data(), 1), "sector read succeeds");
    return sector;
}

void check_shared_smoke(const char* format_name) {
    namespace fs = picocalc::filesystem;
    const fs::Error mounted = fs::mount();
    check(mounted == fs::Error::Ok, format_name);
    const fs::SmokeResult smoke = fs::smoke_test();
    check(smoke.ok(), "shared mount/write/sync/read/compare/remove smoke passes");
    check(picocalc::host::sd_sectors_written() > 0, "shared smoke wrote sectors");
    check(picocalc::host::sd_sectors_read() > 0, "shared smoke read sectors");
    check(fs::unmount() == fs::Error::Ok, "filesystem unmounts cleanly");
}

void check_public_file_api(const char* format_name) {
    namespace fs = picocalc::filesystem;
    char path[64] = {};
    char renamed[64] = {};
    snprintf(path, sizeof(path), "0:/API_%s.TXT", format_name);
    snprintf(renamed, sizeof(renamed), "0:/API_%s.REN", format_name);

    check(fs::mount() == fs::Error::Ok, "public file API mounts");

    fs::FileHandle invalid{};
    uint8_t invalid_byte = 0;
    check(fs::read(&invalid, &invalid_byte, 1).error == fs::Error::InvalidArgument,
          "invalid file handle read is rejected");
    check(fs::write(&invalid, &invalid_byte, 1).error == fs::Error::InvalidArgument,
          "invalid file handle write is rejected");
    check(fs::sync(&invalid) == fs::Error::InvalidArgument,
          "invalid file handle sync is rejected");
    check(fs::close(&invalid) == fs::Error::InvalidArgument,
          "invalid file handle close is rejected");

    fs::FileInfo info{};
    check(fs::stat("0:/API_DOES_NOT_EXIST.TXT", &info) == fs::Error::NotFound,
          "stat reports not-found");
    check(fs::remove("0:/API_DOES_NOT_EXIST.TXT") == fs::Error::NotFound,
          "remove reports not-found");

    fs::FileHandle file{};
    check(fs::open_write_truncate(path, &file) == fs::Error::Ok,
          "create/open-write-truncate succeeds");
    const uint8_t payload[] = {'p', 'i', 'c', 'o', 'e', 'd', 'i', 't'};
    const fs::WriteResult bounded = fs::write(&file, payload, 3);
    check(bounded.ok() && bounded.bytes == 3, "bounded write succeeds");
    const fs::WriteResult zero = fs::write(&file, payload, 0);
    check(zero.ok() && zero.bytes == 0, "zero-byte write succeeds");
    uint8_t read_during_write = 0;
    check(fs::read(&file, &read_during_write, 1).error ==
              fs::Error::InvalidArgument,
          "read through a write-only handle is rejected");
    check(fs::stat(path, &info) == fs::Error::Busy,
          "stat is rejected while a file is open");
    check(fs::remove(path) == fs::Error::Busy,
          "remove is rejected while a file is open");
    check(fs::rename(path, renamed) == fs::Error::Busy,
          "rename is rejected while a file is open");
    check(fs::sync(&file) == fs::Error::Ok, "write sync succeeds");
    check(fs::close(&file) == fs::Error::Ok, "write close succeeds");

    fs::DirectoryHandle directory{};
    check(fs::open_dir("0:/", &directory) == fs::Error::Ok,
          "root directory opens before mutation exclusion checks");
    check(fs::stat(path, &info) == fs::Error::Busy,
          "stat is rejected while a directory is open");
    check(fs::remove(path) == fs::Error::Busy,
          "remove is rejected while a directory is open");
    check(fs::rename(path, renamed) == fs::Error::Busy,
          "rename is rejected while a directory is open");
    check(fs::close_dir(&directory) == fs::Error::Ok,
          "root directory closes after mutation exclusion checks");

    check(fs::stat(path, &info) == fs::Error::Ok, "stat after write succeeds");
    check(info.size == 3 && !info.is_dir, "stat reports bounded file size");
    check(fs::open_read(path, &file) == fs::Error::Ok, "read-open succeeds");
    check(fs::write(&file, payload, 1).error == fs::Error::InvalidArgument,
          "write through a read-only handle is rejected");
    check(fs::sync(&file) == fs::Error::InvalidArgument,
          "sync through a read-only handle is rejected");
    uint8_t readback[3] = {};
    const fs::ReadResult read = fs::read(&file, readback, sizeof(readback));
    check(read.ok() && read.bytes == sizeof(readback) &&
              memcmp(readback, payload, sizeof(readback)) == 0,
          "partial file read matches");
    check(fs::close(&file) == fs::Error::Ok, "read close succeeds");

    check(fs::rename(path, renamed) == fs::Error::Ok, "rename succeeds");
    check(fs::stat(path, &info) == fs::Error::NotFound,
          "old path is not-found after rename");
    check(fs::stat(renamed, &info) == fs::Error::Ok && info.size == 3,
          "renamed path preserves file size");
    check(fs::remove(renamed) == fs::Error::Ok, "remove succeeds");
    check(fs::stat(renamed, &info) == fs::Error::NotFound,
          "removed path is not-found");
    check(fs::unmount() == fs::Error::Ok, "public file API unmounts cleanly");
    check(fs::stat(path, &info) == fs::Error::NotMounted,
          "stat rejects an unmounted filesystem");
    check(fs::open_write_truncate(path, &file) == fs::Error::NotMounted,
          "write-open rejects an unmounted filesystem");
    check(fs::remove(path) == fs::Error::NotMounted,
          "remove rejects an unmounted filesystem");
    check(fs::rename(path, renamed) == fs::Error::NotMounted,
          "rename rejects an unmounted filesystem");
}

void check_fat32() {
    picocalc::host::reset_all();

    const auto boot = read_sector(0);
    check(get16(boot.data() + 11) == 512, "FAT32 BPB sector size is 512");
    check(boot[13] == 1, "FAT32 uses one sector per cluster on 64 MiB");
    check(get16(boot.data() + 14) == 32, "FAT32 has 32 reserved sectors");
    check(boot[16] == 2, "FAT32 has two allocation tables");
    check(get16(boot.data() + 17) == 0, "FAT32 fixed root entry count is zero");
    check(get16(boot.data() + 22) == 0, "FAT32 FAT16-size field is zero");
    check(get32(boot.data() + 32) == picocalc::host::sd_sector_count(),
          "FAT32 BPB covers the 64 MiB card");
    check(get32(boot.data() + 36) == 1009, "FAT32 table has enough entries");
    check(get32(boot.data() + 44) == 2, "FAT32 root directory is cluster 2");
    check(get16(boot.data() + 48) == 1, "FAT32 FSInfo is sector 1");
    check(get16(boot.data() + 50) == 6, "FAT32 backup boot is sector 6");
    check(memcmp(boot.data() + 82, "FAT32   ", 8) == 0, "FAT32 type label is present");
    check(get16(boot.data() + 510) == 0xAA55, "FAT32 boot signature is valid");

    const auto fsinfo = read_sector(1);
    check(get32(fsinfo.data()) == 0x41615252u, "FAT32 FSInfo lead signature is valid");
    check(get32(fsinfo.data() + 484) == 0x61417272u,
          "FAT32 FSInfo structure signature is valid");
    check(get32(fsinfo.data() + 488) == 129021u,
          "FAT32 FSInfo free count excludes the root cluster");
    check(get32(fsinfo.data() + 492) == 3, "FAT32 FSInfo next free cluster is 3");
    check(get32(fsinfo.data() + 508) == 0xAA550000u,
          "FAT32 FSInfo trail signature is valid");

    const auto backup_boot = read_sector(6);
    const auto backup_fsinfo = read_sector(7);
    check(backup_boot == boot, "FAT32 backup boot matches the primary");
    check(backup_fsinfo == fsinfo, "FAT32 backup FSInfo matches the primary");

    const auto fat0 = read_sector(32);
    const auto fat1 = read_sector(32 + 1009);
    check(fat0 == fat1, "FAT32 allocation tables start identically");
    check((get32(fat0.data()) & 0x0FFFFFFFu) == 0x0FFFFFF8u,
          "FAT32 media entry is reserved");
    check((get32(fat0.data() + 8) & 0x0FFFFFFFu) == 0x0FFFFFFFu,
          "FAT32 root cluster is allocated as EOC");

    const auto root = read_sector(32 + 2 * 1009);
    const std::array<uint8_t, kSectorSize> empty{};
    check(root == empty, "FAT32 root cluster starts empty");

    check_shared_smoke("default FAT32 mounts through shared ChanFatFS");
    check_public_file_api("FAT32");
}

void check_fat16() {
    picocalc::host::format_sd(picocalc::host::SdFormat::Fat16);
    picocalc::sdcard::reset();
    check(picocalc::sdcard::init(), "FAT16 card reinitializes");

    const auto boot = read_sector(0);
    check(get16(boot.data() + 11) == 512, "FAT16 BPB sector size is 512");
    check(boot[13] == 4, "FAT16 uses four sectors per cluster");
    check(get16(boot.data() + 14) == 1, "FAT16 has one reserved sector");
    check(boot[16] == 2, "FAT16 has two allocation tables");
    check(get16(boot.data() + 17) == 512, "FAT16 has a fixed root directory");
    check(get16(boot.data() + 22) != 0, "FAT16 table size is present");
    check(memcmp(boot.data() + 54, "FAT16   ", 8) == 0, "FAT16 type label is present");
    check(get16(boot.data() + 510) == 0xAA55, "FAT16 boot signature is valid");

    const uint32_t fat_sectors = get16(boot.data() + 22);
    const auto fat0 = read_sector(1);
    const auto fat1 = read_sector(1 + fat_sectors);
    check(fat0 == fat1, "FAT16 allocation tables start identically");

    check_shared_smoke("explicit FAT16 mounts through shared ChanFatFS");
    check_public_file_api("FAT16");
}

}  // namespace

int main() {
    check_fat32();
    check_fat16();
    printf("sd_formats_test: %s (%d failure%s)\n", g_failures == 0 ? "pass" : "FAIL",
           g_failures, g_failures == 1 ? "" : "s");
    return g_failures == 0 ? 0 : 1;
}
