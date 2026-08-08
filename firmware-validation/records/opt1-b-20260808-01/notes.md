# OPT1-B serial fast-path gate evidence

**Date:** 2026-08-08  
**Target:** `picotetris-opt1b` revision 5  
**Candidate backend:** `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`

## Change under test

Serial fast-path判定でPIO idleを最初に評価し、PIO active時は結果を変えない残りのread-only
predicateを短絡する。さらに`all_peripherals_idle()`内に含まれるDMA判定の重複を除く。
tick、edge、IRQ、event horizon、runner/scenarioには変更を入れていない。

## Exactness procedure

1. 同一PicoTetris BIN、scenario、device profileでbaseline `612b485...8f66`とcandidateを実行。
2. trace ONで`behavior_sha256`、schema 2 event stream、全9 domainのcount/hashを比較。
3. trace OFFでnormal report、UART、PNGの決定性を確認。
4. Template Bと公式Helloを登録済みの再現BINで実行。
5. R5相関BINをcandidateで再実行し、既存preflight/hardware evidenceとの同値性を確認。

PicoTetrisは85/85、cycle、virtual time、timeline、UART、RGB565 framebufferが一致した。
behavior SHA-256は`79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`、
event streamは`2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`、
173,498,680 eventsで、9 domainすべてbaselineと一致した。

公式Helloは95億cycleを完走し、8 MiB PSRAM全域が一致した。622.51秒という値は正確性runの
所要時間であり、性能gateには使用しない。

## Performance procedure

WSL2、AMD Ryzen 5 5600X、logical CPU 0固定、release、trace OFF。同一BIN/scenarioでwarm-up
1回を除外し10回測定した。OPT1-Aの同条件中央値27.122874483秒に対し、candidateは
25.381593530秒で6.419972%短縮、1.068604倍だった。実時間比中央値は14.636592963%、
throughput中央値は36,543,363.279 cycle/sである。

Template Bの3 run中央値はbaseline 20.63秒、candidate 20.91秒で1.357247%退行し、3%上限内。
UARTとframebufferは全runで一致した。

## Artifact roles

- `run-report.json`: trace OFFのcandidate normal report
- `behavior-trace.json`: correctness用trace ON artifact。wall-time評価には使わない
- `realtime-performance.json`: warm-upを除く10 runのraw measurementと統計
- `template-b-report.json`: candidate Template B report
- `hello-report.json`: candidate公式Hello全域PSRAM report
- `record.json`: 上記をtarget、R5相関、採用判断へ結ぶ要約

