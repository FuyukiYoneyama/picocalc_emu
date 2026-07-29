add_library(picocalc_bsp STATIC
    src/bsp.cpp
    src/display.cpp
    src/fatfs_diskio.cpp
    src/filesystem.cpp
    src/keyboard.cpp
    src/sdcard.cpp
    third_party/ChanFatFS/src/ff.c
    third_party/ChanFatFS/src/ffunicode.c
)

set(PICOCALC_BSP_VERSION "0.1.4")
if(NOT PICOCALC_BUILD_TIMESTAMP)
    string(TIMESTAMP PICOCALC_BUILD_TIMESTAMP UTC "%Y-%m-%dT%H:%M:%SZ")
endif()
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

pico_generate_pio_header(picocalc_bsp
    ${CMAKE_CURRENT_LIST_DIR}/src/lcd_spi_min.pio
)

target_include_directories(picocalc_bsp
    PUBLIC
        ${CMAKE_CURRENT_LIST_DIR}/include
        ${CMAKE_CURRENT_LIST_DIR}/third_party/ChanFatFS/include
)

target_compile_definitions(picocalc_bsp
    PUBLIC
        PICOCALC_BSP_ENABLE_SD_WRITE=1
        PICOCALC_BSP_VERSION=\"${PICOCALC_BSP_VERSION}\"
        PICOCALC_BUILD_TIMESTAMP=\"${PICOCALC_BUILD_TIMESTAMP}\"
        PICOCALC_BUILD_COMMIT=\"${PICOCALC_BUILD_COMMIT}\"
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
        hardware_pio
        hardware_spi
)
