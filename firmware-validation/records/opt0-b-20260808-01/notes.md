# OPT0-B behavior / streaming event contract — 2026-08-08

## Provenance

| Item | Value |
|---|---|
| backend | `picoem-picocalc` `763595fedefa08886b41298be79bff69324ac51f`, clean |
| firmware source | `picotetris` `fed84f358d7dcadb1457752e687355ddb1875c48`, clean detached checkout |
| firmware SHA-256 | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| UF2 SHA-256 | `44ec62270175aac16add07ca8d7c99abb0942bcff341c4c36c0d884fc857e274` |
| scenario SHA-256 | `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208` |
| execution | Serial, release, quantum 1, behavior-trace feature |
| normal report SHA-256 | `8e583d9526903bc9e4254a0818cd9dcca89fa2d289aff768273743fca12f054a` |
| behavior artifact SHA-256 | `6a4e9c09afb3870eda6fd04ecef0016f740fd1138fbf417b6e3a8dfc4c2a1160` |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |

The pinned BIN and UF2 were regenerated from the detached source and matched the target registry.
Two complete trace-ON runs produced byte-identical normal reports, behavior artifacts, and UART
streams. A third run from a release binary built without `behavior-trace` produced the same normal
report and UART bytes as trace ON. The trace artifact is diagnostic and explicitly invalid for
wall-time measurement.

## Correctness result

- verdict `pass`, stop `scenario_done`, scenario 85/85;
- 927,528,660 master cycles and 3,715,000 us virtual time;
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- `behavior_sha256` `3ee0dff39b10b5863aa28326189f70ba553e714c1e9ada403db1ad4622a1daf3`;
- event stream SHA-256 `448b0a00575b6748445906a5863c508f2fb86910fba73137605d66147bd191d9`;
- 173,498,252 streamed events, with no retained event array.

## Domain counts

| Domain | Events | SHA-256 |
|---|---:|---|
| clock | 8 | `02e8ed8493ac5744dbe0b5ceb9d35cea7a833c71a5d95b3015c04794f5ef745e` |
| irq_exception | 1,110 | `28d4f352734c14fb9afec06fce2403951c0346e36f62f35449d82e44e329139a` |
| pio_gpio | 1 | `61d3af30a4d6209d193fd498a1296c7c77c72b816cd62b87bbe6eeca57abd996` |
| psram | 85,621,393 | `841fc3983f5c5f86ebcc3062c17ad2992c5b3ac1fe090ec0e04981ee6f57515a` |
| lcd | 84,708,286 | `f9ee81d6c0940e81310058a715e29f718f4123f059a30f49314ac547b0bb118a` |
| dma_dreq | 82 | `64a7e5d3e1d2d89a451c90ade5ac571d92d6c6ee5337ab94c5d515476627bdfb` |
| timer_pwm | 3,154,379 | `d6cddb9698ccc86c1564b9f25471f0be5eeae4541458cd554102f7a96c285fcd` |
| serial_bus | 12,847 | `468b89947f3868d88bd1014806245250f0ccb30f195c0c2f0397d5aa3c4551db` |
| scenario_input | 146 | `6a15d009a3eedbaec4ea647d205233289ae163303079afb71f18f39b24e6b4f0` |

The full machine-readable values are in `behavior-trace.json`; the unchanged schema 8 output is in
`run-report.json`. OPT0-B is complete. OPT1-A exact idle fast-forward is next.
