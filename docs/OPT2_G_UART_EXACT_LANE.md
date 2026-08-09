# OPT2-G UART exact scheduler lane

## 結論

OPT2-GのUART-only scheduler laneは、canonical PicoTetris実行でexactnessに合格した。しかし
CPU 0固定のclean A/B/A/B/A/B screeningではbaseline中央値25.92秒に対してcandidate 28.17秒、
`-8.6805555556%`（8.681%退行）となったため、不採用・revert済みとする。

実際のrunning fast-forwardは実装していない。CPU MMIO、clock変更、DMAの将来orderingを事前に
証明できないため、feature-gatedかつfail-closedのUART-only laneだけを試作した。

## 対象と実装境界

candidate backendは`593e6d78541722920e1fa903e682d49912eae825`、baselineは
`2671d0476c1a4286de7e3666bf91e20e27613854`。candidate featureは
`uart-deadline-prototype`のみである。

laneは、非UART peripheralがidleである場合にUART TXのobservable boundaryを通常のUART0→UART1
orderingで処理する。TXRISの一cycle境界、TX FIFO pop、FIFO由来DREQを対象にする。CPUが将来
UART MMIOを書く可能性や、DMAが同一boundaryでFIFOをrefillするorderingは安全なrunning horizon
とはみなさない。通常経路はfeature OFFで変更しない。

proof countersは全candidate runで同一だった。

- `lane_calls=3,137,790`
- `lane_cycles=6,268,797`
- `temporal_tx_calls=3,127,577`
- `first_tx_deadline_cycles=1`
- `static_calls=10,213`

## canonical exactness

firmwareはSHA-256 `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`、scenarioは
`tetris-line-clear.json`（SHA-256 `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`）を使用した。
boardは`picocalc`、LCDは`pio-rgb565`、PSRAM、keyboard、FAT32 SD、quantum 1、cycle limit
8,000,000,000、stopは`scenario_done`である。

trace-on candidateは次を満たした。

- exit 0 / verdict pass
- `927528660` cycles、virtual `3715000` us
- scenario `85/85`
- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
- PSRAM `tick_count=305747113`
- behavior SHA-256 `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`
- event stream SHA-256 `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- 173,498,680 events、全9 domainがOPT1-B referenceと一致

canonical artifactはrecordの`run-report.json`と`behavior-trace.json`である。

## 性能 screening

trace-off clean release runnerをCPU 0固定（`taskset -c 0`）で、warmupなしのA/B/A/B/A/B順に実行した。
各runのwall値、commit、exit status、exact output、proof counterはmachine-readable recordへ固定した。

| run | variant | wall |
|---|---|---:|
| A1 | baseline | 26.37 s |
| B1 | candidate | 27.85 s |
| A2 | baseline | 25.70 s |
| B2 | candidate | 28.17 s |
| A3 | baseline | 25.92 s |
| B3 | candidate | 28.53 s |

baseline中央値は25.92 s、candidate中央値は28.17 s。pairごとの改善率は
`-5.6124383769%`、`-9.6108949416%`、`-10.0694444444%`で、中央値改善率は
`-8.6805555556%`だった。exactnessは全6本で一致したが、5% promotion thresholdを満たさない。

machine-readableな入力hash・run一覧・CPU affinity・proof counters・exactnessは
[`opt2-g-uart-deadline-20260809-01`](../firmware-validation/records/opt2-g-uart-deadline-20260809-01/record.json)
と同recordの[`performance-screening.json`](../firmware-validation/records/opt2-g-uart-deadline-20260809-01/performance-screening.json)
に固定した。

## 採否と次工程

exactnessは合格、性能は不合格。active target、firmware pin、validation attestationは変更しない。
candidateは`335ecdd7f01cbc5d4f63e18403033bd629efbe77`でrevertし、最終内容がbaseline
`2671d0476c1a4286de7e3666bf91e20e27613854`と一致することを確認した。backend CI
run `31287315634`はtest、fmt、Clippyの全jobが成功した。

OPT2は性能条件未達のまま追加promotionなしで終了し、次工程はOPT3 CPU/decode/execute block cacheとする。UART laneを
promoted optimizationとして扱わず、
CPU MMIO/DMA orderingの未証明を理由にrunning fast-forwardへ拡張しない。
