# OPT4-A unconditional decode-cache lookup

> **隔離試作の測定記録と現行状態。** 過去の隔離candidateは下記workloadでexactnessを
> 満たしたが、2026-08-16に現行backend mainとの組合せでempty-sentinel回帰が見つかった。
> promoted targetやactive registryのpinは変更していない。

## 現在の判定

**bank候補としての扱いを停止し、修正・再検証待ちとする。** レビュー対象のbackend code commit `b94e550`で
`unconditional-cache-lookup-prototype`を有効にすると、
`empty_sentinel_does_not_match_faulting_pc`が失敗する。通常12-byte `DecodedOp`の
`matches_pc()`がempty tag `u32::MAX`を除外せず、faulting PC `u32::MAX`をcache hitと
誤認してbus accessを飛ばすためである。

過去の隔離candidateで得たPicoTetris、Template B、公式Helloの測定値は、そのcommitに対する
履歴証拠として有効である。しかし、後続の共通helper化を含む現行mainのexactness根拠には
流用しない。修正と有効feature matrixの再検証が終わるまでpromotion／bank総合測定へ進まない。
実行順序はbackend側の
[`BACKEND_CHANGE_VALIDATION_PLAN.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/BACKEND_CHANGE_VALIDATION_PLAN.md)
を正典とする。

## 変更

`decode_execute` のcache lookupで、cache投入時に既に保証されている
`is_cacheable_pc`のregion判定を、実験feature時だけ省略する。
隔離試作ではslotのfull PC tag比較と空entry番兵(`u32::MAX`)の除外を維持した。現行mainでは
後続のrepresentation共通helper化により、通常12-byte表現からこの除外が失われている。

- production default: 従来経路のまま
- feature: `unconditional-cache-lookup-prototype`
- main実装commit: `213057aa7add2dd187424a9c81554c68dca3f1ff`
- 対象ファイル: `rp2040-emu` のdecode path、feature forwarding、境界テスト
- promoted backend/target: **変更なし**（OPT1-Bの正式pinを維持）

初回試作では空entryのtag `u32::MAX` と異常PCの一致を見落とし、PicoTetrisが1 cycleずれた。
正確性ゲートで停止し、空entryを明示除外するテストを追加して同一候補commitへ反映した。
この失敗は候補を無条件に採用しない運用が機能した証拠として残す。

## 隔離candidateで確認したhistorical exactness

測定用候補は、正式promoted backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1` のclean
checkoutへOPT4-Aだけを適用した隔離commit
`3651f4c1346c0d1e787e253495b3a2746526ba9c` である。PicoTetris source/BIN、scenario、
SDK、board profileはbaselineと同一にした。

- firmware BIN SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- cycles: `927528660`（baseline/candidate一致）
- elapsed_us: `3715000`（baseline/candidate一致）
- scenario: `85/85` pass
- UART SHA-256: `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- framebuffer RGB565 SHA-256: `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
- PSRAM `tick_count`: `305747113`（baseline/candidate一致）
- behavior SHA-256（trace ON）:
  `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`
- streaming event total: `173498680`
- 9 event domains: count/hashすべて一致

trace ONのrunは正確性確認専用であり、wall-time測定には使用していない。

## 10-run A/B

WSL2、logical CPU 0固定、release、trace/proof OFF、同一BIN/scenario、baseline→candidateの
順で10組を逐次実行した。95% CIは標本平均に対するt(9)の95%区間である。

| | baseline | candidate |
|---|---:|---:|
| commit | `e985a9d7...` | `3651f4c1...` |
| n | 10 | 10 |
| mean wall (s) | 26.388979 | 25.401103 |
| median wall (s) | 26.366208 | 25.358667 |
| 95% CI (s) | [26.080201, 26.697757] | [25.148607, 25.653599] |
| min–max (s) | 25.860901–27.105521 | 24.925924–26.004707 |

中央値改善率は **3.821338%**。全20 runでverdict、cycle、virtual time、UART、framebuffer、
PSRAM、scenarioのprojectionが一致した。candidateがbaselineより遅い組も1組あったが、
全体のCIと中央値でscreening passとした。

## 代表workloadの補助確認

registryが固定するTemplate B source commit `82e943ab1942ef869e9bff38ae6fcf8074930361`を
remoteから明示取得してclean cloneを復元し、BIN／UF2がregistry pin
(`1e6abac2…`／`1ab0d16…`)と一致することを確認した。その正式BINを使い、baseline
`e985a9d7…`とA候補`3651f4c1…`を同一条件（PSRAM、keyboard、SD FAT32、1.2B cycles）で
warmup後10回ずつ実行した。

正式Template Bの前回測定に見えた19.257495%改善は、baseline runnerだけが
`behavior-trace` feature有効でcandidateとコンパイル条件が異なっていたため、証拠から除外した。
trace OFF同士を同じrelease profileで再ビルドして10-run A/Bをやり直した結果は次のとおりである。

- baseline mean / median: `21.292 s` / `21.190 s`
- candidate mean / median: `21.306 s` / `21.290 s`
- paired difference (baseline−candidate) 95% CI: `[-0.208954, 0.180954] s`
- median change: **0.471921% regression**
- 10組すべてでsemantic report、cycle、virtual time、UART、RGB565、PSRAM、SD、keyboard、verdictが一致

公式Helloはtarget registryの正式条件（`hwspi-rgb888`、PSRAM 8MiB verify、keyboard `HI`、
SD未接続、9.5B cycles）でcandidateを実行した。baselineの正式recordと、backend identityとPNG
出力名を除くreportがbyte相当で一致した。

- cycles / elapsed_us: `9500000000` / `71447048`
- UART SHA-256: `5559f2f1…`
- framebuffer RGB565 SHA-256: `a7351e95…`
- PSRAM verify: `8388608 matched / 0 mismatched`
- keyboard: `4 delivered / 0 remaining / 0 dropped / backlight 0`
- verdict: `pass`、required UART markers: 全て存在

従って、公式Helloのexactnessは不合格ではない。前回のSD接続・LCD variant不一致のrunは
比較条件不一致として破棄し、Aの採否判断には使わない。

加えて、実装commit `213057aa...` とその直前の現行main `7dd0c344...` を直接比較する短い
XIP workload（同一PicoTetris BIN、board/PSRAMなし、100M cycles、quantum 64）を10組測定した。
projectionとcycleは全組一致したが、中央値は `0.238905 s` → `0.239648 s` で **0.311026%
の退行**だった（95% CI: baseline `[0.235289, 0.242927]`、candidate
`[0.236259, 0.250710]`）。これはnoiseと区別できる改善ではなく、OPT4-A単独のpromotion根拠
には数えない。周辺機器変更を含む現行mainとの直接比較でも、候補を無条件に昇格しないという
運用が確認できた。

## 検証コマンドの要点

```text
cargo test --release -p rp2040-emu --features unconditional-cache-lookup-prototype
cargo test --release -p picocalc-harness --features unconditional-cache-lookup-prototype
```

上記に加え、featureなしの`rp2040-emu`全テストも実行して1244件合格した。GitHub Actionsは
実行していない。

## 次

現行mainのempty-sentinel回帰を修正し、通常12-byte表現と8-byte試作表現の有効feature matrixを
再検証する。続いてDMA／audio／UART markerの低レベルtestとCLI E2E、既存firmware回帰を閉じる。
これらが終わるまでAをbankへ戻さず、A単独のpromotion、versioned validation、active target更新、
bank総合性能測定を行わない。詳細は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)とbackend側の
[`BACKEND_CHANGE_VALIDATION_PLAN.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/BACKEND_CHANGE_VALIDATION_PLAN.md)
を参照する。
