#include "picocalc/keyboard.h"

#include <stddef.h>

#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "picocalc/board.h"

namespace picocalc::keyboard {
namespace {

constexpr uint8_t kRegKey = 0x04;
constexpr uint8_t kRegFifo = 0x09;
uint32_t g_read_count = 0;
uint32_t g_error_count = 0;
uint32_t g_empty_count = 0;

bool read_reg(uint8_t reg, uint8_t* data, size_t len) {
    const int written =
        i2c_write_blocking(i2c1, board::kKeyboardAddress, &reg, 1, true);
    if (written != 1) {
        ++g_error_count;
        return false;
    }
    const int read =
        i2c_read_blocking(i2c1, board::kKeyboardAddress, data, len, false);
    if (read != static_cast<int>(len)) {
        ++g_error_count;
        return false;
    }
    return true;
}

}  // namespace

void init() {
    i2c_init(i2c1, board::kKeyboardHz);
    gpio_set_function(board::kKeyboardSda, GPIO_FUNC_I2C);
    gpio_set_function(board::kKeyboardScl, GPIO_FUNC_I2C);
    gpio_pull_up(board::kKeyboardSda);
    gpio_pull_up(board::kKeyboardScl);
}

bool read_event(KeyEvent* event) {
    if (event == nullptr) {
        return false;
    }
    uint8_t key_info[2] = {};
    if (!read_reg(kRegKey, key_info, sizeof(key_info))) {
        return false;
    }
    if ((key_info[0] & 0x1f) == 0) {
        ++g_empty_count;
        return false;
    }
    uint8_t fifo_item[2] = {};
    if (!read_reg(kRegFifo, fifo_item, sizeof(fifo_item))) {
        return false;
    }
    event->state = static_cast<KeyState>(fifo_item[0]);
    event->key = fifo_item[1];
    ++g_read_count;
    return event->key != 0;
}

uint32_t read_count() {
    return g_read_count;
}

uint32_t error_count() {
    return g_error_count;
}

uint32_t empty_count() {
    return g_empty_count;
}

}  // namespace picocalc::keyboard
