# Versioned firmware target validation

この文書は、firmware targetを更新しながら過去の検証証拠を不変に保つR4契約を定めます。
正本は`reference-projects/firmware-targets.json`（schema 3）、形式定義は
`reference-projects/firmware-targets.schema.json`と
`firmware-validation/target-validation.schema.json`です。

## 三つの固定対象

1. **target contract** — source、toolchain、成果物、backend、runner、scenario、acceptanceを
   `validation`フィールドを除く正規化JSONのSHA-256で固定する。
2. **validation attestation** — target ID/revision、target contract SHA、根拠recordを結ぶ。
   registryはattestationのpathとファイルSHA-256を保持する。
3. **evidence record** — 実行時のcommit、成果物、観測値と合否を保持する時点証拠。
   attestationはpath、SHA-256、`record_id`、根拠sectionを固定する。

この二段階のSHAにより、targetだけ、attestationだけ、過去recordだけを変更してもportable
verifierが`firmware-targets:versioned-validations`で失敗します。pathはrepository内の相対path
だけを許可し、未知の`supersedes`、revisionの逆行、recordのtarget/backend不一致も拒否します。

## revisionの追加手順

既存targetを上書きしません。新しいIDを追加し、`revision`を増やして`supersedes`へ直前の
target IDを指定します。新しいbackendで実行し、reportと成果物のSHAを測定して新規evidence
recordを作成します。そのtarget contract SHAとevidence SHAを新規attestationへ記録し、最後に
attestation SHAをregistryへ入れます。旧target、旧attestation、旧evidenceは変更しません。

合否確認は次です。

```sh
python3 tools/verify_environment.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/picocalc.py test --mode firmware \
  --target <new-target> --firmware <pinned-bin> --backend-dir <pinned-backend>
```

## R4 PicoTetris revision 2

`picotetris-r4` revision 2は`picotetris-r3`をsupersedeし、backend
`3bc6bbd7833e45fbf94d640eb7fbe056dd9fbd81`を受理します。source、BIN、UF2、scenario、
runner条件はR3と同じです。clean cloneからBIN `0784d80d...e62`とUF2
`44ec6227...274`を再生成し、firmware scenarioを3回実行しました。

3回ともexit 0、85/85 steps、13 lines、score 1400で、raw/normalized report、timeline、
UART、framebuffer、PNGが各々一致しました。UART、framebuffer、timelineはR3とも同一です。
backend commitがreportに含まれるためnormalized reportだけがR4固有の
`40b64168...020b`です。集約証拠は
`firmware-validation/records/r4-20260806-01/report.json`、attestationは
`firmware-validation/validations/picotetris-r4-r2.json`にあります。

PicoTetris repositoryのcommit `6cd16eb075120140d9073a72db665482f3c2fe95`では、この固定sourceと
SDK/toolchain/timestamp/identityをGitHub Actionsで再構築し、登録済みBIN/UF2 SHAを直接照合
します。run `31101591668`でunit 666 checksと再現buildの両jobが合格しました。このCIは
既存revisionを再pinせず、固定された成果物を第三者環境で再現できることを継続検査します。

`picocalc_emu` run `31103564391`は、同じbundle/source/toolchainからBINを再構築し、accepted
backendをcommit固定でclean clone/buildしてから`picotetris-r4`を実行しました。target/schema
jobとfirmware regression jobの双方が合格しているため、attestationの静的整合だけでなく、
固定contractの実走までclean runnerで継続検査されます。R4 full gateの全体は
[`R4_CI.md`](R4_CI.md)に記録しています。
