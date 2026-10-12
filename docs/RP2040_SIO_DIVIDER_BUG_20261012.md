# RP2040 SIO除算器の既知不具合（2026-10-12）

状態: **未修正。実装の不整合は確認済み、修正版による再確認は未実施。**

## 不具合と影響

backendのSIO除算器は、除数の書き込みでは計算しますが、被除数の書き込みでは
再計算しません。RP2040はどちらのオペランドを書いても計算を開始する仕様です。
符号なし・符号付きの被除数レジスターが両方とも該当します。

公開backend `32d27ff4179a993ae9fac6ff4a1d5e8999570fa9` と、今回の環境センサー
付き観測に使った `f810d059958773d1b42a1c6d03cc15183cdc1a4f` のソースに同じ
欠落を確認しました。全履歴・RP2350・Threaded動作まで確認したという意味ではありません。

Pico SDKの64bit除算には、除数→被除数の順で書き込む処理があります。この順序で
古い結果を使うため、商の補正ループが長時間進み、画面更新や入力処理が止まった
ように見える可能性があります。backendの実装箇所、SDKの固定版参照、最小再現手順、
修正後の受入条件は
[backendの不具合文書](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/rp2040_sio_divider_bug_20261012.md)
を正典とします。

## 今回の観測

ClockCalc 0.8.78をcleanなf810d059、Serial、quantum 1で実行し、電卓からEscで
時計へ遷移させました。2,680 ms時点で時計の時刻領域は非黒画素0、scenarioはfail。
最終PC `0x10016e40` はSDK除算の補正ループ内でした。例外・emulator error・
unsupported MMIOは報告されていません。

UARTはBMP280のADC値、校正値、温度補正結果まで出ています。別の0.8.77診断runの
レジスターと保存LRも圧力補正からの除算呼び出しに対応しました。
【推定】 上記モデルの欠落が今回の除算停滞を説明します。ただし修正版による比較runは
未実施です。ユーザーが報告した実機LCDの故障原因とは断定しません。

0.8.73のbaselineは非黒画素数のassertでpassでしたが、時計snapshotに電卓の残像が
あります。単なる非黒画素数では期待した画面の表示を保証できません。
また、LCDのCOLMODやSLPOUTが正しく記録されても、実機の表示成功を保証しません。

## 保存記録と運用

- [原本・実行条件・SHA-256台帳](../firmware-validation/evidence/clockcalc-sio-divider-20261012-01/README.md)
  にscenario、report、UART、runnerログ、I2C sidecar、画像と診断用patchを保存しました。
- これは既知不具合の調査記録です。新しい正式validation recordやtargetの合格ではなく、
  registry / capability / accepted backend pinを変更しません。
- 元のBINはdirtyな外部アプリの診断buildです。BIN/UF2と完全な外部ソースsnapshotは
  このrepoに同梱していないため、保存資料だけで同一BINを再生成できるとは主張しません。
  レジスター単位の最小再現はbackend文書から独立して実装できます。
- 修正時は、両operandの書き込み順、符号付き・符号なし、core間の独立性、SDKの
  64bit除算を確認し、期待する時計文字と後続入力を含む比較記録を残してください。
- ユーザーはエミュレーター作業を中止し実機確認を選択しました。この文書化では
  emulator実行・修正・新規テスト・実機操作は行っていません。

本件の記録追加は文書保守です。BSP版、report schema、target契約、公開タグは変更しません。
