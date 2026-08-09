# OPT2-F stationary pin-device bulk observation

## 目的

OPT2-Eは、空TX FIFOへの`PULL`で停止したPIO内部を閉形式で進めても、runnerが毎cycle
`tick_pio_and_route_irqs(1) + update_gpio()`を呼ぶため、全callが1 cycleに留まることを示した。
OPT2-FはPIO内部だけでなく、pinが変化しない区間のGPIO/PSRAM/LCD/SD観測をexactにまとめる。

性能より正確性を先に判定する。未知のdeviceを「同じ入力なら安全」と推測せず、device自身が
constant-pin bulk対応を明示しない限り従来のper-cycle loopへfallbackする。

## 参照する1-cycle順序

slow pathの各cycleは次の順である。

1. `tick_pio_and_route_irqs(1)`
2. SIOとPIOの`pad_out/pad_oe`をmerge
3. PSRAMがCS/SCK/MOSIを観測し、必要ならMISOをdrive
4. PIO LCDなどの`PinWatchingDevice`がpadを観測し、必要なら入力pinをdrive
5. external GPIO overrideを適用し、`bus.gpio_in`を更新
6. SPI接続deviceがCS/DC/RESETなどのside-band pinを観測

bulk pathも、この論理順序と最終drive値を変えてはならない。

## exact契約

`N > 1`の区間をまとめられるのは、次をすべて満たす場合だけである。

1. 少なくとも1つのPIO SMがenabledで、全enabled SMが空TX FIFOへの`PULL`で既に停止している。
2. `tick_peripherals`後からPIO/device観測終了までCPU/DMAはTX FIFOを補充できない。
3. PIO divider phase、stall counter、`FDEBUG.TXSTALL`、pad診断counterをN回実行と同値に更新する。
4. PIO `pad_out/pad_oe`は区間全体で一定で、PIO IRQ/FIFO/DREQも変化しない。
5. SIO出力とexternal GPIO overrideは区間内で一定である。
6. PSRAM、全`PinWatchingDevice`、SPI side-band deviceがconstant-pin bulk対応を明示している。
7. 各deviceは最初のsampleを通常の`tick/observe_pins`で処理する。したがって区間先頭の
   CS/SCK/RESET/DC edge、LCD partial-byte破棄、MISO切替は従来どおり1回発生する。
8. 残りN-1 sampleは最初と完全に同一で、自律的な時間遷移を持たない。PSRAMは
   `tick_count += N-1`を閉形式で補正する。
9. 複数deviceをまとめる場合、各deviceは同一入力に対して最初のsample後のdrive値が一定である。
10. behavior traceのcycle/order、UART、framebuffer、PSRAM/LCD/SD report counter、最終GPIO入力が
    reference pathと完全一致する。

## 必ずfallbackする境界

- active PIO命令、`WAIT`、RX-full、delay、autopull解除可能状態、TX FIFO refill
- CS/SCK/MOSI/DC/RESET/pad directionの区間内変化
- PSRAM command/address/data/read-delay/MISO shiftのedge
- LCD bit/byte/pixel/RAMWR/RAMRD/window transitionのedge
- deviceがconstant-pin bulk対応を宣言していない場合
- `N <= 1`

## featureと採否

試作は`stationary-pin-bulk-prototype` featureに隔離する。通常buildの分岐・counter・状態を増やさない。

採用には次が必要である。

1. device単体でN回referenceとbulk後の全状態・counter・drive値が一致する。
2. 既存PSRAM PIO edge-interleave回帰を含むbackend全試験が合格する。
3. PicoTetrisでcycle、85/85 scenario、behavior SHA、streaming event SHAと全9 domain、UART、
   framebuffer、PSRAM tickがOPT1-Bと一致する。
4. trace-OFFの交互A/Bでwall中央値を5%以上短縮する。未達なら候補をrevertし、active targetを変えない。

測定結果と最終採否は、実装後のimmutable evidence recordへ固定する。

## 実施結果（2026-08-09）

clean candidate `9ec1988ec4c5c4fa240a1f409ac9524364e017de`で試作した。PicoTetrisは
927,528,660 cycle、85/85、behavior/event SHA、全9 domain、UART、framebuffer、PSRAM tickが
OPT1-Bと完全一致した。外側bulkは23,199,887回成立し、37,012,745回の重複`update_gpio`を削減した。

CPU 0固定のclean trace-OFF 3 paired A/Bの中央値はbaseline 26.18秒、candidate 26.00秒で、短縮は
0.687547746%だった。5%採用条件に届かないため、exactnessは合格、性能は不採用とした。
candidateは`cdb7584`、前提PIO reapplyは`2671d04`で履歴を残してrevertし、active targetとpinは
変更していない。完全な証拠は
[`opt2-f-stationary-pin-bulk-20260809-01`](../firmware-validation/records/opt2-f-stationary-pin-bulk-20260809-01/notes.md)
に固定する。

次の独立候補はOPT2-Dで次点だったUART deadline promotionとする。CPU/decode block cacheは
計画どおりOPT3へ残す。
