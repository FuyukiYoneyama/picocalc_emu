# SD-GEN-1-P0 M-NESCO wire trace

判定: **P0 trace採取 PASS（M-NESCO Run Aのみ）**

SD-GEN-1-P0で、clean source/backendによるM-NESCO mapper 2／中容量caseのSD wire traceを
3回採取した。3回のtraceはevent count、command集合、digest、保存JSONのSHA-256が一致する。

## provenance

- NESco source: commit `7f3fa05971930e03653694117cbf6a435ec1dd4e`, clean
- 診断BIN: SHA-256 `71e7ee1ab5d1145e8e0eb8f7e3f50f399c442ce4c477190811ada2f42fec5457`
- backend: commit `d1360cbb13fd807661474b49a1b5516b12567d00`, clean
- runner: `picocalc-run` SHA-256 `4745c256f215469c2ad554556936663261a3b3cffd67ef6622125d7712e85720`
- trace保持tool: `tools/mnesco_ext.py`（current commit `846e13f`）

入力ROMは呼び出し側のread-only入力として扱い、絶対pathは保存していない。記録するROM識別は
basename、iNES metadata、SHA-256だけである。

## Run A結果

- case: mapper 2／中容量／XIP staging
- ROM bytes: `131088`
- ROM SHA-256: `7421b53c43f5d4a1b8620f56696c827f1192ba3feeccde594e7e92af18a0ff53`
- repeats: `A1`, `A2`, `A3`
- event count: `2079`（各run）
- trace digest: `d8cc44007b800f6b5d6fa3a5b49c6abf4965321ae7484a1e3945f9d7d859d92f`
- command集合: `CMD0`, `CMD8`, `CMD17`, `CMD55`, `ACMD41`, `CMD58`
- unknown command: 0
- trace JSON SHA-256: 3ファイルとも
  `583a7dc595f481c40efdf0a224048992ffa1a208cac929630d5e620ceb169cb6`

このtraceではCMD18／CMD12／CMD23／CMD24／CMD25は現れていない。これはM-NESCOの今回の
single-block経路の観測結果であり、汎用SD protocolの未対応範囲を自動的に解消するものではない。

## Run Bの扱い

同じ診断BINでflash再attachのB1〜B3もrunnerまでは完走したが、autostart buildがROM pathを
`flash:/BUILTIN.NES`として報告したため、M-NESCO host toolのcross-phase契約（`flash:/TEST.NES`）
で不合格になった。このtrace採取の目的はP0のwire観測なので、B結果をM-NESCO受入証拠へ昇格せず、
Run Aのtraceだけを保存した。既存のM-NESCO拡張受入証拠は変更しない。

次のP0作業は、通常menu buildまたは明示的なflash pathを使ったB契約の再確認と、FAT16／FAT32
代表経路のwire trace採取である。SD-GEN-1-P1契約とCMD18等のproduction実装はまだ開始しない。
