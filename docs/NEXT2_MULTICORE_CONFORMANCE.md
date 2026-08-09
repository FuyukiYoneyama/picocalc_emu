# NEXT-2A Serial multicore conformance

**状態:** エミュレーター正式受入完了（2026-08-09）。同一UF2のPicoCalc実機相関待ち。

## 固定artifact

| 項目 | 値 |
|---|---|
| app repository | `picocalc-multicore` |
| app commit | `9dfb04e1ed6bb4600b4ce4ade6a3a6b72c321837` |
| backend commit | `38683d65800ef36026f674dd47228024d69eb5e7` |
| target | `picocalc-multicore-r1` revision 1 |
| BIN SHA-256 | `4d99a40413f31d3b83586083a036325bbe651bcba73297b101bd88a78b451675` |
| UF2 SHA-256 | `d9fe9beda7a1ba63c98cc811c0009cd8982d84e40f6e1e8066bf46fcc0337de8` |
| build timestamp | `2026-08-09T10:00:00Z` |

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

正式targetは通常CLIで3回実行し、全回が152,548,085 cycle、615 ms、exceptionなし、unsupported
MMIO 0、全phase PASSとなった。raw report、UART、scenario timeline、snapshotはbyte-identicalで、
別々のclean clone 2本からBIN/UF2も完全再現した。core 1 NMI/HardFaultがrunnerをFAILにする回帰も
含む。証拠は
[`next2-multicore-r1-20260809-01/`](../firmware-validation/records/next2-multicore-r1-20260809-01/)
にある。

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

## 実機で人間が行うこと

人間の操作は**UF2書込みと証拠保存の1セッションだけ**である。キー入力、タイミング合わせ、SD内容の
変更、途中写真は不要である。

1. 次を実行し、表示値が上表のUF2 SHA-256と一致することを確認する。

   ```sh
   sha256sum /home/fuyuki/pico_dvl/codex/picocalc-multicore/build/picocalc_app.uf2
   ```

2. UARTログを起動前から保存できるよう準備する。UART0を使う場合は115200 8N1である。
3. 既知のPicoCalc UF2書込み手順でBOOTSEL mass-storage modeへ入り、上記UF2をコピーする。
4. 起動後、画面に`NEXT2 MULTICORE`と次の5行がすべて緑の`PASS`で出るまで待つ。

   ```text
   LAUNCH   PASS
   FIFO     PASS
   WFE SEV  PASS
   IRQ1     PASS
   OVERALL  PASS
   ```

5. 5行すべてが読める最終画面写真を1枚撮る。
6. UARTログを保存してから電源を切る。ログには次の5 markerがすべて必要である。

   ```text
   [NEXT2][MC][LAUNCH] status=pass ready=0xc0110001
   [NEXT2][MC][FIFO] status=pass vectors=4
   [NEXT2][MC][WFE_SEV] status=pass before=1 after=2
   [NEXT2][MC][IRQ_PROC1] status=pass count=1 word=0x13579bdf
   [NEXT2][MC][VERDICT] launch=pass fifo=pass wfe_sev=pass irq_proc1=pass overall=pass
   ```

提出物はUARTログ全文と最終写真1枚の2点だけである。

## 失敗・無反応時の扱い

- 10秒待っても最終画面へ到達しない、赤い`FAIL`が1つでも出る、またはUART markerが欠ける場合、
  その試行を失敗証拠としてログと写真に残す。成功したように読み替えない。
- USB/UART接続や電源投入順の明白な採取ミスなら、原因を直して最初から1回やり直せる。最初の失敗
  ファイルは上書きせず、試行番号を分ける。
- 同じartifactで再びfirmware側FAILまたは停止になる場合は、それ以上「通るまで」繰り返さない。
  `emulator PASS -> hardware FAIL`のfalse-accept候補としてNEXT-3へ渡す。
- キー操作による復旧は行わない。このappは入力を一切要求せず、キーで状態を変えない。

## 合格範囲

この相関が合格しても、Serial executionにおける固定launch/FIFO/WFE-SEV/IRQ_PROC1経路だけを証明する。
Threaded execution、両coreからの同時LCD/PSRAM、spinlock contention timing、core 1 reset/relaunch、
DMA-paced PCM sample outputは別の契約が必要である。NEXT-2B audioはこの結果と混同しない。
