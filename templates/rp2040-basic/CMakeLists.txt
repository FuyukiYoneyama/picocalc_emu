cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED ENV{PICO_SDK_PATH})
    message(FATAL_ERROR "PICO_SDK_PATH is not set")
endif()

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(picocalc_app C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
option(PICOCALC_AUDIO_REFERENCE_TONE
    "Use the copied Picocalc_ment fixed-sine reference path" ON)
option(PICOCALC_PSRAM_LCD_COEXIST_TEST
    "Run the PSRAM clock/LCD update coexistence test" OFF)
set(PICOCALC_LCD_VARIANT "pio-rgb565" CACHE STRING
    "LCD BSP variant: hwspi-rgb888 or pio-rgb565")
if(PICOCALC_PSRAM_LCD_COEXIST_TEST AND
   NOT PICOCALC_LCD_VARIANT STREQUAL "pio-rgb565")
    message(FATAL_ERROR
        "PICOCALC_PSRAM_LCD_COEXIST_TEST requires PICOCALC_LCD_VARIANT=pio-rgb565")
endif()
if(NOT DEFINED PICOCALC_APP_VERSION)
    if(PICOCALC_PSRAM_LCD_COEXIST_TEST)
        set(PICOCALC_APP_VERSION "0.8.1-b-pio-rgb565-psram-lcd-coexist")
    elseif(PICOCALC_LCD_VARIANT STREQUAL "pio-rgb565")
        set(PICOCALC_APP_VERSION "0.8.1-b-pio-rgb565-default")
    else()
        set(PICOCALC_APP_VERSION "0.8.1-a-hwspi-rgb888-rgb666-compat")
    endif()
endif()

pico_sdk_init()

# A generated project contains its own pinned BSP copy. The fallback keeps this
# source template directly buildable from the picocalc_emu repository.
if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/bsp/CMakeLists.txt")
    set(PICOCALC_BSP_DIR "${CMAKE_CURRENT_LIST_DIR}/bsp")
else()
    set(PICOCALC_BSP_DIR "${CMAKE_CURRENT_LIST_DIR}/../../bsp")
endif()
add_subdirectory("${PICOCALC_BSP_DIR}" picocalc_bsp_build)

add_executable(picocalc_app
    app/main.cpp
)

target_link_libraries(picocalc_app PRIVATE picocalc_bsp)

target_compile_definitions(picocalc_app PRIVATE
    PICOCALC_PSRAM_LCD_COEXIST_TEST=$<BOOL:${PICOCALC_PSRAM_LCD_COEXIST_TEST}>)

pico_enable_stdio_usb(picocalc_app 1)
pico_enable_stdio_uart(picocalc_app 1)
pico_add_extra_outputs(picocalc_app)
