# Host build of the Canonical PicoCalc BSP.
#
# Standalone on purpose: no Pico SDK, no cross toolchain, no board
# variant. Configure this directory directly.
#
#   cmake -S bsp/host -B build-host && cmake --build build-host
#   ./build-host/tests/emu_smoke
#
# The device build under bsp/CMakeLists.txt is untouched by anything
# here. It is hardware-verified; this is a second consumer of the same
# public API, not a change to it.

cmake_minimum_required(VERSION 3.13)
project(picocalc_bsp_host LANGUAGES C CXX)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug)
endif()

include(${CMAKE_CURRENT_LIST_DIR}/CMakeLists.host.txt)

enable_testing()
add_subdirectory(tests)
add_test(NAME emu_smoke COMMAND emu_smoke)
add_test(NAME sd_formats_test COMMAND sd_formats_test)
