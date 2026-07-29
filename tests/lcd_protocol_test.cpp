#include <stddef.h>
#include <stdint.h>

#include <cstdlib>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "picocalc/detail/lcd_protocol.h"

namespace {

struct Transaction {
    bool data_mode;
    std::vector<uint8_t> bytes;
};

class FakeTransport {
public:
    void select() {
        require(!selected_, "CS selected twice");
        selected_ = true;
        mode_set_ = false;
        waited_ = false;
        current_.clear();
    }

    void deselect() {
        require(selected_, "CS deselected without selection");
        require(mode_set_, "DC was not set while CS was active");
        require(waited_, "transport did not wait for idle before releasing CS");
        require(!current_.empty(), "empty SPI transaction");
        transactions.push_back({data_mode_, current_});
        selected_ = false;
    }

    void set_data_mode(bool data_mode) {
        require(selected_, "DC changed while CS was inactive");
        data_mode_ = data_mode;
        mode_set_ = true;
    }

    void write(const uint8_t* bytes, size_t length) {
        require(selected_, "SPI write while CS was inactive");
        current_.insert(current_.end(), bytes, bytes + length);
    }

    void wait_idle() {
        require(selected_, "idle wait while CS was inactive");
        waited_ = true;
    }

    std::vector<Transaction> transactions;

private:
    static void require(bool condition, const char* message) {
        if (!condition) {
            std::cerr << message << '\n';
            std::exit(1);
        }
    }

    bool selected_ = false;
    bool mode_set_ = false;
    bool data_mode_ = false;
    bool waited_ = false;
    std::vector<uint8_t> current_;
};

[[noreturn]] void fail(const std::string& message) {
    std::cerr << message << '\n';
    std::exit(1);
}

void append_command(std::vector<Transaction>& expected,
                    uint8_t command,
                    std::vector<uint8_t> data = {}) {
    expected.push_back({false, {command}});
    if (!data.empty()) {
        expected.push_back({true, std::move(data)});
    }
}

void require_equal(const std::vector<Transaction>& actual,
                   const std::vector<Transaction>& expected) {
    if (actual.size() != expected.size()) {
        fail("transaction count mismatch: actual=" + std::to_string(actual.size()) +
             " expected=" + std::to_string(expected.size()));
    }
    for (size_t index = 0; index < expected.size(); ++index) {
        if (actual[index].data_mode != expected[index].data_mode ||
            actual[index].bytes != expected[index].bytes) {
            fail("transaction mismatch at index " + std::to_string(index));
        }
    }
}

}  // namespace

int main() {
    FakeTransport transport;
    std::vector<uint32_t> delays;
    bool clear_called_after_display_inversion = false;

    picocalc::detail::lcd::initialize_controller(
        transport,
        [&](uint32_t milliseconds) { delays.push_back(milliseconds); },
        [&]() {
            clear_called_after_display_inversion =
                !transport.transactions.empty() &&
                !transport.transactions.back().data_mode &&
                transport.transactions.back().bytes == std::vector<uint8_t>{0x21};
        });

    std::vector<Transaction> expected;
    append_command(expected, 0xf0, {0xc3});
    append_command(expected, 0xf0, {0x96});
    append_command(expected, 0x36, {0x48});
    append_command(expected, 0x3a, {0x65});
    append_command(expected, 0xb1, {0xa0});
    append_command(expected, 0xb4, {0x00});
    append_command(expected, 0xb7, {0xc6});
    append_command(expected, 0xb9, {0x02, 0xe0});
    append_command(expected, 0xc0, {0x80, 0x06});
    append_command(expected, 0xc1, {0x15});
    append_command(expected, 0xc2, {0xa7});
    append_command(expected, 0xc5, {0x04});
    append_command(expected, 0xe8,
                   {0x40, 0x8a, 0x00, 0x00, 0x29, 0x19, 0xaa, 0x33});
    append_command(expected, 0xe0,
                   {0xf0, 0x06, 0x0f, 0x05, 0x04, 0x20, 0x37,
                    0x33, 0x4c, 0x37, 0x13, 0x14, 0x2b, 0x31});
    append_command(expected, 0xe1,
                   {0xf0, 0x11, 0x1b, 0x11, 0x0f, 0x0a, 0x37,
                    0x43, 0x4c, 0x37, 0x13, 0x13, 0x2c, 0x32});
    append_command(expected, 0xf0, {0x3c});
    append_command(expected, 0xf0, {0x69});
    append_command(expected, 0x35, {0x00});
    append_command(expected, 0x11);
    append_command(expected, 0x21);
    append_command(expected, 0x29);

    require_equal(transport.transactions, expected);
    if (delays != std::vector<uint32_t>{120, 120}) {
        fail("LCD delay sequence mismatch");
    }
    if (!clear_called_after_display_inversion) {
        fail("clear callback was not placed between commands 0x21 and 0x29");
    }

    std::vector<size_t> chunks;
    picocalc::detail::lcd::for_each_chunk(
        321, 160, [&](size_t chunk) { chunks.push_back(chunk); });
    if (chunks != std::vector<size_t>{160, 160, 1}) {
        fail("LCD CS chunk sequence mismatch");
    }

    std::cout << "LCD protocol transaction test passed\n";
    return 0;
}
