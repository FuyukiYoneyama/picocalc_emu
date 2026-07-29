#include <stdio.h>

#include "pico/stdlib.h"
#include "picocalc/bsp.h"

int main() {
    const bool ok = picocalc::init_backlight_only();
    printf("[PICOCALC][APP] version=%s compile=%s %s mode=backlight-only status=%s\n",
           PICOCALC_APP_VERSION, __DATE__, __TIME__, ok ? "ready" : "halt");
    while (true) {
        sleep_ms(1000);
    }
}
