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
    printf("[PICOCALC][SMOKE] lcd=ok sd=%s stage=%s detail=%lu status_region=%s\n",
           ok ? "ok" : "fail",
           picocalc::filesystem::stage_name(result.stage),
           static_cast<unsigned long>(result.detail),
           ok ? "green" : "red");
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

    printf("[PICOCALC][VERIFY] stage=begin components=lcd,sd,keyboard\n");
    printf("[PICOCALC][LCD][VERIFY] stage=begin pattern=known_regions width=320 height=320\n");
    picocalc::display::draw_test_pattern();
    printf("[PICOCALC][LCD][VERIFY] stage=end status=drawn top=0x07e0 bottom=0x001f "
           "white=0xffff inset=0x0000 red=0xf800 green=0x07e0 blue=0x001f\n");

    constexpr const char* kSmokePath = "0:/PICOTEST.TXT";
    printf("[PICOCALC][SD][SMOKE] stage=begin path=%s "
           "sequence=mount,write,sync,close_write,read,compare,close_read,remove\n",
           kSmokePath);
    const auto storage = picocalc::filesystem::smoke_test();
    printf("[PICOCALC][SD][SMOKE] stage=end status=%s result_stage=%s detail=%lu\n",
           storage.ok() ? "ok" : "fail",
           picocalc::filesystem::stage_name(storage.stage),
           static_cast<unsigned long>(storage.detail));
    show_storage_result(storage);

    printf("[PICOCALC][KEY][VERIFY] stage=waiting requirement=multiple_press_release_events\n");
    printf("[PICOCALC][VERIFY] stage=ready lcd=drawn sd=%s keyboard=waiting\n",
           storage.ok() ? "ok" : "fail");
    printf("[PICOCALC][READY] keyboard=waiting\n");
    uint32_t key_events = 0;
    while (true) {
        picocalc::keyboard::KeyEvent event{};
        if (picocalc::keyboard::read_event(&event)) {
            ++key_events;
            printf("[PICOCALC][KEY] state=%u code=0x%02x\n",
                   static_cast<unsigned>(event.state),
                   event.key);
            printf("[PICOCALC][KEY][VERIFY] stage=event count=%lu state=%u code=0x%02x\n",
                   static_cast<unsigned long>(key_events),
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
