# NEXT-2A frozen-backend first run

This directory preserves the first firmware execution of the independently generated
`picocalc-multicore` application. The expected phases and UART markers were frozen in
`firmware-validation/contracts/next2-multicore-v1.json` before the application was implemented.
The backend remained at the contract's promoted commit `e985a9d7...`.

## Outcome

The runner correctly returned exit code 1 and a fail-closed report:

- core 1 launch: PASS
- four bidirectional FIFO vectors: PASS
- WFE/SEV: FAIL (`before=2 after=2`; core 1 resumed before the intended core 0 SEV)
- `SIO_IRQ_PROC1`: FAIL (`count=0 word=0x00000000`)
- exception: absent
- unsupported MMIO: zero

The final framebuffer is intentionally retained. It clearly shows green PASS rows for LAUNCH and
FIFO and red FAIL rows for WFE/SEV, IRQ1, and OVERALL. No expected marker, vector, or pass rule was
changed to fit this result.

## Command

The runner was built from a clean checkout of backend commit `e985a9d7...` and invoked with the
canonical BIN, RP2040 B2 bootrom, PicoCalc board, PSRAM, keyboard, FAT32 SD, Serial execution,
quantum 1, a 1,000,000,000-cycle limit, the five frozen UART expectations, and final framebuffer,
UART, and JSON outputs enabled. The bootrom was passed by absolute path; a preceding invocation
that stopped before firmware execution because the runner's relative default bootrom path did not
resolve is an environment preflight error and is not classified as the first firmware run.

## Initial diagnosis and next experiment

The WFE observation does not yet prove a backend error. Core 0 used `sleep_ms(5)` between reading
the armed marker and sampling the shared stage. Pico SDK time/synchronization code may itself issue
SEV, which violates this test's requirement that no event occur before the application's explicit
SEV. The next application revision will replace that interval with a busy wait that cannot emit
SEV while preserving the frozen five-millisecond observation window and all expected values.

The backend contains WFE/event primitives, but the first-run source audit found no projection from
the SIO FIFO readable condition to the per-core NVIC `SIO_IRQ_PROC1` pending bit. That is a separate
candidate backend gap. It will only be changed after this failure record is committed, and it must
be covered by focused tests plus a rerun of the unchanged contract.
