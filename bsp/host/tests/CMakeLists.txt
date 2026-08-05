# Milestone 2's completion condition, as a runnable program.

add_executable(emu_smoke emu_smoke.cpp)
target_link_libraries(emu_smoke PRIVATE picocalc_bsp_host)
target_compile_options(emu_smoke PRIVATE -Wall -Wextra)
