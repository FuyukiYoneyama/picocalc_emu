# エミュレーターを補完する実機 HIL デバッグ

## 位置づけ

PicoCalc の実機デバッグは、エミュレーターを置き換えるものではありません。
エミュレーターで再現性のある検証を行った後、実 RP2040、実基板、実表示、実音声、
実入力、リセット経路でしか判定できない範囲を Hardware-in-the-Loop (HIL) で確認します。

推奨する流れは次のとおりです。

```text
hardware-free unit test
        ↓
host backend
        ↓
firmware backend / emulator scenario
        ↓
safe HIL runner（UART・リセット・起動証拠）
        ↓
必要な場合だけ人間による表示・音声・物理操作の確認
```

HIL の合格は、エミュレーターの合格や人間による見た目・聴感の合格を自動的には意味しません。
各段階の結果を別々に記録してください。

## どの段階で何を判定するか

| 段階 | 主に判定できること | 主に判定できないこと |
| --- | --- | --- |
| host backend | アプリロジック、状態遷移、描画データ、入力の基本 | 実RP2040のタイミング、実ペリフェラル |
| firmware backend | RP2040命令、PIO、DMA、GPIO、I2C、SPI、LCD接続、固定範囲の音声 | 実基板の個体差、実パネルの見え方、実スピーカーの聴感 |
| HIL runner | 実起動、実クロック、実UART、実リセット、実flash／loader経路、実ペリフェラル初期化 | UARTに出していない状態、画面の見た目、音の聴感 |
| 人間による確認 | LCDの見え方、キーの物理操作、スピーカーの聞こえ方 | 再現性のある内部状態の網羅 |

HIL は、LCD・PIO・DMA・PSRAM・SD・音声・クロック・USBリセット・loaderを変更したとき、
およびリリース候補で優先します。純粋なゲームロジックの修正ごとに実機書き込みを行う必要は
ありません。

## HIL runner の契約

プロジェクト固有の runner を用意する場合は、次の性質を持たせます。

1. シリアルポート、ボーレート、タイムアウト、artifact を引数で受け取る。環境固有の値を
   ソースへ埋め込まない。
2. 既定動作は読み取りとアプリ再起動だけにし、flash 書き込みを行わない。
3. シリアルポートを開くときは、基板の仕様が要求しない限り DTR/RTS を無効にする。
   ポートを開いただけで意図しないリセットを起こさないためである。
4. リセットまたは書き込みの前にUART captureを開始し、起動直後のログを失わない。
5. `[BOARD][BOOT]`、`[BOARD][READY]`、アプリのready／pass markerなど、機械的に照合できる
   markerを持つ。ログの一部を人間が読んで合格扱いにしない。
6. 終了コードを固定する。`0` は判定済み合格、`1` は判定済み不合格、`2` は接続・artifact・
   環境不足などで判定不能とする。
7. UART log、runner log、artifactのSHA-256、source/build identity、実行時刻、判定を一つの
   証拠セットとして保存する。

Windows で PowerShell runner を使う場合の一般形は次のようになります。`<serial-port>`、
runner名、引数名はプロジェクトに合わせて置き換えます。

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File .\tools\hardware-smoke.ps1 `
  -Port <serial-port> `
  -ResetApplication
```

PowerShellから `picotool` などの書き込みツールを呼ぶ場合も、runnerの既定動作は読み取り・
リセットに限定します。書き込みは別の明示的なオプションに分け、実行前の安全検査を必須に
してください。

## UF2 と常駐 loader の安全性

PicoCalc のように、アプリを選択・転送する常駐 loader が flash の一部を所有する構成では、
通常の SDK が生成したUF2を低レベルの書き込みツールで直接転送してはいけません。UF2の先頭
boot2やloaderの予約領域を上書きし、通常のloaderメニューへ戻れなくなる可能性があります。

実機へ書き込む必要がある場合は、対象loaderが定める通常の転送経路を優先します。低レベルの
書き込みが必要なプロジェクトでは、少なくとも次を機械的に検査できる安全版artifactを用意します。

- loaderが所有するboot2を保持している。
- loaderの予約領域へアプリが重ならない。
- application payload、source commit、BSP/backend identityが期待値と一致する。
- 書き込み前にUF2 family、範囲、boot2、loader metadataを検証する。
- raw UF2を直接指定する経路と、安全版UF2を指定する経路をrunnerで分離する。

書き込み後は、verifyだけでなく、loaderの通常メニューへの復帰、アプリ起動、UART起動markerを
確認します。リリース候補では、warm resetだけでなく可能なら電源OFF/ONのcold bootも一度確認します。

## デバッグ時の使い分け

- 状態遷移、落下、連結、スコア、タイマーの不具合は、まずscenarioとUART/snapshotでエミュレーター上に
  固定する。
- 起動しない、周辺機器の初期化が止まる、実クロックでだけ壊れる場合は、同じartifactのHIL UARTを比較する。
- エミュレーターと実機で同じアプリ payloadを使ったことを、BIN/UF2のprovenanceまたはpayload SHAで示す。
- HILのUARTがPASSでも、LCDの色・ちらつき・音量・ノイズ・キーの押しやすさは別の人間確認にする。
- 実機だけで再現する不具合は、まず起動marker、失敗直前の状態、リセット種別、電源条件、artifact SHAを記録し、
  可能ならその状態をエミュレーターscenarioへ戻して再現性を作る。

この分離により、エミュレーターは速くて再現性の高い回帰検証を担当し、HILは実シリコンと実機構成の
相関確認を担当できます。どちらか一方の合格だけで「完成」と判定しないでください。
