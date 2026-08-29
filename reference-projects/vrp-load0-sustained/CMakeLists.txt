cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED ENV{PICO_SDK_PATH})
    message(FATAL_ERROR "PICO_SDK_PATH is not set")
endif()

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(vrp_load0_sustained C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(PICOCALC_APP_VERSION "vrp-load0-r1")
set(PICOCALC_LCD_VARIANT "pio-rgb565" CACHE STRING
    "LCD BSP variant: hwspi-rgb888 or pio-rgb565")
set(VRP_LOAD0_DURATION_SECONDS "120" CACHE STRING
    "Virtual duration of this versioned workload in seconds")
option(PICOCALC_PSRAM_LCD_COEXIST_TEST
    "Run the PSRAM clock/LCD update coexistence test" OFF)
if(PICOCALC_PSRAM_LCD_COEXIST_TEST)
    message(FATAL_ERROR
        "VRP-LOAD-0 is not compatible with PICOCALC_PSRAM_LCD_COEXIST_TEST")
endif()

if(NOT VRP_LOAD0_DURATION_SECONDS MATCHES "^[1-9][0-9]*$")
    message(FATAL_ERROR "VRP_LOAD0_DURATION_SECONDS must be a positive integer")
endif()

# VRP-LOAD-0 exercises the public 48 kHz stream path, not the fixed reference
# tone.  Keep this choice in the source project so a plain CMake build cannot
# silently turn the workload into a tone-only smoke test.
set(PICOCALC_AUDIO_REFERENCE_TONE OFF CACHE BOOL
    "Use the copied Picocalc_ment fixed-sine reference path" FORCE)

pico_sdk_init()

# This project is intentionally repository-owned and builds against the
# canonical BSP in the same clean clone.  The build command pins the source
# commit and toolchain; it does not create or modify any external project.
add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../../bsp" picocalc_bsp_build)

add_executable(picocalc_app
    app/main.cpp
)

target_compile_definitions(picocalc_app PRIVATE
    VRP_LOAD0_DURATION_SECONDS=${VRP_LOAD0_DURATION_SECONDS})

target_link_libraries(picocalc_app PRIVATE
    picocalc_bsp
    pico_multicore)

pico_enable_stdio_usb(picocalc_app 1)
pico_enable_stdio_uart(picocalc_app 1)
pico_add_extra_outputs(picocalc_app)
