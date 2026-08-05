# Milestone 2's completion condition, as a runnable program.

add_executable(emu_smoke emu_smoke.cpp)
target_link_libraries(emu_smoke PRIVATE picocalc_bsp_host)
target_compile_options(emu_smoke PRIVATE -Wall -Wextra)

add_executable(sd_formats_test sd_formats_test.cpp)
target_link_libraries(sd_formats_test PRIVATE picocalc_bsp_host)
target_compile_options(sd_formats_test PRIVATE -Wall -Wextra)
