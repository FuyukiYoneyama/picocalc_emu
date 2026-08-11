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

The audio driver derived from `FuyukiYoneyama/Picocalc_ment` contains documented
BSP-specific changes for cross-core SPSC accounting, drain/restart handling,
quantizer state correction, and an exactly equivalent wrap-255 reconstruction
optimization. The change history and reasons are recorded in
`bsp/CHANGELOG.md` and `bsp/vendor/README.md`.

## ClockworkPi PicoCalc official sample code

- Upstream: <https://github.com/clockworkpi/PicoCalc>
- Referenced source: `Code/picocalc_helloworld/lcdspi/lcdspi.c` and its headers
- Affected file in this repository: `bsp/vendor/lcd_hwspi_rgb888.cpp` (LCD variant A)
- Upstream license: **not stated.** As of 2026-08-03 the upstream repository
  contains no `LICENSE` file, GitHub reports no detected license for it, and
  `lcdspi.c` carries no copyright header.

`bsp/vendor/lcd_hwspi_rgb888.cpp` is an independent implementation written for
this repository. The comparison was checked on 2026-08-03 against
`clockworkpi/PicoCalc` upstream `HEAD`
`e8e38aa4b502d31a0d789911bbd84ec9eb0068b9`. The official `lcdspi.c` at that
revision has Git blob ID `1c683dc0c921ee5a0fa7cc9e08981c548449d0b1`; the local
reference checkout used for the comparison contains the same blob even though
its repository `HEAD` is different.

The comparison produced these engineering observations:

1. **Code: not copied.** `lcd_hwspi_rgb888.cpp` is 275 lines, `lcdspi.c` is 715.
   They share four non-trivial identical lines, all Pico SDK boilerplate
   (`tight_loop_contents();`, `sleep_ms(120);` twice, `reset_controller();`).
   The longest contiguous identical run is three lines, two of which are `}`.
2. **Initialization register values: identical and also published elsewhere.**
   Both files write the same ILI9488 initialization sequence, including the two
   15-byte gamma tables. The identical bytes are also published in Bodmer's `TFT_eSPI`
   (`TFT_Drivers/ILI9488_Init.h`) — E0 `00 03 09 08 16 0A 3F 78 4C 09 0A 08 16
   1A 0F`, E1 `00 16 19 03 0F 05 32 45 46 04 0E 0D 35 37 0F`, C0 `17 15`,
   C1 `41`, C5 `00 12 80`, `3A`=`66`, B0 `00`, B1 `A0`, B4 `02`, B6 `02 02 3B`.
   This establishes that the command/value sequence is not unique to the
   ClockworkPi repository. It does not by itself determine authorship or license.

No ClockworkPi file is vendored in this repository. The line comparison above is
recorded as provenance evidence, not as a legal conclusion.

**License boundary — GPL-3.0 code is not included.** `lcdspi.c` itself has no
copyright header and no stated origin, but the same file is distributed by
third parties under GPL-3.0: `madcock/uf2loader` ships
`common/lcdspi/lcdspi.c` (772 lines, differing from the ClockworkPi copy by 135
lines) under GPL-3.0 and credits `clockworkpi/PicoCalc` in its README, and the
project it is based on, `adwuard/Picocalc_SD_Boot`, is also GPL-3.0. The file
additionally retains MMBasic/PicoMite-style identifiers (`gui_fcolour`,
`gui_bcolour`, `MainFont`), suggesting a further upstream that has not been
identified.

The release decision is to keep `lcd_hwspi_rgb888.cpp` as an independently
implemented MIT-licensed adapter and not incorporate `lcdspi.c`. The adapter
was written from the public ILI9488/Pico SDK protocol and the engineering
comparison above found no copied ClockworkPi source. The GPL-3.0 repositories
are cited only as provenance investigated during review; no GPL source or
derived file is redistributed here. Two standing rules enforce that boundary:

- **Do not vendor `lcdspi.c`**, or any file derived from it, into this
  MIT-licensed repository.
- **Do not vendor `Code/picocalc_helloworld`** — neither its source nor its
  built artifacts. It is built and run locally by each verifier; this
  repository records only the result and the identity needed to reproduce it.
  If a distributable fixture is ever needed, write an equivalent sample
  in-house (see [`docs/history/EMULATOR_ROADMAP.md`](docs/history/EMULATOR_ROADMAP.md) §2.1).

If future work needs to incorporate ClockworkPi source rather than observe its
hardware protocol, its license must be resolved before that source or a derived
artifact is distributed. This notice records the engineering provenance and
distribution boundary; it is not legal advice or a legal determination.

Note that `bsp/vendor/rp2040-psram/` reached this project through the same
official sample, but it is separately licensed MIT by Ian Scott — the upstream
repository ships `Code/picocalc_helloworld/rp2040-psram/LICENSE` — and is
recorded under its own heading above.

## Build-time dependencies

The project can be built with the Raspberry Pi Pico SDK and other external
tools. Those dependencies are not relicensed by this repository and remain
subject to their respective license terms.
