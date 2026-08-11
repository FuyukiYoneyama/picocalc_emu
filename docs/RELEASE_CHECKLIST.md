# 公開前チェックリスト

`picocalc_emu`を公開リポジトリにする時点で満たすべき条件をまとめる。

**現状（2026-08-11）:** `picocalc_emu`と`picoem-picocalc`はどちらもprivateである。
公開準備では、通常利用の依存性、同梱第三者物、実機証拠の扱い、ライセンス境界を確認する。
LCD adapterについては、GPL-3.0のソースを同梱せず独立実装をMITで配布する方針を
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)に固定した。これは法的助言ではなく、
公開物のエンジニアリング上のprovenance判断である。公開操作の時期は人間が決める。
（[`history/IMPLEMENTATION_PLAN.md`](history/IMPLEMENTATION_PLAN.md) Gate 6参照）。

両方がprivateである限り`FIRMWARE_BACKEND.md`の公開条件と矛盾しない。矛盾が生じる
のは「`picocalc_emu`だけを公開し、backendがprivateのまま」という状態である。

## 0. 利用者向けバージョン目印

- [ ] 初回公開版または更新版の SemVer（例: `v0.1.0`）を決めた
- [ ] `picocalc_emu` と `picoem-picocalc` の対応する commit SHA を記録した
- [ ] BSP、report schema、machine API schema、toolchain 条件を記録した
- [ ] 両リポジトリの同じリリース番号に annotated tag を付けた
- [ ] GitHub Release notes に対応表、既知の制限、取得方法を記載した
- [ ] 公開済みタグを移動・force-pushしない運用を確認した

## 1. 依存の公開性

- [ ] `picoem-picocalc`が公開されている、または等価な再現可能配布として入手できる
- [ ] 公開版`picocalc_emu`の通常ビルドと`python3 tools/picocalc.py verify`が
      private依存を要求しない（**機械検査あり**: 下記§4）
- [ ] `firmware-validation/capability.json`のbackend URLが公開先を指している

`picocalc_emu`を先に公開する場合、backendを要する機能（`test --mode firmware`）は
「backend不在」を明示して終了コード2を返す設計になっており、clone単体の検証は
通る。したがって技術的には先行公開も可能だが、**Gate 5の結果を第三者が再現できない**
ため推奨しない。

## 2. 第三者ソースの非同梱

- [ ] ClockworkPi公式`picocalc_helloworld`のソース・ELF/BIN/UF2が含まれない
      （**機械検査あり**）
- [ ] Pico SDK、`rp2040-psram`等のvendorソースが意図せず入り込んでいない
- [ ] `THIRD_PARTY_NOTICES.md`が実際の同梱物と一致する
- [ ] `bsp/vendor/`の由来記載が`bsp/vendor/README.md`と一致する

conformance targetは目印であってリポジトリの資産ではない
（[`history/EMULATOR_ROADMAP.md`](history/EMULATOR_ROADMAP.md) §2.1）。記録するのは結果と再現に必要な識別情報だけである。CIで配布可能な
fixtureが必要になった場合も公式サンプルを同梱せず、契約を満たす等価サンプルを
自作する。

## 3. ライセンスと帰属

- [x] `LICENSE`が存在し、`picoem-picocalc`側の`MIT OR Apache-2.0`とNOTICEが維持
      されている
- [x] upstream（`0x4D44/picoem`）の履歴・著作権表示・帰属が保持されている
- [x] 実機記録に含まれる写真・ログに公開したくない情報が含まれていない
      （公開JPEGはGPS・撮影日時・機種情報を除去し、色プロファイルだけを保持）

## 4. 機械検査

次のコマンドで、§1と§2のうち自動化できる項目を検査する。

```sh
python3 tools/picocalc.py verify
```

`release:no-conformance-target`と`release:portable-without-backend`の2項目が
これに対応する。前者はリポジトリ内にconformance targetのソースや成果物が
入り込んでいないこと、後者はbackend不在でもportable検証が完結することを確認する。

機械検査は§1〜§3のすべてを代替しない。公開判断の前に本書のチェックリストを
人間が確認する。

## 公開物における証拠と開発環境情報

`firmware-validation/records/`と`hardware-validation/records/`は、判定を再現するための
凍結証拠である。record内のbuild log、source video、toolchain pathは、その時点の測定環境を
示すprovenanceフィールドであり、通常のビルド・実行時に参照される依存ではない。公開版では
新しいREADMEや実行手順に個人環境の絶対pathを使用せず、過去recordの値は契約を壊さない範囲で
保持する。秘密鍵、token、認証情報をrecordへ追加してはならない。

公開前の最終手順は [`PUBLIC_RELEASE.md`](PUBLIC_RELEASE.md) を正とする。

なお、この準備では既存Git履歴を書き換えない。backendはupstream履歴を保持しているため、
visibility変更前に、履歴中の旧author metadataや開発pathを保持するか、別途レビューした履歴
rewriteを行うかを所有者が判断する。force-pushはこのチェックリストの自動手順ではない。
