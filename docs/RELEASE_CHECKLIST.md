# 公開前チェックリスト

`picocalc_emu`を公開リポジトリにする時点で満たすべき条件をまとめる。

**現状（2026-08-04）:** `picocalc_emu`と`picoem-picocalc`はどちらもprivateである。
方針としては公開予定であり、ライセンス面の確認は済んでいる（`MIT OR Apache-2.0`、
NOTICE維持）。ただし十分な完成度に達するまで公開しない。**実施時期は未定**であり、
判断は人間が行う。この項目はGate進行の前提条件ではない（`IMPLEMENTATION_PLAN.md`
Gate 6参照）。

両方がprivateである限り`FIRMWARE_BACKEND.md`の公開条件と矛盾しない。矛盾が生じる
のは「`picocalc_emu`だけを公開し、backendがprivateのまま」という状態である。

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

conformance targetは目印であってリポジトリの資産ではない（`EMULATOR_ROADMAP.md`
§2.1）。記録するのは結果と再現に必要な識別情報だけである。CIで配布可能な
fixtureが必要になった場合も公式サンプルを同梱せず、契約を満たす等価サンプルを
自作する。

## 3. ライセンスと帰属

- [ ] `LICENSE`が存在し、`picoem-picocalc`側の`MIT OR Apache-2.0`とNOTICEが維持
      されている
- [ ] upstream（`0x4D44/picoem`）の履歴・著作権表示・帰属が保持されている
- [ ] 実機記録に含まれる写真・ログに公開したくない情報が含まれていない

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
