#pragma once

#include "config/build_config.h"
#include "platform/picocalc_uart_log.h"

#define PM_LOG_BOOT(fmt, ...) ::picoment::log_printf("BOOT", fmt, ##__VA_ARGS__)
#define PM_LOG_MAIN(fmt, ...) ::picoment::log_printf("MAIN", fmt, ##__VA_ARGS__)
#define PM_METRIC_INC(counter) (++(counter))
