# ClockCalc / RP2040 SIO divider investigation evidence

Recorded 2026-10-12. **Diagnostic evidence, not an accepted target validation.**
See [the issue summary](../../../docs/RP2040_SIO_DIVIDER_BUG_20261012.md)
and [the backend issue](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/rp2040_sio_divider_bug_20261012.md).

## Preserved inputs and observations

- `initial-escape.json`: nine-step scenario used by baseline-v073,
  diagnostic-v077 and framing-v078; keyboard Esc code `0xb1`.
- `clock-transition.json`: longer first 0.8.77 scenario. Raw `+` is not the
  physical calculator plus binding, so its arithmetic step is not valid
  calculator evidence. Later scenarios removed that step.
- `baseline-v073/`, `clock-run/`, `diagnostic-v077/`, `framing-v078/`: byte-for-byte
  saved report, UART, runner log, I2C sidecar and PNG artifacts where present.
- `diagnostic-backend.patch`: only the isolated f810d059 worktree's post-run
  register/stack-printing addition. It does not alter divider execution.
- `build-info-v078.h`: exact generated identification for the observed BIN.
- `manifest.json`: artifact paths, sizes and SHA-256 values, backend/SDK/fixture
  identities and firmware hashes read from the original reports. Existing
  artifacts were copied after emulator cancellation; no scenario was rerun.

| Run | Backend state | Result and limitation |
| --- | --- | --- |
| baseline-v073 | clean f810d059 | Runner pass, but clock PNG retains calculator graphics; broad pixel assertion gives a false visual acceptance |
| clock-run | clean f810d059 | 0.8.77 fail; bad LCD command decoding and clock content; later input not processed |
| diagnostic-v077 | f810d059 with register-dump patch | 0.8.77 fail; division-loop PC `0x10016cca`, saved LR maps to pressure-compensation caller |
| framing-v078 | clean f810d059 | 0.8.78 fail; LCD COLMOD `0x65`, SLPOUT 1, but zero pixels in time region; division-loop PC `0x10016e40` |

Firmware source base: `814f346ec66f1c6ac66e43cd27f6d538fbb1535f`
in the external Picocalc_ClockCalc repository. The 0.8.77/0.8.78 builds were
dirty candidates; exact observed BIN hashes remain in each report. For 0.8.78:
git `814f346`, dirty `1`, time `2026-10-12 09:43:55 +0900`, purpose
`0.8.78-lcd-framing-trace`, UF2 SHA-256
`2a424475c43aea4220be83bcfeb40bd3bf5917b02515347b36bdf6939e78d2cb`.
The old BIN/UF2 and full external dirty source snapshot are not included here.
Rebuilding the external source base alone does not reproduce those candidates.

## Original runner conditions

Common options: Serial default build, `--board picocalc --lcd-variant pio-rgb565
--keyboard --quantum 1 --i2c-profile picocalc-rtc-env-v1` and
`--i2c-fixture firmware-validation/fixtures/i2c-ext-e5-env-v1.json`.
The fixture is already tracked in this repository; its hash is in the manifest.
The supplied B2 bootrom is identified by the report hash; direct boot does not
execute it. No PSRAM, SD or physical hardware operations were used.

The 0.8.78 run used the clean f810d059 runner copied before adding diagnostics:

```sh
picocalc-run --bin <exact-v078-BIN> --bootrom <RP2040-B2-ROM> \
  --backend-commit f810d059958773d1b42a1c6d03cc15183cdc1a4f \
  --board picocalc --lcd-variant pio-rgb565 --keyboard --quantum 1 \
  --i2c-profile picocalc-rtc-env-v1 \
  --i2c-fixture firmware-validation/fixtures/i2c-ext-e5-env-v1.json \
  --cycles 1200000000 --scenario <this-directory>/initial-escape.json \
  --snapshot-dir <new-output-directory> --uart <new-output-directory>/uart.log \
  --json <new-output-directory>/report.json \
  --i2c-report <new-output-directory>/i2c.json \
  --run-id clockcalc-v078-framing --progress-interval 10
```

This documents the past invocation, not a request to rerun it. Its exit 1 came
from the failed clock-content assertion at 2,680 ms, not the cycle limit.
The longer clock-run budget was 3,000,000,000 cycles; the other short runs
used 1,200,000,000. Exact limits and stop reasons are in each report.

## Diagnosis and closure limits

Source inspection establishes omitted recalculation on DIV_UDIVIDEND and
DIV_SDIVIDEND in both inspected backend revisions. SDK documentation and its
divisor-first reciprocal sequence establish why that implementation is wrong.
The saved pressure-compensation PC/UART/register state supports the stall
explanation, but no corrected-divider run was performed. This evidence is
not proof of the cause or recovery of the user's physical LCD failure.

Before accepting a correction, verify both operand orders and aliases,
per-core isolation and SDK 64-bit division. Then require sensor completion,
actual expected clock glyphs and subsequent input processing. Non-black counts
and CPU-side LCD completion are insufficient acceptance criteria.
