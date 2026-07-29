#include "picocalc/bsp.h"

#include <stdio.h>

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "pico/stdlib.h"

namespace picocalc {

bool init() {
    const uint32_t boot_ms = to_ms_since_boot(get_absolute_time());
    if (!set_sys_clock_khz(board::kSystemClockKhz, true)) {
        printf("[PICOCALC][BOOT][%lu ms] clock status=fail target_khz=%lu\n",
               static_cast<unsigned long>(boot_ms),
               static_cast<unsigned long>(board::kSystemClockKhz));
        return false;
    }
    stdio_init_all();
    printf("[PICOCALC][BOOT] bsp=%s git=%s build=%s compile=%s %s\n",
           PICOCALC_BSP_VERSION, PICOCALC_BUILD_COMMIT,
           PICOCALC_BUILD_TIMESTAMP, __DATE__, __TIME__);
    printf("[PICOCALC][BOOT] clock status=ok target_khz=%lu actual_khz=%lu\n",
           static_cast<unsigned long>(board::kSystemClockKhz),
           static_cast<unsigned long>(clock_get_hz(clk_sys) / 1000u));
    // UF2 Loader起動ではRP2040だけが先に再起動し、PicoCalc側の
    // STM32/I2C/LCD電源・クロックが安定する前に到達することがある。
    // 実機動作済みPicocalc_Clock/ClockCalc/mentがLCD初期化前に置く
    // 200 msの安定待ちを採用する。100 msの実装も存在するが、UF2 Loader
    // からRP2040だけを再起動する経路では、より長い側を基準にする。
    sleep_ms(200);
    printf("[PICOCALC][BOOT][%lu ms] settle status=ok delay_ms=200\n",
           static_cast<unsigned long>(to_ms_since_boot(get_absolute_time())));

    // PSRAM is not part of the LCD bus. Keep its real CS (GP20) inactive so
    // applications that do not use PSRAM cannot accidentally select it.
    gpio_init(board::kPsramCs);
    gpio_set_dir(board::kPsramCs, GPIO_OUT);
    gpio_put(board::kPsramCs, 1);
    printf("[PICOCALC][BOOT][%lu ms] psram_cs status=ok pin=%u level=1\n",
           static_cast<unsigned long>(to_ms_since_boot(get_absolute_time())),
           board::kPsramCs);

    printf("[PICOCALC][LCD][%lu ms] init status=begin\n",
           static_cast<unsigned long>(to_ms_since_boot(get_absolute_time())));
    display::init();
    printf("[PICOCALC][LCD][%lu ms] init status=ok\n",
           static_cast<unsigned long>(to_ms_since_boot(get_absolute_time())));
    keyboard::init();
    printf("[PICOCALC][BOOT][%lu ms] keyboard status=ok\n",
           static_cast<unsigned long>(to_ms_since_boot(get_absolute_time())));
    return true;
}

}  // namespace picocalc
