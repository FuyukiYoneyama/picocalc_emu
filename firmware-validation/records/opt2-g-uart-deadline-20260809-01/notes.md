# OPT2-G UART exact scheduler lane

## Purpose

OPT2-G tested a feature-gated UART-only scheduler lane. The prototype preserves the normal
peripheral ordering and uses exact UART TX observable boundaries (including TXRIS and TX FIFO
pop/DREQ changes) while all non-UART peripherals are proven idle. It deliberately does not claim
actual running fast-forward: future CPU MMIO, clock changes, and DMA ordering are not proven safe.

The lane is fail-closed and diagnostic-only. Normal builds remain unchanged. The candidate is
exact but is rejected because the clean CPU-0-pinned A/B screening regressed wall time.

## Provenance

- clean baseline backend: `2671d0476c1a4286de7e3666bf91e20e27613854`
- clean candidate backend: `593e6d78541722920e1fa903e682d49912eae825`
- candidate feature: `uart-deadline-prototype`
- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- record: `opt2-g-uart-deadline-20260809-01`

- candidate revert: `335ecdd7f01cbc5d4f63e18403033bd629efbe77`;
- final backend content equals baseline `2671d0476c1a4286de7e3666bf91e20e27613854`;
- backend CI: run `31287315634`, test/fmt/Clippy all successful.

## Exactness

The canonical trace-on candidate run passed `scenario_done`, 927,528,660 cycles, 3,715,000 virtual
microseconds, and all 85 scenario steps. It matched the one-cycle reference on the observable
contract:

- UART SHA-256: `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer RGB565 SHA-256: `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- PSRAM tick count: `305747113`;
- behavior SHA-256: `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`;
- event stream SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`;
- event stream total: `173,498,680`, with all nine domains matching the OPT1-B reference.

The candidate proof counters were deterministic in all three candidate runs:

- `lane_calls=3,137,790`;
- `lane_cycles=6,268,797`;
- `temporal_tx_calls=3,127,577`;
- `first_tx_deadline_cycles=1`;
- `static_calls=10,213`.

## Performance screening

Trace-off clean release runners were executed in CPU-0-pinned A/B/A/B/A/B order, with no warmups.
Every run passed the same cycle, scenario, UART, framebuffer and PSRAM checks.

| run | variant | wall seconds |
|---|---|---:|
| A1 | baseline | 26.37 |
| B1 | candidate | 27.85 |
| A2 | baseline | 25.70 |
| B2 | candidate | 28.17 |
| A3 | baseline | 25.92 |
| B3 | candidate | 28.53 |

Baseline median was 25.92 s; candidate median was 28.17 s. The median change was `-8.6805555556%`
(8.681% slower), below the 5% promotion requirement. Pair changes were `-5.6124383769%`,
`-9.6108949416%`, and `-10.0694444444%`.

## Decision

Exactness passed, performance failed. The candidate was reverted; no active target or validation
attestation is changed. Actual running fast-forward remains unproven
because CPU MMIO and DMA observation/order boundaries are not predictable from the current
post-hoc instrumentation. OPT2 is closed without another promotion after missing its performance
threshold; the next work package is
OPT3 CPU/decode/execute block cache.
