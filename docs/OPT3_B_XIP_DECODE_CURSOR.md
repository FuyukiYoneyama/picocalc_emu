# OPT3-B short immutable-XIP decode cursor

## 結論

OPT3-Bのfeature-gated試作は完了した。**正確性gateは合格したが、性能gateは不合格**だった。
候補は不採用としてrevertし、active backend、target pin、validation attestationは変更していない。

候補はcursor pathを実際に1億回以上使った。それでもtrace/proof OFFのclean A/B/A/B/A/Bで、
wall中央値は25.98秒から27.13秒へ悪化した。改善率は`-4.4264819092%`である。機構が休眠して
いたのではなく、短いsuccessorを先回りして複製・破棄するコストがdecode-cache lookup削減を
上回ったと判断する。

## 試作の境界

backend baseline `0b99b2eabe23205b3c6ac194dcdf016a53de554d`から、candidate
`0e22846186e68d2d726e49817a9f74c246f517ca`を作った。

- `xip-decode-cursor-prototype`を有効にしたときだけ実装を含める。
- 計測counterはさらに`xip-decode-cursor-proof`へ分離し、性能runには載せない。
- Serial core 0だけを対象とし、core 1とThreadedはfail closedにする。
- 対象を実XIP flash `0x10000000..0x14000000`だけに限定する。
- schedulerは従来どおり1命令ずつ進める。
- 現在のdirect-mapped decode cacheにすでにある有効な後続`DecodedOp`を最大3件だけ複製する。
- 先読みbus access、追加decode、cache populationは行わない。
- narrow/wide命令幅を保持し、redirect、fault、prefetch exception、scope exitで直ちに破棄する。
- XIP entry/region/bulk/all invalidationでは破棄し、SRAM-only invalidationでは保持する。
- SRAM、XIP-SRAM、ROMは候補外とする。

unit testは実cursor hit、narrow/wide PC進行、branch redirect、SRAM拒否、SRAM/XIP invalidation、
core 0限定builderを直接検査した。候補時点でrp2040 default 1,229件、feature組合せ最大1,270件、
harness behavior/proof 40件、fmt、Clippy `-D warnings`が合格した。

## exactness

clean candidate runは次をすべて維持した。

| 観測 | 結果 |
|---|---|
| scenario | 85/85、`scenario_done` |
| cycle / virtual time | 927,528,660 / 3,715,000 us |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer RGB565 SHA-256 | `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2` |
| PSRAM tick | 305,747,113 |
| behavior SHA-256 | `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8` |
| event stream | 173,498,680件、SHA `2ead2041...64a789` |
| domain digest | 全9 domainのcount/hashがOPT1-Bと一致 |

proof付きrunと性能runは分離した。proof付きrunのcore 0 counterは次のとおりで、core 1はdisabled・
全counter 0だった。

| counter | 値 |
|---|---:|
| cursor take hit | 134,612,445 |
| cursor take miss | 38,102,585 |
| install | 57,047,061 |
| staged entry | 168,959,816 |
| clear | 32,017,974 |

## 性能gate

trace/proofを無効化した別runnerを使い、clean baseline/candidateを交互に3組測定した。

| pair | baseline | candidate | 改善率 |
|---:|---:|---:|---:|
| 1 | 26.44 s | 26.71 s | -1.0212% |
| 2 | 25.66 s | 27.13 s | -5.7288% |
| 3 | 25.98 s | 29.09 s | -11.9707% |
| 中央値 | **25.98 s** | **27.13 s** | **-4.4265%** |

6 runすべてexactnessは合格したが、全pairで退行し、中央値も採用条件の5%改善に届かなかった。
このscreeningで採否が確定したため、promotion用10 runは実施しなかった。

OPT3-Aのrun平均4.563命令に対して最大3件をeager copyする方式では、使われないstaged entryが
約3,435万件あり、さらに3,202万回のclearが発生した。次候補で同じsuccessor-copy方式を
微調整する根拠はない。

## 採否と次の作業

candidateはcommit `e58e67f1be69357edec0bd47e879039f47a42648`でrevertした。revert後のsourceは
baselineとbyte-equivalentで、backend CI run `31293556450`のtest、fmt、Clippyはすべて成功した。

この文書作成時点の次候補は**OPT3-C compact predecoded dispatch key**だった。既存cache entryに
top-level dispatch用の小さな分類値を保持し、hit時の分岐・decode補助を減らす一方、後続命令を
eager copyしない。
scheduler、exception/IRQ、invalidation、mutable codeの境界はOPT3-Bと同じgateで守る。これは次の
調査方向であり、性能改善を保証するものではなかった。OPT3-Cは後にexactnessへ合格したが
4.1541916168%改善で5%性能gateに届かず、revertして終了した。現在状態は
[`OPT3_C_COMPACT_DISPATCH_KEY.md`](OPT3_C_COMPACT_DISPATCH_KEY.md)を参照する。

完全な機械可読証拠は
[`opt3-b-xip-decode-cursor-20260809-01`](../firmware-validation/records/opt3-b-xip-decode-cursor-20260809-01/notes.md)
に固定する。
