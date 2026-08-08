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

## OPT1-A PicoTetris revision 3

`picotetris-opt1a` revision 3は`picotetris-r4`をsupersedeし、exact idle fast-forwardを実装した
backend `c68c58f6c37fb31eb9313566c8b16883db9063b6`を受理します。firmware BIN、scenario、
device profileはrevision 2と同じで、既存revisionとR3/R4の時点証拠は変更していません。

新規record
`firmware-validation/records/opt1-a-20260808-01/record.json`は、85/85 timeline、cycle、UART、
framebufferに加え、one-cycle referenceと候補のbehavior trace schema 2全9 domain一致、trace OFF
10回の決定性と性能、Template Bの追加screeningを固定します。attestationは
`firmware-validation/validations/picotetris-opt1a-r3.json`です。

このrevisionは自動回帰と性能gateを通った**candidate**です。R5で同一BIN SHAを実機と相関する
までは正式採用へ昇格させず、R5で不一致があれば速度にかかわらず棄却または修正します。

## R5 correlation revision 4

`picotetris-r5` revision 4は`picotetris-opt1a`をsupersedeする。backendはraw keyboard eventを
scenarioへ投入できる`612b48510452d4012e4ac6639960ca3983b48f66`、firmwareはR5相関専用
`PicoTetris_R5.bin`である。製品firmwareと診断firmwareを二つ使う契約ではなく、この1つの
BIN/UF2をエミュレーターとPicoCalc実機の両方で使う。

source `9a40a905...`のclean clone build 2回はBIN `8b4ac5c...adc0`とUF2
`0e990cff...4f1`で一致した。emulator preflightでは自動LCD/PSRAM/FAT32/audio/PicoTetris検査と、
`CAPS`を最後に置いたraw eventによる67キーscenarioが5/5で合格した。UART、framebuffer、normalized report、
timelineをtargetへpinしている。evidenceは
`firmware-validation/records/r5-preflight-20260808-01/record.json`、attestationは
`firmware-validation/validations/picotetris-r5-r4.json`である。

このattestationの`accepted`はtarget contractとemulator preflightの妥当性を示す。
実機合格を意味しない。recordの`hardware_correlation_completed=false`を維持し、実機UART全文、
最終PASS写真1枚、参照音確認が新しいhardware evidenceへ記録されるまでOPT1-Aはcandidateである。

後続の実機record
`firmware-validation/records/r5-hardware-20260808-01/record.json`は同一UF2のPicoCalc実行を記録し、
完全verdict、最終PASS写真、参照音抜粋、CRC-validな`PCR5KEY.DAT` 67/67をSHA固定した。
したがって現在の相関状態は`hardware_correlation_completed=true`、OPT1-Aは`promoted`である。
preflight recordと上記attestationは当時のcandidate時点証拠として変更しない。
このR5相関が証明するkeyboard範囲は67キーのpress/release到達性であり、Caps状態遷移、終了時
Caps off、操作UXは含まない。

## OPT1-B PicoTetris revision 5

`picotetris-opt1b` revision 5は時間順で`picotetris-r5`をsupersedeし、製品PicoTetrisの固定BINと
scenarioへ戻してserial fast-path gateを検証する。backendは
`e985a9d7ecb51ef760506a105edd34e31cf9b5f1`、candidate固有normalized reportは
`6c63ab48729684f8391498ff1e1b6486c3a3e19db62c191f0b6637ee29d2d917`である。R5の診断targetや
hardware recordを上書きしない。

新規record `firmware-validation/records/opt1-b-20260808-01/record.json`は、OPT1-A/R5 backendとの
behavior/event全domain一致、trace OFF 10 run性能、Template B、公式Hello、R5相関firmwareの
同値性を固定する。attestationは`firmware-validation/validations/picotetris-opt1b-r5.json`である。
新しい実機操作を省略する根拠は速度だけではなく、candidateが既存の実機相関済みR5 emulator
contractを完全再現したことにある。
