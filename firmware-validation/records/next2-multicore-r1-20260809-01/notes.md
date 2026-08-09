# NEXT-2A multicore formal emulator acceptance

The acceptance values were frozen before the application was implemented in
`firmware-validation/contracts/next2-multicore-v1.json`. The first run against the then-promoted
backend was preserved as a failure. It isolated the missing Serial-mode projection from SIO FIFO
`VLD/WOF/ROE` to the receiving core's local NVIC line.

Backend commit `38683d65800ef36026f674dd47228024d69eb5e7` implements that level-sensitive,
core-local projection without using the shared peripheral IRQ bitmap. It also makes a fatal NMI or
HardFault on core 1 stop the harness fail-closed. The runner was rebuilt after the commit in a fresh
Cargo target directory, so the report's compile-time backend identity is the committed clean source.

Application commit `9dfb04e1ed6bb4600b4ce4ade6a3a6b72c321837` never returns from the core 1 entry.
The fixed FIFO vectors, WFE/SEV stages and SIO IRQ input remain exactly those in the frozen contract.

Three independent firmware executions used the normal `tools/picocalc.py test --mode firmware
--target picocalc-multicore-r1` path and `scenarios/next2-multicore-v1.json`. They stopped at the
same cycle after the frozen overall-PASS marker, and their raw reports, UART byte streams, scenario
step timelines and PNG snapshots are byte-identical. Two separate clean clones of the application
also reproduced the canonical BIN and UF2 exactly with Pico SDK 2.2.0, Ninja and the fixed timestamp.

This record accepts Serial execution only. Threaded execution, concurrent LCD/PSRAM access from both
cores, spinlock contention timing, core 1 relaunch and DMA-paced PCM remain outside NEXT-2A. Physical
PicoCalc correlation still requires the same UF2, a complete UART log and one final PASS photograph.
