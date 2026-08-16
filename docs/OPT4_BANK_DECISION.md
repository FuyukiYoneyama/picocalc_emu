# OPT4 micro-opt bank 判定

更新日: 2026-08-16

## 判定

OPT4-A〜Eの候補評価をいったん区切る。**micro-opt bankはpromotionしない。**

OPT4-Aの隔離candidateはPicoTetrisで正の性能信号を得て、正式Template Bと公式Helloの
exactnessも通過した。しかし2026-08-16、現行backend mainとの組合せでempty `DecodedOp`の
sentinelとfaulting PCが一致する回帰をunit testが検出した。回帰はbackend commit `37c50e6`で
修正し、cache representationのfeature matrixを再検証した。続くbackend `6a675b1`でDMA／audio
quantum-invariance 5/5（timer累積値、miss分類、PCM／block／latencyを含む）、`00b05f5`で
HIGH_PRIORITY／timer競合5/5、`e0eda1c`でboard-less audio／WAV／UART marker CLI E2Eも合格した。
Aはなおfirmware回帰待ちであり、bankへはまだ戻さない。
OPT4-B〜Eは従来どおり採用しない。

これは性能の大小ではなく、**一つでも正式代表workloadが不一致なら即不採用とするexactness
絶対条件**による判定である。

## 候補の最終状態

| 候補 | exactness | 性能 | bank |
|---|---|---|---|
| OPT4-A unconditional cache lookup | 隔離candidateは代表workload合格。**sentinel／DMA・audio／priority低レベル／CLI E2E回帰済み、firmware待ち** | PicoTetris中央値3.821338%。正式Template B中央値0.471921%退行（CIは0を含む） | **bank復帰保留** |
| OPT4-B NVIC bitmap scan | 合格 | 10-run差0.048429%、paired 95% CIが0を含む | 不採用 |
| OPT4-C 8-byte `DecodedOp` | 合格 | PicoTetris中央値1.909397%退行 | 不採用 |
| OPT4-D diagnostic PC compile-out | 合格 | 正式SD/FAT32条件で正の改善を識別できず | 不採用 |
| OPT4-E compact dispatch key | 合格 | 100M-cycle短縮screeningで中央値0.299401%退行。正式10-runはhost slowdownで未完了 | 不採用 |

各候補のdefault build、promoted target、target registry、versioned validationは変更していない。

## OPT4-A 代表workload確認

### Template相当BIN（補助確認）

正式pinではない現行generator由来のBINを使い、同一BIN・同一board profile・FAT32条件で
baseline `e985a9d7…` とA候補 `3651f4c1…` を各1回実行した。

- BIN SHA-256: `a9a39545083979afee29a08da14cb94973bc0b20a0256ea472cbb14e9b5459cd`
- cycles: `1,200,000,000`
- elapsed_us: `4,805,028`（両方一致）
- stop: `cycle_limit`、verdict: `pass`（両方）
- UART SHA-256: `c882c225dbceaa2add779f6e6d45243f8e2811e70e2a59620154dbcc85d4e6a3`
- framebuffer RGB565 SHA-256: `d22729c05ef814b473c90d97b54d9074d8761bf0bc94c0201c6d2df393d5e71b`
- SD: FAT32、keyboard dropped: 0

wall timeはbaseline 27.60 s、候補24.11 sだったが、各1回のため性能根拠には使わない。
これは「代表入力で明らかな退行がない」ことだけを確認する補助測定である。

### 公式Hello（短縮確認）

固定source `553da6f2408963b956779599d179d77fd611a4d7` から得た正式BIN
(`925d4a97745744e130877b1a113b98f656e059ec9c4f9e6e906969e47fc44086`)を、100M cycleで
baseline／候補各1回実行した。

- cycles: `100,000,000`
- elapsed_us: `770,356`（両方一致）
- stop: `cycle_limit`、verdict: `pass`（両方）
- UART SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- framebuffer RGB565 SHA-256: `8eafc7bd411c1f02b9e972a83d2b0a4164eefc5ef51e6b63ad7acc78be4ad44f`
- PSRAM: tick_count `7,598,069`（両方一致）

これは公式Helloの9.5B-cycle正式受入や性能測定の代替ではない。OPT1-Bに記録された
e985候補の9.5B-cycle exactnessを再利用し、A候補については短縮区間の非逸脱だけを記録する。

## 正式Template Bのprovenance復元とA/B

target registryが固定するTemplate Bのsource commit `82e943ab1942ef869e9bff38ae6fcf8074930361`
をremoteから明示取得してclean cloneを復元した。生成BIN／UF2はそれぞれregistry pin
`1e6abac252c28a349d172254c0bc08976786023597a1c44002bfcb1bfbd02a3d`／
`1ab0d16f4f05207934f6d63b77d2ae5437231ee3762381b82505a3d4acefc757`と一致した。

その正式BINを使い、baseline／candidateを同じrelease profile、同じtrace OFF条件で10組ずつ
測定した。10組すべてのsemantic report、UART、RGB565、PSRAM、SD、keyboard、verdictが一致した。
wall中央値はbaseline `21.190 s`、candidate `21.290 s`で、中央値変化は0.471921%退行、
paired differenceの95% CIは`[-0.208954, 0.180954] s`だった。前回の19.257495%値はbaseline
だけがbehavior-trace feature有効だったため、比較条件不一致として破棄した。

`templates/rp2040-basic/build`のuntracked成果物は正式pinの証拠ではない。今回の正式BINはclean
cloneから再生成した一時artifactであり、リポジトリへバイナリを追加していない。

## 公式HelloのA候補exactness

正式Hello BIN (`925d4a97745744e130877b1a113b98f656e059ec9c4f9e6e906969e47fc44086`)を
candidate backend `3651f4c1…`でtarget契約どおり（`hwspi-rgb888`、PSRAM verify、keyboard `HI`、
SD未接続、9.5B cycles）実行した。baseline正式recordとの比較はbackend identityとPNG出力名を
除いて一致した。

- cycles / elapsed_us: `9500000000` / `71447048`
- UART SHA-256: `5559f2f1…`
- framebuffer RGB565 SHA-256: `a7351e95…`
- PSRAM verify: `8388608 matched / 0 mismatched`
- keyboard: `4 delivered / 0 remaining / 0 dropped / backlight 0`
- verdict: `pass`、required UART markers: 全て存在

前回の失敗に見えたrunは`pio-rgb565`を使い、別runはSDを接続していたため、正式baselineと
比較条件が異なる。いずれもexactness recordには採用しない。

## 残件（OPT4の次の安全な手順）

1. Aを含む現行bank（現在はAのみ）を元のpromoted baselineと同一条件で総合A/Bし、
   複雑度、保守負担、追加メモリ、診断影響を記録する。
2. 総合改善が再現し、exactnessと退行上限を満たす場合だけ、versioned validationを作成して
   promotion可否を別判断する。
3. 新候補を加える場合も、PicoTetris、Template B、公式Helloのexactnessを先に閉じてから
   bank全体を再測定する。

原因が閉じるまで、OPT4は**feature-gated実験候補のまま**とし、既定実行経路はOPT1-Bを維持する。
GitHub Actionsは使用しない。
