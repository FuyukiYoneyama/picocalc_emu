#include "picocalc/bsp.h"

#include <stdio.h>

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "pico/stdlib.h"

namespace picocalc {

bool init() {
    if (!set_sys_clock_khz(PICOCALC_LCD_SYSTEM_CLOCK_KHZ, true)) {
        return false;
    }
    stdio_init_all();
    printf("[PICOCALC][BOOT] bsp=%s app=%s variant=%s git=%s build=%s compile=%s %s\n",
           PICOCALC_BSP_VERSION, PICOCALC_APP_VERSION, PICOCALC_LCD_VARIANT,
           PICOCALC_BUILD_COMMIT, PICOCALC_BUILD_TIMESTAMP, __DATE__, __TIME__);
    printf("[PICOCALC][BOOT] clock status=ok target_khz=%lu actual_khz=%lu\n",
           static_cast<unsigned long>(PICOCALC_LCD_SYSTEM_CLOCK_KHZ),
           static_cast<unsigned long>(clock_get_hz(clk_sys) / 1000u));
    // UF2 loader can reset the RP2040 while the PicoCalc side remains powered.
    sleep_ms(100);
    printf("[PICOCALC][BOOT] settle status=ok delay_ms=100\n");

    // Match the proven pico_rescue startup order: LCD first, PSRAM second,
    // keyboard third. This keeps the reference PSRAM probe after the display
    // has established its own bus state.
    printf("[PICOCALC][LCD] variant=%s\n", PICOCALC_LCD_VARIANT);
    display::init();
    printf("[PICOCALC][LCD] init status=ok\n");

    gpio_init(board::kPsramCs);
    gpio_set_dir(board::kPsramCs, GPIO_OUT);
    gpio_put(board::kPsramCs, 1);
    psram::init();
    keyboard::init();
    printf("[PICOCALC][BACKLIGHT] mode=unchanged status=ok\n");
    const bool audio_ok = audio::init();
    printf("[PICOCALC][AUDIO] status=%s mode=reference-fixed-sine output=1khz\n",
           audio_ok ? "ok" : "unavailable");
    return true;
}

}  // namespace picocalc
