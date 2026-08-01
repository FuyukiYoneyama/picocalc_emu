#include "picocalc/filesystem.h"

#include <algorithm>
#include <limits.h>
#include <string.h>

#include "ff.h"

namespace picocalc::filesystem {
namespace {

FATFS g_filesystem{};
FIL g_file{};
constexpr size_t kMaxOpenDirectories = 16;
DIR g_directories[kMaxOpenDirectories]{};
bool g_directory_used[kMaxOpenDirectories]{};
bool g_mounted = false;
bool g_file_open = false;
size_t g_directory_count = 0;
constexpr uint32_t kFileToken = 0x46494c45u;
constexpr uint32_t kDirectoryToken = 0x44495231u;
constexpr char kPayload[] = "PicoCalc BSP SD read/write smoke test\n";

SmokeResult fail(SmokeStage stage, FRESULT detail) {
    return {stage, static_cast<uint32_t>(detail)};
}

Error map_mount_error(FRESULT result) {
    return result == FR_OK ? Error::Ok : Error::MountFailed;
}

bool valid_file(const FileHandle* handle) {
    return handle != nullptr && handle->token == kFileToken && g_file_open;
}

bool valid_directory(const DirectoryHandle* handle) {
    if (handle == nullptr || handle->token <= kDirectoryToken) return false;
    const uint32_t index = handle->token - kDirectoryToken - 1u;
    return index < kMaxOpenDirectories && g_directory_used[index];
}

size_t directory_index(const DirectoryHandle* handle) {
    return static_cast<size_t>(handle->token - kDirectoryToken - 1u);
}

}  // namespace

const char* error_name(Error error) {
    switch (error) {
        case Error::Ok: return "ok";
        case Error::InvalidArgument: return "invalid_argument";
        case Error::NotMounted: return "not_mounted";
        case Error::Busy: return "busy";
        case Error::MountFailed: return "mount_failed";
        case Error::OpenFailed: return "open_failed";
        case Error::ReadFailed: return "read_failed";
        case Error::SeekFailed: return "seek_failed";
        case Error::CloseFailed: return "close_failed";
        case Error::DirectoryFailed: return "directory_failed";
        case Error::EndOfDirectory: return "end_of_directory";
    }
    return "unknown";
}

Error mount() {
    if (g_mounted) return Error::Ok;
    const FRESULT result = f_mount(&g_filesystem, "0:", 1);
    if (result != FR_OK) return map_mount_error(result);
    g_mounted = true;
    return Error::Ok;
}

Error unmount() {
    if (g_file_open || g_directory_count != 0) return Error::Busy;
    if (!g_mounted) return Error::Ok;
    const FRESULT result = f_mount(nullptr, "0:", 0);
    if (result != FR_OK) return Error::MountFailed;
    g_mounted = false;
    return Error::Ok;
}

bool mounted() {
    return g_mounted;
}

Error open_read(const char* path, FileHandle* handle) {
    if (path == nullptr || handle == nullptr) return Error::InvalidArgument;
    if (!g_mounted) return Error::NotMounted;
    if (g_file_open || g_directory_count != 0) return Error::Busy;
    const FRESULT result = f_open(&g_file, path, FA_READ);
    if (result != FR_OK) return Error::OpenFailed;
    g_file_open = true;
    handle->token = kFileToken;
    return Error::Ok;
}

ReadResult read(FileHandle* handle, void* destination, size_t bytes) {
    if (!valid_file(handle) || destination == nullptr) return {0, Error::InvalidArgument};
    if (bytes == 0) return {0, Error::Ok};
    UINT actual = 0;
    const FRESULT result = f_read(&g_file, destination, static_cast<UINT>(std::min<size_t>(bytes, UINT_MAX)), &actual);
    if (result != FR_OK) return {actual, Error::ReadFailed};
    return {actual, Error::Ok};
}

Error seek(FileHandle* handle, uint32_t offset) {
    if (!valid_file(handle)) return Error::InvalidArgument;
    return f_lseek(&g_file, static_cast<FSIZE_t>(offset)) == FR_OK ? Error::Ok : Error::SeekFailed;
}

Error tell(const FileHandle* handle, uint32_t* offset) {
    if (!valid_file(handle) || offset == nullptr) return Error::InvalidArgument;
    *offset = static_cast<uint32_t>(f_tell(&g_file));
    return Error::Ok;
}

Error size(const FileHandle* handle, uint32_t* bytes) {
    if (!valid_file(handle) || bytes == nullptr) return Error::InvalidArgument;
    *bytes = static_cast<uint32_t>(f_size(&g_file));
    return Error::Ok;
}

Error close(FileHandle* handle) {
    if (!valid_file(handle)) return Error::InvalidArgument;
    const FRESULT result = f_close(&g_file);
    g_file_open = false;
    handle->token = 0;
    return result == FR_OK ? Error::Ok : Error::CloseFailed;
}

Error open_dir(const char* path, DirectoryHandle* handle) {
    if (path == nullptr || handle == nullptr) return Error::InvalidArgument;
    if (!g_mounted) return Error::NotMounted;
    if (g_file_open || g_directory_count >= kMaxOpenDirectories) return Error::Busy;
    size_t index = 0;
    while (index < kMaxOpenDirectories && g_directory_used[index]) ++index;
    if (index == kMaxOpenDirectories) return Error::Busy;
    const FRESULT result = f_opendir(&g_directories[index], path);
    if (result != FR_OK) return Error::DirectoryFailed;
    g_directory_used[index] = true;
    ++g_directory_count;
    handle->token = kDirectoryToken + static_cast<uint32_t>(index) + 1u;
    return Error::Ok;
}

Error next_dir(DirectoryHandle* handle, DirectoryEntry* entry) {
    if (!valid_directory(handle) || entry == nullptr) return Error::InvalidArgument;
    FILINFO info{};
    const FRESULT result = f_readdir(&g_directories[directory_index(handle)], &info);
    if (result != FR_OK) return Error::DirectoryFailed;
    if (info.fname[0] == '\0') return Error::EndOfDirectory;
    strncpy(entry->name, info.fname, sizeof(entry->name) - 1);
    entry->name[sizeof(entry->name) - 1] = '\0';
    entry->size = static_cast<uint32_t>(info.fsize);
    entry->is_dir = (info.fattrib & AM_DIR) != 0;
    return Error::Ok;
}

Error close_dir(DirectoryHandle* handle) {
    if (!valid_directory(handle)) return Error::InvalidArgument;
    const size_t index = directory_index(handle);
    const FRESULT result = f_closedir(&g_directories[index]);
    g_directory_used[index] = false;
    --g_directory_count;
    handle->token = 0;
    return result == FR_OK ? Error::Ok : Error::CloseFailed;
}

SmokeResult smoke_test(const char* path) {
    if (path == nullptr) {
        return {SmokeStage::OpenWrite, 0xffffffffu};
    }

    if (g_file_open || g_directory_count != 0) return {SmokeStage::Mount, static_cast<uint32_t>(FR_LOCKED)};
    FRESULT result = FR_OK;
    if (!g_mounted) {
        result = f_mount(&g_filesystem, "0:", 1);
        if (result != FR_OK) return fail(SmokeStage::Mount, result);
        g_mounted = true;
    }

    FIL file{};
    result = f_open(&file, path, FA_CREATE_ALWAYS | FA_WRITE);
    if (result != FR_OK) {
        return fail(SmokeStage::OpenWrite, result);
    }

    UINT written = 0;
    result = f_write(&file, kPayload, sizeof(kPayload), &written);
    if (result != FR_OK || written != sizeof(kPayload)) {
        f_close(&file);
        return {SmokeStage::Write, static_cast<uint32_t>(result)};
    }
    result = f_sync(&file);
    if (result != FR_OK) {
        f_close(&file);
        return fail(SmokeStage::Sync, result);
    }
    result = f_close(&file);
    if (result != FR_OK) {
        return fail(SmokeStage::CloseWrite, result);
    }

    result = f_open(&file, path, FA_READ);
    if (result != FR_OK) {
        return fail(SmokeStage::OpenRead, result);
    }
    char buffer[sizeof(kPayload)] = {};
    UINT read = 0;
    result = f_read(&file, buffer, sizeof(buffer), &read);
    if (result != FR_OK || read != sizeof(buffer)) {
        f_close(&file);
        return {SmokeStage::Read, static_cast<uint32_t>(result)};
    }
    if (memcmp(buffer, kPayload, sizeof(kPayload)) != 0) {
        f_close(&file);
        return {SmokeStage::Compare, 0};
    }
    result = f_close(&file);
    if (result != FR_OK) {
        return fail(SmokeStage::CloseRead, result);
    }
    result = f_unlink(path);
    if (result != FR_OK) {
        return fail(SmokeStage::Remove, result);
    }
    return {SmokeStage::Ok, 0};
}

const char* stage_name(SmokeStage stage) {
    switch (stage) {
        case SmokeStage::Ok: return "ok";
        case SmokeStage::Mount: return "mount";
        case SmokeStage::OpenWrite: return "open_write";
        case SmokeStage::Write: return "write";
        case SmokeStage::Sync: return "sync";
        case SmokeStage::CloseWrite: return "close_write";
        case SmokeStage::OpenRead: return "open_read";
        case SmokeStage::Read: return "read";
        case SmokeStage::Compare: return "compare";
        case SmokeStage::CloseRead: return "close_read";
        case SmokeStage::Remove: return "remove";
    }
    return "unknown";
}

}  // namespace picocalc::filesystem
