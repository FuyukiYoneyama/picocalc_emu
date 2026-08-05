# Third-Party Notices

This generated project is distributed under the MIT License in `LICENSE`,
except for the third-party components below, which retain their own notices
and terms.

## FatFs R0.14a

- Location: `bsp/third_party/ChanFatFS/`
- Copyright: Copyright (C) 2020, ChaN, all rights reserved.
- License: the redistribution terms preserved in
  `bsp/third_party/ChanFatFS/LICENSE.txt` and the source headers apply.

## rp2040-psram

- Location: `bsp/vendor/rp2040-psram/`
- Copyright: Copyright (c) 2023 Ian Scott
- License: MIT License, preserved in the vendored source headers.

## Canonical PicoCalc BSP provenance

The BSP was copied from `FuyukiYoneyama/picocalc_emu`. Its exact source commit,
version, dirty-state disclosure, and content SHA-256 are recorded in
`.picocalc-project.json`. Parts of the BSP were derived from these MIT-licensed
projects by Fuyuki Yoneyama:

- `FuyukiYoneyama/picocalc-life`
- `FuyukiYoneyama/pico_skyace`
- `FuyukiYoneyama/Picocalc_ment`
- `FuyukiYoneyama/pico_rescue`

`bsp/vendor/lcd_hwspi_rgb888.cpp` is an independent implementation. No source
file from ClockworkPi's `Code/picocalc_helloworld` is included. The official
repository did not state a repository license when reviewed on 2026-08-03, so
official source must not be copied into this project without resolving its
license first.

## Build-time dependencies

The Raspberry Pi Pico SDK and other external build tools are not included or
relicensed by this project and remain subject to their own license terms.
