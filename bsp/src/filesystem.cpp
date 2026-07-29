#include "picocalc/filesystem.h"

#include <string.h>

#include "ff.h"

namespace picocalc::filesystem {
namespace {

FATFS g_filesystem{};
constexpr char kPayload[] = "PicoCalc BSP SD read/write smoke test\n";

SmokeResult fail(SmokeStage stage, FRESULT detail) {
    return {stage, static_cast<uint32_t>(detail)};
}

}  // namespace

SmokeResult smoke_test(const char* path) {
    if (path == nullptr) {
        return {SmokeStage::OpenWrite, 0xffffffffu};
    }

    FRESULT result = f_mount(&g_filesystem, "0:", 1);
    if (result != FR_OK) {
        return fail(SmokeStage::Mount, result);
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
