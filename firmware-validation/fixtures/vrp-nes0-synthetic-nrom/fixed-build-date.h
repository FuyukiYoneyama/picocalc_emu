#pragma once

/* Keep the external NESco diagnostic BIN byte-stable across build times. */
#undef __DATE__
#undef __TIME__
#define __DATE__ "Jan 01 2026"
#define __TIME__ "00:00:00"
