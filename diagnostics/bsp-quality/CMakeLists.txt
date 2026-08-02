cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED ENV{PICO_SDK_PATH})
    message(FATAL_ERROR "PICO_SDK_PATH is not set")
endif()

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(PicoCalc_BSP_Diagnostic C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(PICOCALC_APP_VERSION "0.8.8-hv1-lcd-keyboard")
set(PICOCALC_UF2_NAME "PicoCalc_BSP_Diagnostic" CACHE STRING
    "Fixed local hardware-validation artifact name" FORCE)
set(PICOCALC_LCD_VARIANT "pio-rgb565" CACHE STRING
    "LCD BSP variant" FORCE)
set(PICOCALC_AUDIO_REFERENCE_TONE OFF CACHE BOOL
    "HV-1 must remain silent" FORCE)
option(PICOCALC_PSRAM_LCD_COEXIST_TEST
    "Accepted for picocalc.py compatibility; unused by this focused diagnostic" OFF)
if(PICOCALC_PSRAM_LCD_COEXIST_TEST)
    message(FATAL_ERROR "HV-1 is a focused LCD readback/keyboard diagnostic")
endif()

pico_sdk_init()

add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../../bsp" picocalc_bsp_build)

add_executable(picocalc_app app/main.cpp)
set_target_properties(picocalc_app PROPERTIES OUTPUT_NAME "${PICOCALC_UF2_NAME}")

target_link_libraries(picocalc_app PRIVATE
    picocalc_bsp
    hardware_watchdog
)

target_compile_definitions(picocalc_app PRIVATE PICO_USE_STACK_GUARDS=1)
target_compile_options(picocalc_app PRIVATE
    -Wall
    -Wextra
    -Werror
    -fstack-usage
)
target_link_options(picocalc_app PRIVATE
    "-Wl,-Map=${CMAKE_BINARY_DIR}/${PICOCALC_UF2_NAME}.map"
)

pico_enable_stdio_usb(picocalc_app 1)
pico_enable_stdio_uart(picocalc_app 1)
pico_add_extra_outputs(picocalc_app)
