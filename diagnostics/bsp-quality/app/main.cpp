#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "picocalc/bsp.h"

namespace {

constexpr uint32_t kReadbackIterations = 100;
constexpr uint32_t kKeyboardStepTimeoutMs = 60000;
constexpr uint32_t kKeyboardPollMs = 10;
constexpr uint32_t kRawLogLimit = 24;

struct Glyph {
    char value;
    std::array<uint8_t, 5> columns;
};

// Small diagnostic-only uppercase font authored for this project. Each byte is
// one 5x7 column, least-significant bit at the top.
constexpr Glyph kGlyphs[] = {
    {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
    {'0', {0x3e, 0x51, 0x49, 0x45, 0x3e}},
    {'1', {0x00, 0x42, 0x7f, 0x40, 0x00}},
    {'2', {0x62, 0x51, 0x49, 0x49, 0x46}},
    {'3', {0x22, 0x49, 0x49, 0x49, 0x36}},
    {'4', {0x18, 0x14, 0x12, 0x7f, 0x10}},
    {'5', {0x2f, 0x49, 0x49, 0x49, 0x31}},
    {'6', {0x3e, 0x49, 0x49, 0x49, 0x32}},
    {'7', {0x01, 0x71, 0x09, 0x05, 0x03}},
    {'8', {0x36, 0x49, 0x49, 0x49, 0x36}},
    {'9', {0x26, 0x49, 0x49, 0x49, 0x3e}},
    {'A', {0x7e, 0x11, 0x11, 0x11, 0x7e}},
    {'B', {0x7f, 0x49, 0x49, 0x49, 0x36}},
    {'C', {0x3e, 0x41, 0x41, 0x41, 0x22}},
    {'D', {0x7f, 0x41, 0x41, 0x22, 0x1c}},
    {'E', {0x7f, 0x49, 0x49, 0x49, 0x41}},
    {'F', {0x7f, 0x09, 0x09, 0x09, 0x01}},
    {'G', {0x3e, 0x41, 0x49, 0x49, 0x7a}},
    {'H', {0x7f, 0x08, 0x08, 0x08, 0x7f}},
    {'I', {0x00, 0x41, 0x7f, 0x41, 0x00}},
    {'J', {0x20, 0x40, 0x41, 0x3f, 0x01}},
    {'K', {0x7f, 0x08, 0x14, 0x22, 0x41}},
    {'L', {0x7f, 0x40, 0x40, 0x40, 0x40}},
    {'M', {0x7f, 0x02, 0x0c, 0x02, 0x7f}},
    {'N', {0x7f, 0x04, 0x08, 0x10, 0x7f}},
    {'O', {0x3e, 0x41, 0x41, 0x41, 0x3e}},
    {'P', {0x7f, 0x09, 0x09, 0x09, 0x06}},
    {'Q', {0x3e, 0x41, 0x51, 0x21, 0x5e}},
    {'R', {0x7f, 0x09, 0x19, 0x29, 0x46}},
    {'S', {0x46, 0x49, 0x49, 0x49, 0x31}},
    {'T', {0x01, 0x01, 0x7f, 0x01, 0x01}},
    {'U', {0x3f, 0x40, 0x40, 0x40, 0x3f}},
    {'V', {0x1f, 0x20, 0x40, 0x20, 0x1f}},
    {'W', {0x3f, 0x40, 0x38, 0x40, 0x3f}},
    {'X', {0x63, 0x14, 0x08, 0x14, 0x63}},
    {'Y', {0x07, 0x08, 0x70, 0x08, 0x07}},
    {'Z', {0x61, 0x51, 0x49, 0x45, 0x43}},
};

const std::array<uint8_t, 5>& glyph_columns(char value) {
    for (const auto& glyph : kGlyphs) {
        if (glyph.value == value) return glyph.columns;
    }
    return kGlyphs[0].columns;
}

void draw_text(int x, int y, const char* text, uint16_t color, int scale = 3) {
    for (const char* cursor = text; *cursor != '\0'; ++cursor) {
        const auto& columns = glyph_columns(*cursor);
        for (int column = 0; column < 5; ++column) {
            for (int row = 0; row < 7; ++row) {
                if ((columns[column] & (1u << row)) != 0u) {
                    picocalc::display::fill_rect(x + column * scale, y + row * scale,
                                                 scale, scale, color);
                }
            }
        }
        x += 6 * scale;
    }
}

void show_prompt(const char* line1, const char* line2, uint16_t accent) {
    picocalc::display::clear(0x0000);
    picocalc::display::fill_rect(0, 0, 320, 24, accent);
    draw_text(16, 58, line1, 0xffff, 3);
    draw_text(16, 106, line2, accent, 3);
}

struct LcdResult {
    uint32_t passed = 0;
    uint32_t failed = 0;
    uint32_t transport_failed = 0;
    uint32_t first_failure = UINT32_MAX;
    uint32_t max_failure_streak = 0;
    uint32_t recoveries = 0;
};

LcdResult run_lcd_test() {
    show_prompt("LCD TEST", "100 READS", 0x07e0);
    printf("[BSP_DIAG][LCD] begin iterations=%lu mode=write_2x2_then_ramrd\n",
           static_cast<unsigned long>(kReadbackIterations));
    LcdResult summary{};
    uint32_t failure_streak = 0;
    bool previous_failed = false;
    for (uint32_t iteration = 0; iteration < kReadbackIterations; ++iteration) {
        watchdog_update();
        const int x = 8 + static_cast<int>((iteration * 17u) % 300u);
        const int y = 152 + static_cast<int>((iteration * 11u) % 152u);
        const uint16_t expected[] = {
            static_cast<uint16_t>(0x001fu ^ (iteration << 5)),
            static_cast<uint16_t>(0x07e0u ^ iteration),
            static_cast<uint16_t>(0xf800u ^ (iteration << 3)),
            static_cast<uint16_t>(0xffffu ^ (iteration << 1)),
        };
        picocalc::display::set_window(x, y, 2, 2);
        picocalc::display::write_pixels(expected, 4);
        const auto result = picocalc::display::verify_pixels(x, y, 2, 2, expected, 4);
        const bool passed = result.ok();
        if (passed) {
            ++summary.passed;
            if (previous_failed) ++summary.recoveries;
            failure_streak = 0;
        } else {
            ++summary.failed;
            if (!result.transport_ok) ++summary.transport_failed;
            if (summary.first_failure == UINT32_MAX) summary.first_failure = iteration;
            ++failure_streak;
            if (failure_streak > summary.max_failure_streak) {
                summary.max_failure_streak = failure_streak;
            }
        }
        previous_failed = !passed;
        printf("[BSP_DIAG][LCD] iteration=%lu x=%d y=%d status=%s transport=%s "
               "mismatches=%lu streak=%lu\n",
               static_cast<unsigned long>(iteration), x, y, passed ? "pass" : "fail",
               result.transport_ok ? "ok" : "fail",
               static_cast<unsigned long>(result.mismatches),
               static_cast<unsigned long>(failure_streak));
    }
    printf("[BSP_DIAG][LCD] summary pass=%lu fail=%lu transport_fail=%lu "
           "first_fail=%ld max_fail_streak=%lu recoveries=%lu result=%s\n",
           static_cast<unsigned long>(summary.passed),
           static_cast<unsigned long>(summary.failed),
           static_cast<unsigned long>(summary.transport_failed),
           summary.first_failure == UINT32_MAX ? -1L : static_cast<long>(summary.first_failure),
           static_cast<unsigned long>(summary.max_failure_streak),
           static_cast<unsigned long>(summary.recoveries),
           summary.failed == 0 ? "pass" : "fail");
    return summary;
}

struct KeyRequirement {
    const char* label;
    const char* prompt1;
    const char* prompt2;
    uint8_t primary;
    uint8_t alternate;
    bool require_hold;
};

struct KeyResult {
    uint32_t status_failures = 0;
    uint32_t fifo_failures = 0;
    uint32_t unexpected = 0;
    uint32_t raw_logged = 0;
    uint32_t passed_steps = 0;
};

bool key_matches(const KeyRequirement& requirement, uint8_t key) {
    return key == requirement.primary ||
           (requirement.alternate != 0u && key == requirement.alternate);
}

bool run_key_step(const KeyRequirement& requirement, KeyResult* summary) {
    show_prompt(requirement.prompt1, requirement.prompt2, 0xffe0);
    printf("[BSP_DIAG][KEY] step=%s instruction=%s_%s timeout_ms=%lu\n",
           requirement.label, requirement.require_hold ? "hold" : "press_release",
           requirement.label, static_cast<unsigned long>(kKeyboardStepTimeoutMs));
    bool pressed = false;
    bool held = false;
    bool released = false;
    const uint64_t started = time_us_64();
    while ((time_us_64() - started) / 1000u < kKeyboardStepTimeoutMs) {
        watchdog_update();
        picocalc::keyboard::DiagnosticSample sample{};
        const bool transaction_ok = picocalc::keyboard::read_diagnostic(&sample);
        if (!transaction_ok) {
            if (sample.fifo_read_attempted) {
                ++summary->fifo_failures;
            } else {
                ++summary->status_failures;
            }
            sleep_ms(kKeyboardPollMs);
            continue;
        }
        if (!sample.fifo_read_attempted) {
            sleep_ms(kKeyboardPollMs);
            continue;
        }
        const uint8_t state = sample.fifo[0];
        const uint8_t key = sample.fifo[1];
        if (summary->raw_logged < kRawLogLimit) {
            printf("[BSP_DIAG][KEY][RAW] index=%lu step=%s status_wr=%d status_rd=%d "
                   "status=0x%02x%02x fifo_wr=%d fifo_rd=%d fifo=0x%02x%02x\n",
                   static_cast<unsigned long>(summary->raw_logged), requirement.label,
                   sample.status_write_result, sample.status_read_result,
                   sample.status[0], sample.status[1], sample.fifo_write_result,
                   sample.fifo_read_result, sample.fifo[0], sample.fifo[1]);
            ++summary->raw_logged;
        }
        if (!key_matches(requirement, key)) {
            ++summary->unexpected;
            printf("[BSP_DIAG][KEY] step=%s event=unexpected state=%u code=0x%02x\n",
                   requirement.label, static_cast<unsigned>(state), key);
            continue;
        }
        if (state == static_cast<uint8_t>(picocalc::keyboard::KeyState::Pressed)) {
            pressed = true;
        } else if (state == static_cast<uint8_t>(picocalc::keyboard::KeyState::Hold)) {
            held = true;
        } else if (state == static_cast<uint8_t>(picocalc::keyboard::KeyState::Released)) {
            released = true;
        } else {
            ++summary->unexpected;
        }
        printf("[BSP_DIAG][KEY] step=%s event=expected state=%u code=0x%02x "
               "pressed=%u hold=%u released=%u\n",
               requirement.label, static_cast<unsigned>(state), key,
               pressed ? 1u : 0u, held ? 1u : 0u, released ? 1u : 0u);
        if (pressed && released && (!requirement.require_hold || held)) {
            ++summary->passed_steps;
            printf("[BSP_DIAG][KEY] step=%s result=pass\n", requirement.label);
            return true;
        }
        sleep_ms(kKeyboardPollMs);
    }
    printf("[BSP_DIAG][KEY] step=%s result=fail reason=timeout pressed=%u hold=%u released=%u\n",
           requirement.label, pressed ? 1u : 0u, held ? 1u : 0u, released ? 1u : 0u);
    return false;
}

bool run_keyboard_test() {
    constexpr KeyRequirement requirements[] = {
        {"up", "HOLD UP", "THEN RELEASE", 0xb5, 0x01, true},
        {"down", "HOLD DOWN", "THEN RELEASE", 0xb6, 0x02, true},
        {"enter", "PRESS ENTER", "THEN RELEASE", 0x0a, 0x00, false},
        {"escape", "PRESS ESC", "THEN RELEASE", 0xb1, 0x00, false},
    };
    KeyResult summary{};
    bool passed = true;
    for (const auto& requirement : requirements) {
        passed = run_key_step(requirement, &summary) && passed;
    }
    passed = passed && summary.status_failures == 0 && summary.fifo_failures == 0;
    printf("[BSP_DIAG][KEY] summary steps_pass=%lu steps_total=%lu status_fail=%lu "
           "fifo_fail=%lu unexpected=%lu result=%s\n",
           static_cast<unsigned long>(summary.passed_steps),
           static_cast<unsigned long>(sizeof(requirements) / sizeof(requirements[0])),
           static_cast<unsigned long>(summary.status_failures),
           static_cast<unsigned long>(summary.fifo_failures),
           static_cast<unsigned long>(summary.unexpected), passed ? "pass" : "fail");
    return passed;
}

}  // namespace

int main() {
    watchdog_enable(10000, true);
    if (!picocalc::init()) {
        printf("[BSP_DIAG_VERDICT] init=fail lcd=not_run keyboard=not_run overall=fail\n");
        while (true) {
            watchdog_update();
            sleep_ms(1000);
        }
    }
    picocalc::audio::stop();
    printf("[BSP_DIAG] version=%s bsp=%s bsp_git=%s app_git=%s variant=%s "
           "sd_access=none audio=stopped readback_iterations=%lu\n",
           PICOCALC_APP_VERSION, PICOCALC_BSP_VERSION, PICOCALC_BSP_GIT,
           PICOCALC_APP_GIT, PICOCALC_LCD_VARIANT,
           static_cast<unsigned long>(kReadbackIterations));
    printf("[BSP_DIAG] human=follow_screen_and_uart no_sd_action no_timing no_photo\n");

    const LcdResult lcd = run_lcd_test();
    const bool keyboard_ok = run_keyboard_test();
    const bool lcd_ok = lcd.failed == 0;
    const bool overall = lcd_ok && keyboard_ok;
    show_prompt(overall ? "ALL PASS" : "TEST FAIL", "SAVE UART LOG",
                overall ? 0x07e0 : 0xf800);
    printf("[BSP_DIAG_VERDICT] init=pass lcd=%s lcd_pass=%lu lcd_fail=%lu "
           "keyboard=%s overall=%s\n",
           lcd_ok ? "pass" : "fail", static_cast<unsigned long>(lcd.passed),
           static_cast<unsigned long>(lcd.failed), keyboard_ok ? "pass" : "fail",
           overall ? "pass" : "fail");
    while (true) {
        watchdog_update();
        sleep_ms(1000);
    }
}

