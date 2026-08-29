# VRP-NES-0: NES-class fixture preparation

Status: **local preparation complete; registry target pending public source revalidation**
Date: 2026-08-29

VRP-NES-0 supplies the NES-class workload required before a future
`realtime-1x-qualified` decision.  It deliberately uses a repository-owned
synthetic ROM rather than a cartridge dump or third-party game data.

## Fixture

The generator is [`tools/generate_vrp_nes0_nrom.py`](../../tools/generate_vrp_nes0_nrom.py).
It uses only the Python standard library and emits this exact image:

```text
path:   firmware-validation/fixtures/vrp-nes0-synthetic-nrom/TEST.NES
format: iNES NROM-256, mapper 0, trainer=1
parts:  512-byte trainer + 32 KiB PRG-ROM + 8 KiB CHR-ROM
bytes:  41488
sha256: 592e79406ebe9def8bed2c8c02b7a9f4fc51f5f2bf6562843a36d1e591468306
```

The reset program configures the PPU/APU, writes a palette and nametable
prefix, enables background rendering, and loops at a fixed address.  The
trainer intentionally makes the image reach NESco's Mapper-0 flash threshold;
the diagnostic run therefore exercises SD loading, flash staging, XIP reads,
core-1 probing, and DMA probing.  The SD input tree is the adjacent `sd/`
directory and contains only `TEST.NES`.

The generator and synthetic image are original project assets under the MIT
License (`firmware-validation/fixtures/vrp-nes0-synthetic-nrom/LICENSE`).
NESco source is not vendored by this fixture.

## Diagnostic firmware input

The run used the external `Picocalc_NESco` source at commit
`7f3fa05971930e03653694117cbf6a435ec1dd4e`, with
`NESCO_MNESCO_EXT_ORACLE=ON` and `NESCO_MNESCO_AUTOSTART_SD=ON`.  The source
workspace commit is on the local `codex/mnesco-extension` branch; as of this
record the public remote exposes no ref containing that commit.  This is why
the registry entry `vrp-nes0-synthetic-nrom` is `pending-revalidation` rather
than `active`.  No public qualification claim is made until a clean clone can
obtain the exact diagnostic commit.

The deterministic build used Pico SDK 2.2.0 (`a1438dff…`), GCC 13.2.1,
CMake 3.28.3, Ninja 1.11.1, and the repository-owned
`fixed-build-date.h`.  Two clean builds produced identical BIN and UF2:

```text
BIN  c6f5137ad76d8a6cb8e25825d6b30960c0e2fbfb3bdc543f4061686627edf40c
UF2  6631fb44232792be7625ae46e545d78df5dccd16fa00cfc17720df9046eed647
```

## Local evidence

The clean backend was `picoem-picocalc` commit
`65c795e87321e79b960ac8a7495a205de6a24ec0` (tracked worktree clean).  The
runner executed the same BIN and SD tree three times.  All three runs were
byte-identical for report, UART, SD trace, framebuffer PNG, and exported
flash image.  The representative run reached:

```text
stop:       scenario_done
cycles:     341758120 / 1000000000
UART SHA:   7d22e8ce6222deaf5251c247e3f1409afcc259cf16b14bd6d8f7ce91a84feffa
SD:         FAT32, 330 blocks read, 0 unknown commands
flash:      12 erases, 179 programs, 45824 programmed bytes, 0 errors
NES oracle: mapper=0, PRG=32768, CHR=8192, source_region=xip,
            core1_xip=pass, dma_xip=pass
```

Evidence, provenance, and SHA-256 inventory are fixed in
[`firmware-validation/evidence/vrp-nes0-synthetic-nrom-20260829-01/`](../../firmware-validation/evidence/vrp-nes0-synthetic-nrom-20260829-01/).
The target contract and validation attestation are
[`reference-projects/firmware-targets.json`](../../reference-projects/firmware-targets.json)
and
[`firmware-validation/validations/vrp-nes0-synthetic-nrom-r1.json`](../../firmware-validation/validations/vrp-nes0-synthetic-nrom-r1.json).

The evidence is a local firmware-run result only.  It is not hardware
correlation, does not change the promoted preview target, and does not enable
`realtime-1x-qualified`.

## Next action

Publish or otherwise make the exact diagnostic NESco commit reachable from a
clean source clone, then rerun the authoritative `picocalc.py test --mode
firmware` command using the registered target and `--sd-dir`.  Only after that
run passes with the pinned BIN/backend/scenario and the source provenance is
reproducible may this target move from `pending-revalidation` to `active` and
feed VRP-5 qualification.
