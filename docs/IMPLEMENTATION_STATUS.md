# 現在の開発環境と対応範囲

更新日: 2026-09-11。目的は[エミュレーターを使ったPicoCalc開発](PROJECT_OVERVIEW.md)です。

## 現在の版

| 項目 | 状態 |
|---|---|
| BSP source | 0.9.0 |
| 標準BSP実機相関 | 0.8.8の固定証拠 |
| 標準LCD／SD | pio-rgb565／FAT32。FAT16は明示profile |
| 公開backend main | 32d27ff4179a993ae9fac6ff4a1d5e8999570fa9 |
| 公開backend tree | e985a9dと同一。33b60b9f7d3721fca074ece8ec69737239bc943c |
| 通常Tetris／PicoEditの登録pin | 各targetのbackend.accepted（旧e985a9d）。mainへの自動置換はしない |
| 新規BINの観測 | 公開backendのbatch runnerを使用。登録targetの正式合格とは区別 |
| 対応外・不足入力 | cannot judgeまたは未対応として報告する |

## 開発の基本経路

BSPからアプリを生成し、hostでロジックを確認、Pico SDKでBIN／UF2をビルド、
firmware runnerでBINを実行し、scenario・UART・snapshotで挙動を検証します。
手順は[利用ガイド](../USER_GUIDE/README.md)にまとめています。
エミュレーターの合格と実機での表示・聴感・物理操作の確認は区別します。

## backend版を選ぶ必要がある機能

復旧後の公開mainは旧高速地点の機能範囲です。
machine API、preview API、host audio monitor用transport、追加audio解析、
外部I2C profile、後続SD／loader機能等の受入記録は、対応する固定backendの証拠です。
それらを公開mainの利用可能機能として一括表示しません。

追加機能を再現するときは[registry](../reference-projects/firmware-targets.json)の固定commit、
[capability](../firmware-validation/capability.json)の適用条件、各recordを確認します。
previewは[追加経路の手順](../USER_GUIDE/PREVIEW_GUI.md)を参照します。
過去の機能完成記録の詳細は[整理前の状態記録](history/project-status-20260911/IMPLEMENTATION_STATUS.md)に保全しました。

## 検証の既知の制約

portable verify／release-layout検査には、既存evidenceのUART bin等を
配布物として誤判定する既知の不整合が記録されています。
[切り分け記録](../firmware-validation/evidence/dma-audio-allocation-20260911-01/validation-checks/README.md)を参照してください。
文書の整理やGitのcleanを、全テストの合格として扱いません。

## 性能と終了した取り組み

高速化・UX 1倍速・性能復旧プロジェクトは**失敗・終了**です。
旧状態への復旧を高速化の達成とは扱いません。
[総括](history/performance/README.md)に旧計画、失敗理由、未達事項をまとめました。

公開commitを無変更で実測した固定Tetrisの値は、2026-09-11の3回で
中央値15.1483%、範囲15.1121〜15.1837%でした。
[原本・条件・再現手順](../firmware-validation/evidence/public-speed-retained-20260911-01/README.md)を保全済みです。
これは特定アプリと環境の値で、全アプリの速度や実時間1倍速を保証しません。
