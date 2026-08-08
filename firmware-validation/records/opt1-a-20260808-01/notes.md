# OPT1-A exact idle fast-forward candidate

**Record:** `opt1-a-20260808-01`

**Backend:** `picoem-picocalc` `c68c58f6c37fb31eb9313566c8b16883db9063b6`

**Target:** `picotetris-opt1a` revision 3
**Result:** candidate pass; R5 hardware correlation is not complete

## Implemented boundary

The PicoCalc runner now calls `Emulator::step_until()` with the earlier of the next scenario poll
and the cycle limit. A jump is considered only while both cores are halted or WFE-blocked. TIMER
alarm, PWM wrap, and caller-owned external boundaries have exact horizons. Every active source
without a promoted exact deadline contributes a one-cycle fallback. Static state may remain
present, but a pending wake-capable IRQ or unresolved temporal source prevents a long jump.

At a selected boundary the implementation preserves the established order: master clock update,
bulk peripheral tick, IRQ routing, and wake checks. Ordinary `step()` retains its prior quantum
contract; the optimization is connected only through the PicoCalc runner's explicit external
boundary.

## behavior schema 2 correction

The first trace comparison exposed an existing contract defect. Schema 1 recorded UART source 1
when the host harness drained its diagnostic UART buffer every 256 step calls. Exact fast-forward
changes the number of host dispatches, so identical guest UART writes were grouped into a different
number of host-drain events. This was not an emulated device difference.

Schema 2 records each accepted `UARTDR` write through a behavior-only tap at the emulator step
boundary. The harness diagnostic drain remains independent. A full one-cycle reference run and the
fast-forward candidate then produced byte-identical behavior projections:

- behavior SHA-256: `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`
- event stream SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- total events: `173,498,680`
- all nine domain event counts and hashes: identical

The old OPT0-B schema 1 artifact remains unchanged as historical evidence.

## Normal exactness result

Ten trace-OFF performance runs all passed the registered normal contract and were deterministic.

| Observation | Result |
|---|---:|
| scenario | 85 / 85 pass |
| cycles | 927,528,660 |
| virtual time | 3,715,000 us |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer SHA-256 | `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2` |
| timeline SHA-256 | `50eb1f6c7382b9c5d4f7764b8825a7aa641bbb744433899c6d644108e6be2dd1` |

These values are identical to the prior PicoTetris behavioral baseline. The normalized report hash
changes because it correctly includes the new backend commit provenance.

## Performance result

The measurement used the same WSL host and CPU 0 as the R5 preflight baseline, a release build,
trace OFF, one excluded warm-up, and ten measured runs.

| Metric | Baseline | OPT1-A | Change |
|---|---:|---:|---:|
| median wall time | 63.2470 s | 27.1229 s | -57.116% |
| median real-time ratio | 5.8738% | 13.6970% | 2.3319x |
| median emulated cycle/s | 14.665 M | 34.197 M | 2.3319x |

Run 9 experienced a host-side outlier (41.711 s). It is retained rather than discarded. The median
is robust to it, and the candidate mean 95% interval (25.273–31.932 s) remains entirely below the
baseline mean 95% interval (62.162–64.929 s).

This clears the candidate correctness, determinism, and performance gates. It does not promote the
optimization as hardware-correlated; that decision belongs to R5.

## Additional workload

Template B was regenerated from the pinned real Git source checkout into a Git-external project.
Its BIN `1e6abac2…` and UF2 `1ab0d16f…` matched the registry. The OPT1-A backend passed the normal
contract. Against the one-cycle backend, the report after removing only backend provenance and the
UART bytes were byte-identical. A single screening run decreased from 70.55 s to 26.37 s. These two
times are not presented as a formal repeated benchmark; they establish that this different device
configuration did not regress and that its behavior remained equal.
