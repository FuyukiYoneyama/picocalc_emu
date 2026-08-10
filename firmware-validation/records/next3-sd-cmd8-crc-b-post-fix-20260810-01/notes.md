# NEXT3 SD CMD8 CRC Fault B post-fix result

Backend `5edca80` implements mandatory command CRC7 validation for CMD0 and
CMD8. The exact Fault B BIN that hardware rejected is unchanged. The corrected
backend now returns R1 `0x09`, no R7 payload, `cmd8_fail detail=9`, and the same
red application FAIL state observed on the physical PicoCalc. The reason match
is exact, so this versioned observation is `correct_negative_detection`.

The A1 correct-CRC BIN was also run on the same backend. Its UART and green
snapshot are byte-identical to the pre-fix A1 evidence, with CMD8 R1 `0x01`, R7
`000001aa`, and application PASS. All backend workspace tests and the focused
Clippy/format checks passed locally.

The earlier frozen-backend observation remains a separate immutable record. It
continues to prove that backend `4a908648` false-accepted this case. The KPI in
this directory describes the corrected backend; the preceding KPI preserves
the first-run 0/1 detection and 1/1 false-accept snapshot. Neither rate is a
general population estimate.
