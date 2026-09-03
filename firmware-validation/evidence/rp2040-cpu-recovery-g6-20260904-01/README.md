# G6（外部I²C module：RTC／EEPROM／AHT20／BMP280）記録

## 状態

**candidate-pass / 未統合**。

高速地点から積み直しているbackend候補へ、PicoCalcの外部I²C経路を限定的に戻した。
このrecordは外部I²C機能の復元確認であり、性能改善、1倍速、formal qualification、
production integrationを意味しない。

## マクロな位置づけ

これは性能退行復旧・再構築計画R2のG6（外部I²C module）の候補検証である。G0〜G5で
高速起点へCPU、表示、PSRAM、音声、flash、loader、SDの必要な境界を順に戻した後、
通常アプリが使う外部I²C機能を追加した。目的は既存の外部I²C受入契約を候補でも再現し、
I²Cを使わない通常アプリへguest-visibleな退行を持ち込んでいないことを確認することだ。

この候補はbackend `main`、active target registry、既存のE5 validation record、外部
project、remote branch、実機を変更していない。既存target `picocalc-clock-i2c-env-e5`
も旧受入commitのままである。

## 候補で戻した契約

1. 明示的に選択した`picocalc-rtc-v1` profileで、DS3231 RTCとAT24C32 EEPROMをI²C1へ接続する。
2. `picocalc-rtc-env-v1` profileでは、上記にAHT20とBMP280を追加する。
3. emulatorの仮想時間を外部deviceへ渡し、RTC、EEPROM busy、sensor conversionをwall-clockに
   依存させず再現する。
4. fixtureのprofile、bus、device、初期値を検証し、I²C transactionをschema 2 sidecarへ記録する。
   address NACK、data NACK、未知address、protocol errorは黙って成功させずfail closedにする。
5. profileを指定しない通常経路は外部I²C muxを付けず、既存Tetris（軽ゲーム実装）の観測値を
   G5-C候補と比較する。

## 起点とprovenance

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前candidate: G5-C `bba2153d8de7d4503f0e7aff1a5b088bbd146da8`
- G6 candidate: `091c371df0baa664f8a082f44d1256f112152798`
- source差分: [`g6-source-diff.patch`](g6-source-diff.patch)、直前candidateから9 files、
  2,696 insertions、91 deletions
- source差分SHA-256: `142e8086a419cd49940b6e6bcc784ea114aac632bb17ddea8727922a9cdc6040`
- candidate worktree: `/tmp`の一時worktree、detached、remote branchなし、clean
- release runner: [`picocalc-run`](picocalc-run)
- runner SHA-256: `ffa1ed4a4be7539780424a8e4acee840e73f7a6c94f57d71bbd8205cfa8948a8`
- backend report identity: `091c371df0baa664f8a082f44d1256f112152798`、`dirty=false`
- bootrom SHA-256: `9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81`
- I²C firmware: `Picocalc_Clock.bin`、SHA-256 `dbca04508de03ebcc01cecfe1ecb1a86fcac1bae5ca649fe843c676bb7a8daff`
- I²C fixture: [`i2c-e5/fixture.json`](i2c-e5/fixture.json)、SHA-256
  `1a2849a79f5e76872d6eee436228d9b5af9fdd5deaef1dc30f8e5c1f8bb8278a`
- Tetris firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- Tetris scenario SHA-256: `49740dab5069cd3f056ab4c9e0a46323d5b18e1f7ff21e4e6a0ce58aa6f8a7f3`

## 実装検証

### unit／integration test

candidate commit後に実行した結果は次のとおり。

- `cargo test --locked -p rp2040-emu -p picocalc-board -p picocalc-harness`: pass
  - board library 99、doctest 1
  - harness runner 66、opt0 baseline 2、SD E2E 1
  - rp2040-emu library 1,251、firmware 9、multicore 9、PSRAM edge 4、smoke 8、WFE IRQ wake 5、doctest 0
- `cargo test --locked -p picocalc-board --no-default-features`: pass（library 94、doctest 1）
- `cargo test --locked -p picocalc-harness --no-default-features`: pass（runner 65、opt0 baseline 2、
  feature依存SD E2Eは0 tests）
- `cargo build --locked --release -p picocalc-harness --bin picocalc-run`: pass
- G6追加fileのrustfmt check、`git diff --check`: pass

workspace全体のpackage-wide `cargo fmt --check`は、G6以外のcandidate既存整形差分を含むため、
G6のpass条件として主張していない。この扱いはfailure logへ記録した。

### I²C外部環境 screening

既存E5と同じ固定firmware、fixture、PicoCalc board、PIO RGB565、PSRAM、keyboard、Serial、
quantum=1、400,000,000 cyclesで、`picocalc-rtc-env-v1`を3回実行した。

各runは次を満たした。

- backend `091c371...`、`dirty=false`
- verdict `pass`、stop reason `cycle_limit`、例外なし、errorなし、unsupported MMIO 0件
- UART 520 bytes、SHA-256 `833a9fade3b1df559f566586cf7bc01dd16d0beaf803783d9ac4cd5e8f8ec2a2`
- framebuffer 320x320、RGB565 SHA-256 `8eafc7bd411c1f02b9e972a83d2b0a4164eefc5ef51e6b63ad7acc78be4ad44f`
- attached addresses `0x1f`, `0x68`, `0x57`, `0x38`, `0x77`
- address phases 26、ACK 26、NACK 0、unknown address 0、write bytes 21、read bytes 181、stop 17
- data NACK 0、protocol error 0、transaction digest
  `327fc2519ae7a076d4f15bd6b0579ca7d6211315dc823d7ff5423606cd1efd0d`

run-01〜03のreport、I²C sidecar、UART、framebufferはすべてbyte-identicalである。
詳細は[`manifest.json`](manifest.json)と各runのファイルを参照する。

### Tetris（軽ゲーム実装）回帰 screening

G5-Cと同じ短いstartup／first-three-placements scenarioを、I²C profileなしで1回実行した。

- report: [`tetris/report.json`](tetris/report.json)
- scenario: [`tetris/r0-scenario-probe.json`](tetris/r0-scenario-probe.json)
- verdict `pass`、stop reason `scenario_done`
- guest cycles `187,528,659`、guest elapsed `755,000 µs`
- UART 1,387 bytes、SHA-256 `db430d62e3e6164709d30ff7ebaac033408ef36f8261a4f313b478e3f8e8155a`
- framebuffer RGB565 SHA-256
  `21738024c789675f1d2a7299004618dc648cc1d5af6f4971c33e392c2bac0162`
- PSRAM CS falling 7、bytes written 24、bytes read 34
- SD protocol errors 0、unknown commands 0

生成PNGの保存先文字列をnull化した[`normalized.json`](tetris/normalized.json)は、G5-Cの
candidate normalized projectionとSHA-256 `fe658ee07415b6d55799e250c09e6997fe9ac98dcd43140efb452fcb4bed4da5`で一致した。
これはこのprobeでG6によるguest-visible退行を観測しなかったことを示すが、速度改善を示さない。

## 判定と次の作業

G6は、外部I²C E5相当の3回完全一致、feature無効経路、G6 unit test、Tetris回帰screeningを
通過したため**candidate-pass**とする。ただし、既存active targetへの昇格やbackend mainへの
統合はまだ行わない。次は計画R2のG7（preview boundary／延期機能）の必要性を確認し、G0〜G6の
candidate差分をまとめて統合可否を判断する。

旧`uf2loader` projectのbranch・公開・改変は行っていない。
