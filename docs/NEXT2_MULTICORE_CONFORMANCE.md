# NEXT-2A Serial multicore conformance

> **文書の役割:** 検証器が読むbounded conformance契約です。NEXT-2Aは完了しています。

**状態:** NEXT-2A正式完了（2026-08-09）。v2エミュレーター受入と、同一v2 UF2による
PicoCalc実機相関の両方が合格した。後続の独立契約NEXT-2B audioも現在は完了している。

## 固定artifact

| 項目 | 値 |
|---|---|
| app repository | `picocalc-multicore` |
| app commit | `e9e99f0bfde7b2706fbe7f5a2a92331eed141c98` |
| backend commit | `38683d65800ef36026f674dd47228024d69eb5e7` |
| target | `picocalc-multicore-r2` revision 2 |
| BIN SHA-256 | `a8816759038df060da3ead7a9e80b02f91e667822132b30c0c1b2436e81c0649` |
| UF2 SHA-256 | `2e19d56560add74267dfc7e1f3876c0034e51d07a5e499ce23e868e7fc7d573f` |
| build timestamp | `2026-08-09T11:30:00Z` |

実機には次のファイルだけを使用する。再buildした別UF2へ置き換えない。

```text
/home/fuyuki/pico_dvl/codex/picocalc-multicore/build/picocalc_app.uf2
```

## エミュレーター結果

契約IDは`next2-multicore-v1-20260809`である。受入値はアプリ実装前に
[`next2-multicore-v1.json`](../firmware-validation/contracts/next2-multicore-v1.json)へ固定した。
最初の凍結backend runはlaunch/FIFOだけが合格し、WFE/SEVとIRQを不合格として保存した。期待値は
変更せず、SDK mutex由来のSEVを測定区間から分離し、Serial backendへcore-local SIO FIFO IRQを
実装した。

v1正式target `picocalc-multicore-r1`は通常CLIで3回実行し、全回が152,548,085 cycle、615 ms、exceptionなし、unsupported
MMIO 0、全phase PASSとなった。v1実機でも最終画面の全5項目がPASSした。しかしmarkerは起動中に
一度だけ出力され、その後無出力だったため、PicoCalc USB Type-Cのnative USB CDCを開く前に全byteが
失われた。2回の0-byte logと最終写真は
[`next2-multicore-hardware-attempt-20260809-01/`](../firmware-validation/records/next2-multicore-hardware-attempt-20260809-01/)
へ、機能PASS・契約証拠未完了として保存した。

この結果を見てv1契約を緩めず、v2実装前に
[`next2-multicore-hardware-evidence-v2.json`](../firmware-validation/contracts/next2-multicore-hardware-evidence-v2.json)
を固定した。v2は同じphase、固定値、初回marker、最終画面を保ち、最終判定後に同じ5-marker blockを
1秒ごとに再送する。`picocalc-multicore-r2`は通常CLI 3回が152,548,092 cycle、615 msで決定一致し、
500,000,000-cycle probeで各markerが2回になること、別々のclean clone 2本でBIN/UF2が完全一致する
ことを確認した。core 1 NMI/HardFaultのfail-closedも維持する。証拠は
[`next2-multicore-r2-20260809-01/`](../firmware-validation/records/next2-multicore-r2-20260809-01/)
にある。

## v2実機相関結果

2026-08-09、上表の同一UF2をClockworkPi PicoCalcへ書き込み、凍結済みv2契約が要求する2点を
同じ実機セッションから取得した。

- USB CDCログは20,664 bytes、360行。固定5-marker blockを72回連続で含み、全blockが同一である。
- 最終写真は`NEXT2 MULTICORE`とLAUNCH、FIFO、WFE/SEV、IRQ1、OVERALLの全PASSを示す。
- エミュレーターPASS・実機FAILは0件で、同一artifact相関の判定はPASSである。

完全な記録、保存用ログ、メタデータ除去済み写真は
[`next2-multicore-r2-hardware-20260809-01/`](../firmware-validation/records/next2-multicore-r2-hardware-20260809-01/)
に固定した。v1の0-byteログと最終PASS写真は、当時の契約未完了を示す時点証拠として別記録のまま
保持する。v2合格によってv1履歴を書き換えない。

## 凍結した試験内容

最初のrunに使うbaselineは`picocalc_emu` `76334780...c8`、promoted backend
`e985a9d7...5f1`、Pico SDK 2.2.0 `a1438dff...179`、ARM GCC 13.2.1、CMake 3.28.3、
Ninja 1.11.1、Serial quantum 1、PIO RGB565である。

- **Launch:** `multicore_launch_core1()`で起動し、core 1が`0xc0110001`を返す。
- **FIFO:** core 0から4語を送り、core 1は
  `rotate_left_32(input XOR 0xa5a55a5a, one_based_index)`を返す。
- **WFE/SEV:** core 1がstage 1とarmed wordを公開してWFEへ入り、core 0の明示SEVより前は
  stage 1、後はstage 2とdone wordになる。
- **IRQ_PROC1:** core 1がhandlerを登録してWFEへ入り、core 0が`0x13579bdf`を送るとhandlerが
  1回だけ受信し、done wordを返す。

FIFO固定vectorは次のとおりで、初回結果やbackend実装に合わせて変更していない。

| input | output |
|---:|---:|
| `0x00000000` | `0x4b4ab4b5` |
| `0x12345678` | `0xde44308a` |
| `0xffffffff` | `0xd2d52d2a` |
| `0x0badcafe` | `0xe0890a4a` |

## 実機で人間が行ったこと

人間の操作は**v2 UF2書込みと証拠保存の1セッションだけ**である。キー入力、monitorを起動前に開く
タイミング合わせ、SD内容の変更、途中写真は不要である。

1. 次を実行し、表示値が上表のUF2 SHA-256と一致することを確認する。

   ```sh
   sha256sum /home/fuyuki/pico_dvl/codex/picocalc-multicore/build/picocalc_app.uf2
   ```

2. 既知のPicoCalc UF2書込み手順でBOOTSEL mass-storage modeへ入り、上記UF2をコピーする。
3. 起動後、画面に`NEXT2 MULTICORE`と次の5行がすべて緑の`PASS`で出るまで待つ。

   ```text
   LAUNCH   PASS
   FIFO     PASS
   WFE SEV  PASS
   IRQ1     PASS
   OVERALL  PASS
   ```

4. PicoCalcのUSB Type-C serialを115200 8N1で開き、ログ保存を開始する。**起動後に開いてよい。**
   v2は次のblockを1秒ごとに再送するので、少なくとも5行が1組揃うまで待つ。
5. 5行すべてが読める最終画面写真を1枚撮る。
6. UARTログを保存してから電源を切る。ログには次の5 markerが同じblock内にすべて必要である。

   ```text
   [NEXT2][MC][LAUNCH] status=pass ready=0xc0110001
   [NEXT2][MC][FIFO] status=pass vectors=4
   [NEXT2][MC][WFE_SEV] status=pass before=1 after=2
   [NEXT2][MC][IRQ_PROC1] status=pass count=1 word=0x13579bdf
   [NEXT2][MC][VERDICT] launch=pass fifo=pass wfe_sev=pass irq_proc1=pass overall=pass
   ```

提出物はUARTログ全文と最終写真1枚の2点だけであり、上記v2実機記録へ保存済みである。

## 失敗・無反応時の扱い

- 10秒待っても最終画面へ到達しない、赤い`FAIL`が1つでも出る場合、
  その試行を失敗証拠としてログと写真に残す。成功したように読み替えない。
- 画面が全PASSでもUSB monitorを開いて3秒以上0 byteなら、USB接続・device名・monitor設定の採取
  問題として保存する。v2は周期再送するため、起動時markerの取り逃しでは説明できない。接続問題を
  直して1回だけやり直し、最初の0-byte fileは上書きしない。
- 同じartifactで再びfirmware側FAILまたは停止になる場合は、それ以上「通るまで」繰り返さない。
  `emulator PASS -> hardware FAIL`のfalse-accept候補としてNEXT-3へ渡す。
- キー操作による復旧は行わない。このappは入力を一切要求せず、キーで状態を変えない。

## 合格範囲

この相関が合格しても、Serial executionにおける固定launch/FIFO/WFE-SEV/IRQ_PROC1経路だけを証明する。
Threaded execution、両coreからの同時LCD/PSRAM、spinlock contention timing、core 1 reset/relaunch、
DMA-paced PCM sample outputは別の契約が必要である。NEXT-2B audioはこの結果と混同しない。
