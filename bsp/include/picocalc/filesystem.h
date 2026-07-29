#pragma once

#include <stdint.h>

namespace picocalc::filesystem {

enum class SmokeStage : uint8_t {
    Ok = 0,
    Mount,
    OpenWrite,
    Write,
    Sync,
    CloseWrite,
    OpenRead,
    Read,
    Compare,
    CloseRead,
    Remove,
};

struct SmokeResult {
    SmokeStage stage;
    uint32_t detail;

    bool ok() const {
        return stage == SmokeStage::Ok;
    }
};

SmokeResult smoke_test(const char* path = "0:/PICOTEST.TXT");
const char* stage_name(SmokeStage stage);

}  // namespace picocalc::filesystem
