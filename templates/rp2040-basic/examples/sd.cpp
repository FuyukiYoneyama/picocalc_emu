#include <stdio.h>

#include "picocalc/filesystem.h"

bool copy_sd_example() {
    const auto result = picocalc::filesystem::smoke_test("0:/AI_TEST.TXT");
    printf("[PICOCALC][EXAMPLE][SD] status=%s stage=%s detail=%lu\n",
           result.ok() ? "pass" : "fail",
           picocalc::filesystem::stage_name(result.stage),
           static_cast<unsigned long>(result.detail));
    return result.ok();
}
