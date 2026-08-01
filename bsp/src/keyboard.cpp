#include "picocalc/keyboard.h"

#include <stddef.h>

#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "picocalc/board.h"

namespace picocalc::keyboard {
namespace {

uint32_t g_read_count = 0;
uint32_t g_error_count = 0;
uint32_t g_empty_count = 0;

bool read_reg(uint8_t reg, uint8_t* data, size_t len, int* write_result = nullptr,
             int* read_result = nullptr) {
    const int written =
        i2c_write_blocking(i2c1, board::kKeyboardAddress, &reg, 1, true);
    if (write_result != nullptr) *write_result = written;
    if (written != 1) {
        ++g_error_count;
        return false;
    }
    const int read =
        i2c_read_blocking(i2c1, board::kKeyboardAddress, data, len, false);
    if (read_result != nullptr) *read_result = read;
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
    if (!read_reg(board::kKeyboardStatusRegister, key_info, sizeof(key_info))) {
        return false;
    }
    if ((key_info[0] & 0x1f) == 0) {
        ++g_empty_count;
        return false;
    }
    uint8_t fifo_item[2] = {};
    if (!read_reg(board::kKeyboardFifoRegister, fifo_item, sizeof(fifo_item))) {
        return false;
    }
    event->state = static_cast<KeyState>(fifo_item[0]);
    event->key = fifo_item[1];
    ++g_read_count;
    return event->key != 0;
}

bool read_diagnostic(DiagnosticSample* sample) {
    if (sample == nullptr) return false;
    *sample = {};
    const bool status_ok = read_reg(board::kKeyboardStatusRegister, sample->status,
                                    sizeof(sample->status), &sample->status_write_result,
                                    &sample->status_read_result);
    if (!status_ok) return false;
    if ((sample->status[0] & 0x1f) == 0) return true;
    sample->fifo_read_attempted = true;
    return read_reg(board::kKeyboardFifoRegister, sample->fifo, sizeof(sample->fifo),
                    &sample->fifo_write_result, &sample->fifo_read_result);
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
