#include "picocalc/bsp.h"

#include <stdio.h>

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "pico/stdlib.h"

namespace picocalc {

bool init() {
    if (!set_sys_clock_khz(board::kSystemClockKhz, true)) {
        return false;
    }
    stdio_init_all();
    printf("[PICOCALC][BOOT] bsp=%s app=%s variant=%s git=%s build=%s compile=%s %s\n",
           PICOCALC_BSP_VERSION, PICOCALC_APP_VERSION, PICOCALC_LCD_VARIANT,
           PICOCALC_BUILD_COMMIT, PICOCALC_BUILD_TIMESTAMP, __DATE__, __TIME__);
    printf("[PICOCALC][BOOT] clock status=ok target_khz=%lu actual_khz=%lu\n",
           static_cast<unsigned long>(board::kSystemClockKhz),
           static_cast<unsigned long>(clock_get_hz(clk_sys) / 1000u));
    // UF2 loader can reset the RP2040 while the PicoCalc side remains powered.
    sleep_ms(100);
    printf("[PICOCALC][BOOT] settle status=ok delay_ms=100\n");

    // PSRAM is not part of the LCD bus. Keep its real CS (GP20) inactive so
    // applications that do not use PSRAM cannot accidentally select it.
    gpio_init(board::kPsramCs);
    gpio_set_dir(board::kPsramCs, GPIO_OUT);
    gpio_put(board::kPsramCs, 1);

    keyboard::init();
    printf("[PICOCALC][BACKLIGHT] mode=unchanged status=ok\n");

    printf("[PICOCALC][LCD] variant=%s\n", PICOCALC_LCD_VARIANT);
    display::init();
    printf("[PICOCALC][LCD] init status=ok\n");
    return true;
}

}  // namespace picocalc
