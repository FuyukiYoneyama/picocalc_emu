#include <stdio.h>

#include "pico/stdlib.h"
#include "picocalc/keyboard.h"

void copy_keyboard_example() {
    picocalc::keyboard::KeyEvent event{};
    if (!picocalc::keyboard::read_event(&event)) {
        return;
    }
    printf("[PICOCALC][EXAMPLE][KEY] state=%u code=0x%02x\n",
           static_cast<unsigned>(event.state), event.key);
}

// Call copy_keyboard_example() from the application loop every 10 ms.
