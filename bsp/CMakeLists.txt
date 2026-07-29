set(PICOCALC_LCD_VARIANT "hwspi-rgb888" CACHE STRING
    "LCD BSP variant: hwspi-rgb888 or pio-rgb565")
set_property(CACHE PICOCALC_LCD_VARIANT PROPERTY STRINGS
    hwspi-rgb888 pio-rgb565)

if(PICOCALC_LCD_VARIANT STREQUAL "hwspi-rgb888")
    set(PICOCALC_DISPLAY_SOURCE src/display.cpp)
elseif(PICOCALC_LCD_VARIANT STREQUAL "pio-rgb565")
    set(PICOCALC_DISPLAY_SOURCE src/display_pio_rgb565.cpp)
else()
    message(FATAL_ERROR
        "PICOCALC_LCD_VARIANT must be hwspi-rgb888 or pio-rgb565")
endif()

add_library(picocalc_bsp STATIC
    src/bsp.cpp
    ${PICOCALC_DISPLAY_SOURCE}
    src/fatfs_diskio.cpp
    src/filesystem.cpp
    src/keyboard.cpp
    src/sdcard.cpp
    third_party/ChanFatFS/src/ff.c
    third_party/ChanFatFS/src/ffunicode.c
)

pico_generate_pio_header(picocalc_bsp ${CMAKE_CURRENT_LIST_DIR}/src/lcd_spi_min.pio)

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
)

target_compile_definitions(picocalc_bsp
    PUBLIC
        PICOCALC_BSP_ENABLE_SD_WRITE=1
        PICOCALC_BSP_VERSION=\"${PICOCALC_BSP_VERSION}\"
        PICOCALC_APP_VERSION=\"${PICOCALC_APP_VERSION}\"
        PICOCALC_BUILD_TIMESTAMP=\"${PICOCALC_BUILD_TIMESTAMP}\"
        PICOCALC_BUILD_COMMIT=\"${PICOCALC_BUILD_COMMIT}\"
        PICOCALC_LCD_VARIANT=\"${PICOCALC_LCD_VARIANT}\"
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
)
