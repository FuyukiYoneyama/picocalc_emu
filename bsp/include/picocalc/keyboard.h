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

// One raw status/FIFO transaction for hardware diagnostics. This deliberately
// exposes I2C transaction counts and bytes, not the keyboard controller's
// implementation types, so an app can distinguish an empty FIFO from a
// controller/bus failure without depending on the vendor driver.
struct DiagnosticSample {
    int status_write_result = 0;
    int status_read_result = 0;
    uint8_t status[2] = {};
    bool fifo_read_attempted = false;
    int fifo_write_result = 0;
    int fifo_read_result = 0;
    uint8_t fifo[2] = {};
};

void init();
bool read_event(KeyEvent* event);
bool read_diagnostic(DiagnosticSample* sample);
uint32_t read_count();
uint32_t error_count();
uint32_t empty_count();

}  // namespace picocalc::keyboard
