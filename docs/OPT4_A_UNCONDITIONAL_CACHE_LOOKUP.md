# OPT4-A unconditional decode-cache lookup

> **現行の実験記録。** この候補はmicro-opt bankのscreeningを通過したが、
> promoted targetやactive registryのpinは変更していない。

## 判定

**screening pass / bank candidate** とする。exactnessは通過し、PicoTetrisの10回A/Bで
中央値が3.821338%改善した。ただし、これは単独promotionの記録ではない。別候補との組合せ、
複雑度、代表workloadの追加確認を終えてからmicro-opt bank全体として採否を判断する。

## 変更

`decode_execute` のcache lookupで、cache投入時に既に保証されている
`is_cacheable_pc`のregion判定を、実験feature時だけ省略する。
slotのfull PC tag比較と空entry番兵(`u32::MAX`)の除外は維持する。

- production default: 従来経路のまま
- feature: `unconditional-cache-lookup-prototype`
- main実装commit: `213057aa7add2dd187424a9c81554c68dca3f1ff`
- 対象ファイル: `rp2040-emu` のdecode path、feature forwarding、境界テスト
- promoted backend/target: **変更なし**（OPT1-Bの正式pinを維持）

初回試作では空entryのtag `u32::MAX` と異常PCの一致を見落とし、PicoTetrisが1 cycleずれた。
正確性ゲートで停止し、空entryを明示除外するテストを追加して同一候補commitへ反映した。
この失敗は候補を無条件に採用しない運用が機能した証拠として残す。

## exactness

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

現行generatorから生成したTemplate B相当BIN（formal `picocalc-template-b`の固定source
commitを再現したものではない）を補助確認した。baseline/candidateともcycle-limitでpassし、
UART、framebuffer、PSRAM、FAT32条件が一致した。公式Helloも短縮100M-cycle区間で両候補の
report、UART、framebuffer、PSRAM tickが一致した。ただし、formal Template B pinのsource／BINは
現在のcloneとorigin refsだけでは復元できず、公式Helloの9.5B-cycle候補runも未実施である。

これらの扱いとbank判定は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)に固定した。
したがって本記録だけでactive targetやcapabilityを昇格させない。

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

OPT4-Aはfeature-gated bank候補として保持する。OPT4-B〜Eの候補評価は完了したが、Aをbankへ
進めるには固定Template B source／BINの復元と代表workloadのprovenanceゲートが必要である。
bankを正式採用する場合のみ、元のpromoted baselineとの総合A/B、versioned validation、必要な
文書更新を行う。詳細は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)を参照する。
