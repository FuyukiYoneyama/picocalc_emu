#include <string.h>
#include <stdio.h>

#include "picocalc/psram_buffer.h"

bool copy_psram_framebuffer_example() {
    if (!picocalc::psram::available()) {
        printf("[PICOCALC][EXAMPLE][PSRAM] status=unavailable\n");
        return false;
    }

    constexpr size_t kWidth = 320;
    constexpr size_t kHeight = 320;
    constexpr size_t kBytesPerPixel = 2;
    constexpr size_t kFramebufferBytes = kWidth * kHeight * kBytesPerPixel;
    picocalc::psram::Buffer framebuffer(0, kFramebufferBytes);
    uint16_t line[kWidth];
    for (size_t x = 0; x < kWidth; ++x) {
        line[x] = (x < kWidth / 2) ? 0xf800 : 0x001f;
    }

    const size_t row = 100;
    const size_t row_offset = row * kWidth * kBytesPerPixel;
    uint16_t readback[kWidth] = {};
    const bool write_ok = framebuffer.write(row_offset, line, sizeof(line));
    const bool read_ok = framebuffer.read(row_offset, readback, sizeof(readback));
    const bool match = write_ok && read_ok && memcmp(line, readback, sizeof(line)) == 0;
    printf("[PICOCALC][EXAMPLE][PSRAM] status=%s address=0x%06lx bytes=%lu\n",
           match ? "pass" : "fail",
           static_cast<unsigned long>(framebuffer.address() + row_offset),
           static_cast<unsigned long>(sizeof(line)));
    return match;
}
