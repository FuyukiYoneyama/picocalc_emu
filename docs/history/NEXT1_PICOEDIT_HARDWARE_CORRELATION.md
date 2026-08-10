# NEXT-1 PicoEdit同一artifact実機相関

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


**状態:** 完了（2026-08-09）。`picoedit-r1`のエミュレーターPASSと、同じbuildから生成したUF2の
ClockworkPi PicoCalc実機PASSを相関した。

## 目的

PicoTetrisで既知のworkloadに合わせた回帰だけでなく、受入条件を実装前に凍結した新規アプリでも、
エミュレーターのPASSが実機PASSを予測できるかを確認する。対象は単一core FAT32 ASCII editor
`PicoEdit`である。

## 同一artifact

| 項目 | 固定値 |
|---|---|
| app commit | `82a6e4c76272e8f520d2f8cba42f1a7e549d4933` |
| BSP | 0.9.0 / `a0041b56516ed56ddff23e80d1900a7c0fc6ab15` |
| build timestamp | `2026-08-09T08:00:00Z` |
| BIN SHA-256 | `17cb513b8dd3ea6525ce6bd92d1ce3081bb6ea9730c590c2afb86a9fa085e8f6` |
| UF2 SHA-256 | `730281ef0070a5cf00610471fec9033a2f53aabebf24f52c3b6f0e520f5c6b73` |
| emulator target | `picoedit-r1` revision 1 |
| backend | `e985a9d7ecb51ef760506a105edd34e31cf9b5f1` |

登録済みtargetのclean clone buildではBIN/UF2を各2回再現済みである。実機には、このUF2以外を
再buildせず書き込んだ。

## 結果

| 観測 | emulator | PicoCalc実機 |
|---|---:|---:|
| 起動、LCD、PSRAM、FAT32 | PASS | PASS |
| `INPUT.TXT` | 61 bytes、固定SHA一致 | 61 bytes、固定SHA一致 |
| PSRAM正本 | PASS | PASS、`0x00010000` |
| 検索・編集 | 11-step scenario PASS | 画面操作PASS |
| `OUTPUT.TXT` | 64 bytes、固定SHA/readback一致 | 64 bytes、固定SHA一致 |
| 保存完了 | PASS | 3回ともPASS/readback一致 |
| 最終画面 | framebuffer証拠固定 | 写真で`SAVED - 64 bytes SHA PASS`確認 |
| 最終判定 | PASS | PASS |

期待output SHA-256は
`5c704b1e8055cf77d3600eb4663c5b4ecf651c8b1085da2d0ada6e669ffc249e`である。
SDカードを再読取した結果、`OUTPUT.TXT`と`OUTPUT.BAK`はいずれもこの値と一致し、
`OUTPUT.TMP`は存在しなかった。

## 人間操作の回復性

手順は長い連続キー列や時刻同期を要求しない。実際のrunでは、検索欄へ最初に`raft`と入力した後、
Backspace 4回で消して`draft`へ修正した。また行末編集でもspaceの後の誤った`k`をBackspaceで消し、
`ok`を入力し直した。UARTは両方の訂正と最終PASSを保持している。

したがって合格は「人間が全キーを一度も間違えなかった」結果ではなく、段階確認と局所的な訂正で
到達できた結果である。

## 証拠と機械検証

正式recordは
[`next1-picoedit-hardware-20260809-01/`](../../firmware-validation/records/next1-picoedit-hardware-20260809-01/)
にある。UART全文、入力、出力、backup、最終写真、事前手順、事前input契約を含む。
`tools/verify_environment.py --scope target-schema`は次をfail-closedで検査する。

- target revisionとcontract SHA、source/BSP/BIN/UF2 identity
- 事前契約、手順、emulator record、全証拠fileのSHA-256
- 入出力の完全なbytesとSAVE PASS 3回
- UART中の起動、PSRAM、SD、load、誤入力回復sequence
- 写真の固定hash、JPEG境界、リポジトリ格納版にEXIF/XMPがないこと
- `emulator_result=pass`、`hardware_result=pass`、`false_accept=false`

提出写真の原本には位置情報を含むEXIFがあったため、原本は変更・格納せず、repository copyだけ
EXIF/XMPを除去した。原本と格納版のdecoded RGB SHA-256は一致し、画素内容は変わっていない。

## 判定範囲

NEXT-1は完了である。この1件では`emulator PASS -> hardware FAIL`は0件だった。ただしこれは
PicoEdit v1で観測した単一core、PIO RGB565、PSRAM、keyboard、FAT32 read/write/rename経路の結果であり、
未知の全workloadについて一般的なfalse-accept率0を主張しない。次はNEXT-2でmulticoreと実PCM audioを
独立したfail-closed gateとして拡張する。
