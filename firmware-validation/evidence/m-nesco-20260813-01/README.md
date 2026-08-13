# M-NESCO-S1 direct-boot SD/flash debug evidence

Date: 2026-08-13

This is the scoped M-NESCO-S1 gate. It establishes that `Picocalc_NESco` can
be debugged through the existing direct-boot path while using the new RAW SD
and flash erase/program semantics. It does **not** claim `uf2loader` support,
boot2/watchdog support, directory import, or full multi-mapper NES coverage.

## Inputs

- Firmware source commit: `ce67aa76e86dec700f086cd70214c247d6317da8`
- Firmware: `Picocalc_NESco.bin`
- Firmware SHA-256: `ce865f2a26fecc55cfd033abfc71590c9918499c477fee81897f7ca5ababeb1c`
- Backend commit: `ae49c6c090dbd26c08c8360821cc6b2cc2c66dbe`
- Backend working tree: clean (`dirty=false`)
- Bootrom SHA-256: `9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81`
- SD fixture: 64 MiB FAT32 RAW image, source SHA-256
  `95fedb2fa5b83a08c8480bb1da654bd25a03f0005fc5471c6606d4180b2f65e0`

The fixture contains a deterministic second menu entry (`TEST.NES`). The
scenario sends Down and Enter after the menu settles; no host directory or
external binary is required at runtime.

## Result

The attached `report.json` and `stderr.txt` show:

- execution model `Serial`, boot mode `direct_boot_from_flash`, scenario exit 0;
- 1,316,021,684 cycles and 5.3 s of virtual scenario time;
- SD FAT32: 341 commands, 332 block reads, 0 unknown commands;
- flash: 12 erases, 179 page programs, 45,824 programmed bytes, 0 unknown
  commands, 0 mutation errors;
- four key events delivered with no drops or overwrites;
- final flash image exported atomically by the runner.

The exported artifacts were deliberately kept out of Git because they are
large generated inputs. Their hashes are `flash-after.bin` =
`21a3dc0bb82d7ad786df0eb8d5484703b489039528d8898f6736bd91734754dd` and
`sd-out.img` =
`95fedb2fa5b83a08c8480bb1da654bd25a03f0005fc5471c6606d4180b2f65e0`.

The screen snapshot and UART are retained as run evidence. The exported
2 MiB flash and 64 MiB SD images are not tracked; their identities are in the
report and can be regenerated from the pinned inputs.

## Scope boundary

This gate is sufficient to begin `Picocalc_NESco` direct-boot debugging with
RAW SD and flash mutation support. It is intentionally narrower than the
later M-NESCO extension: multiple ROM sizes/mappers, complete run-to-run
flash reattach comparison, directory snapshot import, boot2, watchdog warm
reset, and the real `uf2loader` end-to-end scenario remain U3+ work.
