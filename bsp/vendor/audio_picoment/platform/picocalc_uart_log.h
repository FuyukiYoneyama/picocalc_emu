#pragma once

#include <stdarg.h>
#include <stdio.h>

namespace picoment {

inline void log_printf(const char* scope, const char* format, ...) {
    printf("[PICOCALC][AUDIO][%s] ", scope);
    va_list args;
    va_start(args, format);
    vprintf(format, args);
    va_end(args);
    putchar('\n');
}

}  // namespace picoment
