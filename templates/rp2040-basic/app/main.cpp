#include <stdio.h>

#include "pico/stdlib.h"
#include "picocalc/bsp.h"

namespace {

void sd_log(const char* component, const char* status, uint32_t detail) {
    printf("[PICOCALC][SD] component=%s status=%s detail=%lu\n",
           component,
           status,
           static_cast<unsigned long>(detail));
}

void show_storage_result(const picocalc::filesystem::SmokeResult& result) {
    const bool ok = result.ok();
    picocalc::display::fill_rect(16, 184, 288, 48, ok ? 0x07e0 : 0xf800);
    printf("[PICOCALC][SMOKE] lcd=ok sd=%s stage=%s detail=%lu\n",
           ok ? "ok" : "fail",
           picocalc::filesystem::stage_name(result.stage),
           static_cast<unsigned long>(result.detail));
}

}  // namespace

int main() {
    picocalc::sdcard::set_log_callback(sd_log);
    if (!picocalc::init()) {
        printf("[PICOCALC][APP] status=halt reason=bsp_init_failed\n");
        while (true) {
            sleep_ms(1000);
        }
    }
    printf("[PICOCALC][APP] version=%s compile=%s %s\n",
           PICOCALC_APP_VERSION, __DATE__, __TIME__);

    picocalc::display::draw_test_pattern();
    const auto storage = picocalc::filesystem::smoke_test();
    show_storage_result(storage);

    printf("[PICOCALC][READY] keyboard=waiting\n");
    while (true) {
        picocalc::keyboard::KeyEvent event{};
        if (picocalc::keyboard::read_event(&event)) {
            printf("[PICOCALC][KEY] state=%u code=0x%02x\n",
                   static_cast<unsigned>(event.state),
                   event.key);
            picocalc::display::fill_rect(
                16,
                248,
                288,
                32,
                static_cast<uint16_t>(0x001f ^ (event.key << 8)));
        }
        sleep_ms(10);
    }
}
