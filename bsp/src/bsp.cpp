#include "picocalc/bsp.h"

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "pico/stdlib.h"

namespace picocalc {

bool init() {
    if (!set_sys_clock_khz(board::kSystemClockKhz, true)) {
        return false;
    }
    stdio_init_all();

    // PSRAM is not part of the LCD bus. Keep its real CS (GP20) inactive so
    // applications that do not use PSRAM cannot accidentally select it.
    gpio_init(board::kPsramCs);
    gpio_set_dir(board::kPsramCs, GPIO_OUT);
    gpio_put(board::kPsramCs, 1);

    display::init();
    keyboard::init();
    return true;
}

}  // namespace picocalc
