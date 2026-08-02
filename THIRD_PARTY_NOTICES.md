# Third-Party Notices

The project as a whole is distributed under the MIT License in the root
`LICENSE` file, except for third-party components that retain their own
copyright notices and license terms.

## FatFs R0.14a

- Location: `bsp/third_party/ChanFatFS/`
- Copyright: Copyright (C) 2020, ChaN, all rights reserved.
- License: Redistribution and use in source and binary forms, with or without
  modification, are permitted provided that source redistributions retain the
  copyright notice, license condition, and disclaimer included in the FatFs
  source files.

The authoritative notice is preserved at the top of the FatFs source files,
including `bsp/third_party/ChanFatFS/src/ff.c`.

## rp2040-psram

- Location: `bsp/vendor/rp2040-psram/`
- Copyright: Copyright (c) 2023 Ian Scott
- License: MIT License

The full MIT notice is preserved in the vendored source files, including
`bsp/vendor/rp2040-psram/psram_spi.c`.

## Hardware-proven source derivatives

Parts of the canonical PicoCalc BSP were derived from the following projects,
all distributed under the MIT License by Fuyuki Yoneyama:

- `FuyukiYoneyama/picocalc-life`
- `FuyukiYoneyama/pico_skyace`
- `FuyukiYoneyama/Picocalc_ment`
- `FuyukiYoneyama/pico_rescue`

Exact source repositories, pinned commits, copied file paths, and SHA-256
fingerprints are recorded in `reference-projects/catalog.json`.

## Build-time dependencies

The project can be built with the Raspberry Pi Pico SDK and other external
tools. Those dependencies are not relicensed by this repository and remain
subject to their respective license terms.
