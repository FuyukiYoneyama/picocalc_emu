# VRP-NES-0 synthetic NROM evidence

This is the local VRP-NES-0 preparation run for the repository-owned
synthetic NROM fixture.  It is a firmware validation evidence set, not a
hardware-correlation claim and not a `realtime-1x-qualified` claim.

The three runs used the same generated `TEST.NES`, the same diagnostic
NESco BIN, the same 64 MiB FAT32 source image, and the same clean
`picoem-picocalc` runner.  `run-report.json`, `uart.raw`, `sd-trace.json`,
`final.png`, and `flash-final.img` were compared across all three runs and
were byte-identical.  This directory stores the representative run; the
other two run directories were temporary and are not part of the evidence
artifact.

The run reached the M-NESCO oracle through `sd:/TEST.NES`, staged the image
to the emulated flash threshold, and reported `source_region=xip`,
`core1_xip=pass`, and `dma_xip=pass`.  The synthetic image SHA is recorded in
the UART marker and in the target contract.

The external NESco diagnostic commit is currently present only in the local
`codex/mnesco-extension` branch of the source workspace; the public remote
does not expose that ref yet.  Consequently the registry entry remains
`pending-revalidation`.  Once the exact commit is publicly reachable, the
target can be rechecked through the authoritative wrapper and promoted to
`active` without changing this evidence.
