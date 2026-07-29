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
