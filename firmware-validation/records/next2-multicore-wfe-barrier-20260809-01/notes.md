# NEXT-2A WFE barrier diagnosis

The first application correction replaced the core 0 `sleep_ms(5)` observation interval with a
busy wait. It did not change the result: core 1 still reached stage 2 before the intended explicit
SEV. A temporary, uncommitted diagnostic build of the frozen backend logged the exact core and PC
for SEV/WFE transitions. It showed repeated core 0 SEV at SRAM PC `0x20000250`, the copied
`mutex_exit` routine, after core 1 had already armed its WFE phase.

Application commit `be589cc5c039` added an internal FIFO prepare-word barrier. Core 0 now completes
all FIFO-result display and stdio work before releasing core 1 to publish the frozen armed marker.
The prepare word is internal synchronization; it does not alter the contract's four test vectors,
five required markers, or expected stage values.

With the frozen backend, the revised run changed only the intended phase result:

- launch: PASS
- four FIFO vectors: PASS
- WFE/SEV: PASS (`before=1 after=2`)
- IRQ_PROC1: FAIL (`count=0`)

Independent source inspection confirmed that Serial mode had constants for IRQ15/16 and SIO FIFO
state, but no connection from FIFO `VLD/WOF/ROE` to the core-local NVIC pending latch. Threaded mode
already had an immediate peer-pending path. The backend correction therefore belongs in the model,
not in the frozen application expectation.
