# エミュレーターを使ったPicoCalc開発

## 目的

PicoCalc（RP2040）向けアプリを、人間とAIがPC上で作成・実行・観測・修正できる環境を提供する。
動作済みのBSPから始め、問題を再現する入力と検証結果を保存することで、推測による修正と
人間による実機確認の往復を減らす。実機固有の確認は適用範囲を明示して残す。

## 開発の流れ

| 段階 | 入力と作業 | 次へ渡すもの |
|---|---|---|
| 作成 | templateとCanonical BSPからアプリを生成する | source、BSP由来、設定 |
| ロジック確認 | hostでアプリ固有の処理を試す | unit testと結果 |
| ビルド | Pico SDKでRP2040向けに生成する | BIN、UF2、build条件、SHA |
| エミュレーター実行 | 対象版のrunnerでBINとdevice構成を指定する | report、UART、画面 |
| 再現・回帰 | scenarioと期待結果を固定し、同じ条件で修正を確かめる | 入力・使用版・原本・判定 |
| 実機確認 | 対応範囲外、表示、聴感、物理操作を確認する | 同一artifactの実機記録 |

通常のアプリ開発の完了は、要求したアプリの動作をこの流れで確認できたこと。
エミュレーター側の変更の完了は、既存の利用条件を維持し、変更対象の挙動を証拠付きで説明できたこと。
commit、push、cleanは保存状態の確認であり、動作の完成を意味しない。

## 実行経路の役割

hostはアプリロジックの試験を担当する。firmware backendはRP2040命令と周辺回路、
PicoCalcのLCD・keyboard・SD・PSRAM等を、実装された範囲で扱う。
scenario、UART、snapshot、reportを基本の観測手段とする。
machine APIとpreviewは対応する固定backendを必要とする追加の観測・操作手段である。
実機との一致を確認していない範囲を、エミュレーターで動いたという理由だけで保証しない。

## 文書の体系

- README／USER_GUIDE: PicoCalcアプリを開発する人の入口と実行手順。
- IMPLEMENTATION_STATUS／VERSIONING: 現在使う版と適用範囲。
- DEVELOPER_GUIDE／AI_START_HERE: エミュレーター・BSP・検証基盤を変更する手順。
- registry／contracts／records／evidence: 機械検証の入力と保存した原本。
- history／MILESTONES: 終了した計画、実験、採否、失敗の履歴。

固定契約や証拠に残る過去の機能・予定は、公開mainの現在機能や作業指示とは区別する。
使用するbackendは対象targetが要求する版で確認する。

## 性能作業の位置づけ

速度は開発の反復時間に影響する品質項目だが、このプロジェクトの目的そのものではない。
UX 1倍速・高速化・性能復旧の取り組みは失敗・終了として[履歴](history/performance/README.md)へ移した。
旧状態への復旧は原状回復であり、高速化の達成として数えない。
本筋の開発・検証手順を、終了した性能計画への参加や未達の1倍速を前提として組み立てない。

測定する場合は、対象commit、実行バイナリ、入力、device構成、build条件、時計と区間を固定し、
失敗とwarmupを含む原本を保存する。数値だけを文書へ転記して原本を廃棄しない。
