#include <stdio.h>

#include "pico/stdlib.h"
#include "picocalc/bsp.h"

int main() {
    if (!picocalc::init()) {
        printf("[PICOCALC][APP] status=halt reason=lcd_bsp_init_failed\n");
        while (true) {
            sleep_ms(1000);
        }
    }

    printf("[PICOCALC][APP] version=%s compile=%s %s mode=lcd-only\n",
           PICOCALC_APP_VERSION, __DATE__, __TIME__);

    printf("[PICOCALC][LCD] visible_clear phase=begin color=0xf800 hold_ms=3000\n");
    picocalc::display::clear(0xf800);
    printf("[PICOCALC][LCD] visible_clear phase=end status=ok\n");
    sleep_ms(3000);

    const uint16_t verify_pattern[] = {0xf800, 0x07e0, 0x001f, 0xffff};
    picocalc::display::set_window(32, 72, 2, 2);
    picocalc::display::write_pixels(verify_pattern, 4);
    const bool lcd_verify = picocalc::display::verify_pixels(
        32, 72, 2, 2, verify_pattern, 4);
    printf("[PICOCALC][LCD][VERIFY] app_status=%s mode=lcd-only\n",
           lcd_verify ? "pass" : "fail");

    printf("[PICOCALC][READY] mode=lcd-only status=holding\n");
    while (true) {
        sleep_ms(1000);
    }
}
