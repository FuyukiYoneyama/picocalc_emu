#pragma once

#include <stdint.h>

namespace picocalc::keyboard {

enum class KeyState : uint8_t {
    Idle = 0,
    Pressed = 1,
    Hold = 2,
    Released = 3,
};

struct KeyEvent {
    KeyState state;
    uint8_t key;
};

void init();
bool read_event(KeyEvent* event);
uint32_t read_count();
uint32_t error_count();
uint32_t empty_count();

}  // namespace picocalc::keyboard
