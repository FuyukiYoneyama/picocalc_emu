#pragma once

#include <stddef.h>
#include <stdint.h>

#include "picocalc/board_generated.h"

namespace picocalc::detail::lcd {

struct InitStep {
    uint8_t command;
    uint8_t data[14];
    size_t data_length;
};

inline constexpr InitStep kControllerInitSequence[] = {
    {0xf0, {0xc3}, 1},
    {0xf0, {0x96}, 1},
    {0x36, {board::kLcdMadctl}, 1},
    {0x3a, {board::kLcdColmod}, 1},
    {0xb1, {0xa0}, 1},
    {0xb4, {0x00}, 1},
    {0xb7, {0xc6}, 1},
    {0xb9, {0x02, 0xe0}, 2},
    {0xc0, {0x80, 0x06}, 2},
    {0xc1, {0x15}, 1},
    {0xc2, {0xa7}, 1},
    {0xc5, {0x04}, 1},
    {0xe8, {0x40, 0x8a, 0x00, 0x00, 0x29, 0x19, 0xaa, 0x33}, 8},
    {0xe0,
     {0xf0, 0x06, 0x0f, 0x05, 0x04, 0x20, 0x37,
      0x33, 0x4c, 0x37, 0x13, 0x14, 0x2b, 0x31},
     14},
    {0xe1,
     {0xf0, 0x11, 0x1b, 0x11, 0x0f, 0x0a, 0x37,
      0x43, 0x4c, 0x37, 0x13, 0x13, 0x2c, 0x32},
     14},
    {0xf0, {0x3c}, 1},
    {0xf0, {0x69}, 1},
    {0x35, {0x00}, 1},
    {0x11, {}, 0},
};

template <typename Transport>
void write_transaction(Transport& transport,
                       bool data_mode,
                       const uint8_t* bytes,
                       size_t length) {
    if (bytes == nullptr || length == 0) {
        return;
    }
    transport.select();
    transport.set_data_mode(data_mode);
    transport.write(bytes, length);
    transport.wait_idle();
    transport.deselect();
}

template <typename Transport>
void write_command(Transport& transport, uint8_t command) {
    write_transaction(transport, false, &command, 1);
}

template <typename Transport>
void write_data(Transport& transport, const uint8_t* data, size_t length) {
    write_transaction(transport, true, data, length);
}

template <typename Transport>
void write_command_data(Transport& transport,
                        uint8_t command,
                        const uint8_t* data,
                        size_t length) {
    write_command(transport, command);
    write_data(transport, data, length);
}

template <typename Transport>
void write_command_data(Transport& transport, uint8_t command, uint8_t value) {
    write_command_data(transport, command, &value, 1);
}

// This is the executable form of the hardware-proven ST7365P/ILI9488-compatible
// controller sequence. Both the RP2040 BSP and host transaction test call it.
template <typename Transport, typename Delay, typename Clear>
void initialize_controller(Transport& transport, Delay delay_ms, Clear clear) {
    for (const InitStep& step : kControllerInitSequence) {
        if (step.data_length == 0) {
            write_command(transport, step.command);
        } else {
            write_command_data(
                transport, step.command, step.data, step.data_length);
        }
    }
    delay_ms(120);
    write_command(transport, 0x21);
    clear();
    write_command(transport, 0x29);
    delay_ms(120);
}

template <typename Callback>
void for_each_chunk(size_t total, size_t maximum, Callback callback) {
    if (maximum == 0) {
        return;
    }
    while (total > 0) {
        const size_t chunk = total < maximum ? total : maximum;
        callback(chunk);
        total -= chunk;
    }
}

}  // namespace picocalc::detail::lcd
