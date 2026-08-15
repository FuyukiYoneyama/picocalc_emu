# OPT4 micro-opt bank 判定

更新日: 2026-08-15

## 判定

OPT4-A〜Eの候補評価をいったん区切る。**現時点ではmicro-opt bankをpromotionしない。**

OPT4-AはPicoTetrisの正式10-run A/Bで正の性能信号を得ているため、bank候補として保持する。
しかし、代表workloadの固定artifactを再現できる状態にないため、A単独またはA+B…のbankを
promoted backendへ入れる判断は保留する。OPT4-B〜Eは、exactnessを満たした候補も含めて、
採用可能な再現可能な性能改善を確認できなかった。

この判定はsourceやactive targetの不具合ではない。**代表workloadのprovenance不足を理由に、
採用を止めるfail-closed判定**である。

## 候補の最終状態

| 候補 | exactness | 性能 | bank |
|---|---|---|---|
| OPT4-A unconditional cache lookup | 合格 | PicoTetris正式10-runで中央値3.821338%改善 | 候補として保持、未採用 |
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

## 正式Template Bを今すぐ再測定できない理由

target registryが固定するTemplate Bのsource commit `82e943ab1942ef869e9bff38ae6fcf8074930361`
は、**現在の`picocalc_emu` cloneと、そのorigin refsだけでは取得できない**。したがって、期待BIN
`1e6abac252c28a349d172254c0bc08976786023597a1c44002bfcb1bfbd02a3d`をclean cloneから再生成できない。
`templates/rp2040-basic/build`にあるuntracked成果物はこのpinの証拠ではないため、正式測定には使わない。

このartifact欠落を埋めずに「Template B退行なし」や「bank採用」を宣言してはならない。公式Helloの
9.5B-cycle候補runも同様に、正式なA候補BIN／clean backendを固定できるまで保留する。

## 残件（OPT4の採否ゲート）

1. Template Bの固定source（または同じprovenanceを持つimmutable bundle）を復元する。
2. そのBINを使い、A候補のexactnessと代表workload退行を再測定する。
3. 必要なら公式Helloの9.5B-cycle候補exactnessを1回実行する。性能値には使わない。
4. A単独または複数候補bankを、元のpromoted baselineに対して10-run A/Bし、複雑度・診断影響・
   追加メモリと合わせて採否を決める。

これらが閉じるまで、OPT4は**feature-gated実験候補のまま**とし、既定実行経路はOPT1-Bを維持する。
GitHub Actionsは使用しない。
