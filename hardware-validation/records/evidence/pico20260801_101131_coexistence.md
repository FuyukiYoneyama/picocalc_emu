# PSRAM/LCD共存実機検証

- 元ログ: `/home/fuyuki/pico_dvl/codex/log/pico20260801_101131.log`
- BSP/app: `0.8.0` / `0.8.0-b-pio-rgb565-psram-lcd-coexist`
- commit: `9f4cd5cb254f4ff05c922ca78ffc8b3e22ac8555`
- system clock: 250 MHz
- LCD: `pio-rgb565`、PIO0 blocking、LCD DMAなし
- 検証量: 各候補120フレーム、24-byte write/read、16フレームごとにLCD RAMRD

| clkdiv | fudge | PSRAM clock | display_failures | psram_failures | status |
|---:|---:|---:|---:|---:|---|
| 1.0 | true | 125.0 MHz | 0 | 2788 | fail |
| 1.5 | true | 83.3 MHz | 0 | 0 | pass |
| 2.0 | true | 62.5 MHz | 0 | 2817 | fail |
| 3.0 | true | 41.7 MHz | 0 | 2869 | fail |
| 4.0 | true | 31.25 MHz | 0 | 2869 | fail |
| 1.0 | false | 125.0 MHz | 0 | 2879 | fail |
| 1.5 | false | 83.3 MHz | 0 | 933 | fail |
| 2.0 | false | 62.5 MHz | 0 | 0 | pass |
| 3.0 | false | 41.7 MHz | 0 | 0 | pass |
| 4.0 | false | 31.25 MHz | 0 | 2817 | fail |

LCDの全候補で120回の画面更新とRAMRD確認が成功した。PSRAMは3候補が合格し、
最初の合格候補である`clkdiv=1.5 / fudge=true / 約83.3 MHz`を試験終了後も
有効化した。UF2 SHA-256は
`eac8402aa45523536d6c4730860514e85d4a8ff091abc8465140809003c21914`。
