set(PICOCALC_LCD_VARIANT "hwspi-rgb888" CACHE STRING
    "LCD BSP variant: hwspi-rgb888 or pio-rgb565")
set_property(CACHE PICOCALC_LCD_VARIANT PROPERTY STRINGS
    hwspi-rgb888 pio-rgb565)

if(PICOCALC_LCD_VARIANT STREQUAL "hwspi-rgb888")
    # A follows the hardware-proven loader/helloworld SPI contract. The
    # transport and its CS-held window transaction live in the vendor driver;
    # src/display.cpp is only the public RGB565 adapter and verifier.
    set(PICOCALC_DISPLAY_SOURCE
        src/display.cpp
        vendor/lcd_hwspi_rgb888.cpp)
    set(PICOCALC_LCD_SYSTEM_CLOCK_KHZ 125000)
elseif(PICOCALC_LCD_VARIANT STREQUAL "pio-rgb565")
    # B links the unmodified vendored driver plus a thin adapter. The 250 MHz
    # system clock is the clock its clkdiv 2.0 was measured at.
    set(PICOCALC_DISPLAY_SOURCE
        src/display_pio_rgb565.cpp
        vendor/lcd_rgb565_pio.cpp)
    set(PICOCALC_LCD_SYSTEM_CLOCK_KHZ 250000)
else()
    message(FATAL_ERROR
        "PICOCALC_LCD_VARIANT must be hwspi-rgb888 or pio-rgb565")
endif()

add_library(picocalc_bsp STATIC
    src/bsp.cpp
    src/audio.cpp
    ${PICOCALC_DISPLAY_SOURCE}
    src/fatfs_diskio.cpp
    src/filesystem.cpp
    src/keyboard.cpp
    src/psram.cpp
    src/sdcard.cpp
    third_party/ChanFatFS/src/ff.c
    third_party/ChanFatFS/src/ffunicode.c
    vendor/audio_picoment/platform/picocalc_audio_pwm.cpp
    vendor/rp2040-psram/psram_spi.c
)

pico_generate_pio_header(picocalc_bsp ${CMAKE_CURRENT_LIST_DIR}/vendor/lcd_spi_min.pio)
pico_generate_pio_header(picocalc_bsp ${CMAKE_CURRENT_LIST_DIR}/vendor/rp2040-psram/psram_spi.pio)

# These pins are also generated into board_generated.h from the JSON profile.
# Keep the vendored C driver on the same fixed PicoCalc V2 wiring.
set(PICOCALC_PSRAM_CS 20)
set(PICOCALC_PSRAM_SCK 21)
set(PICOCALC_PSRAM_MOSI 2)
set(PICOCALC_PSRAM_MISO 3)
set_source_files_properties(
    vendor/rp2040-psram/psram_spi.c
    PROPERTIES COMPILE_OPTIONS "-Wno-format;-Wno-unused-variable"
)

file(READ "${CMAKE_CURRENT_LIST_DIR}/VERSION" PICOCALC_BSP_VERSION)
string(STRIP "${PICOCALC_BSP_VERSION}" PICOCALC_BSP_VERSION)
if(NOT DEFINED PICOCALC_APP_VERSION)
    set(PICOCALC_APP_VERSION "unknown")
endif()
if(NOT PICOCALC_BUILD_TIMESTAMP)
    string(TIMESTAMP PICOCALC_BUILD_TIMESTAMP UTC "%Y-%m-%dT%H:%M:%SZ")
endif()
if(NOT PICOCALC_BUILD_COMMIT)
    execute_process(
        COMMAND git rev-parse --short=12 HEAD
        WORKING_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/.."
        OUTPUT_VARIABLE PICOCALC_BUILD_COMMIT
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if(NOT PICOCALC_BUILD_COMMIT)
        set(PICOCALC_BUILD_COMMIT "untracked")
    else()
        execute_process(
            COMMAND git diff --quiet
            WORKING_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/.."
            RESULT_VARIABLE PICOCALC_GIT_DIFF_RESULT
        )
        if(NOT PICOCALC_GIT_DIFF_RESULT EQUAL 0)
            set(PICOCALC_BUILD_COMMIT "${PICOCALC_BUILD_COMMIT}-dirty")
        endif()
    endif()
endif()

target_include_directories(picocalc_bsp
    PUBLIC
        ${CMAKE_CURRENT_LIST_DIR}/include
        ${CMAKE_CURRENT_LIST_DIR}/third_party/ChanFatFS/include
    PRIVATE
        # Lets the adapter include "vendor/lcd_rgb565_pio.h" without editing the
        # vendored copy.
        ${CMAKE_CURRENT_LIST_DIR}
        ${CMAKE_CURRENT_LIST_DIR}/vendor/audio_picoment
)

target_compile_definitions(picocalc_bsp
    PUBLIC
        PICOCALC_BSP_ENABLE_SD_WRITE=1
        PICOCALC_BSP_VERSION=\"${PICOCALC_BSP_VERSION}\"
        PICOCALC_APP_VERSION=\"${PICOCALC_APP_VERSION}\"
        PICOCALC_BUILD_TIMESTAMP=\"${PICOCALC_BUILD_TIMESTAMP}\"
        PICOCALC_BUILD_COMMIT=\"${PICOCALC_BUILD_COMMIT}\"
        PICOCALC_LCD_VARIANT=\"${PICOCALC_LCD_VARIANT}\"
        PICOCALC_LCD_SYSTEM_CLOCK_KHZ=${PICOCALC_LCD_SYSTEM_CLOCK_KHZ}
        PSRAM_PIN_CS=${PICOCALC_PSRAM_CS}
        PSRAM_PIN_SCK=${PICOCALC_PSRAM_SCK}
        PSRAM_PIN_MOSI=${PICOCALC_PSRAM_MOSI}
        PSRAM_PIN_MISO=${PICOCALC_PSRAM_MISO}
)

target_compile_options(picocalc_bsp PRIVATE
    -Wall
    -Wextra
    -Werror=return-type
)

target_link_libraries(picocalc_bsp
    PUBLIC
        pico_stdlib
        hardware_clocks
        hardware_gpio
        hardware_i2c
        hardware_spi
        hardware_pio
        hardware_dma
        hardware_irq
        hardware_pwm
)
