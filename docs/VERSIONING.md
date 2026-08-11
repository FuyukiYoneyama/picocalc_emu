# 公開版とバージョン管理

この文書は、`picocalc_emu` と `picoem-picocalc` を公開した後に、開発中の
コミットと利用者向けの安定版を区別するための正典である。

## 利用者が見るべき目印

利用者は `main` の先端や日付の新しいコミットを選ばず、GitHub Releases に
紐づいた SemVer のタグを選ぶ。

```text
main             開発中。利用者向けの安定性を保証しない
通常のコミット   開発履歴。リリースの目印ではない
vX.Y.Z タグ       不変のソース基準点
GitHub Release    利用者向けの説明、対応表、既知の制限を含む配布点
```

GitHub の `Latest` 表示は利便性のために使えるが、再現性が必要な場合は必ず
具体的なタグ名と commit SHA を記録する。`latest` や `stable` のような移動する
タグは作らない。

## バージョン番号

両リポジトリの公開版は Semantic Versioning 2.0.0 の形式 `vMAJOR.MINOR.PATCH`
を使う。

- `PATCH`: バグ修正、文書修正、互換性を壊さない修正
- `MINOR`: 後方互換な機能追加、target や対応範囲の追加
- `MAJOR`: report schema、machine API、target 契約などの互換性を壊す変更

毎回の commit や push で番号を上げる必要はない。開発中の細かな commit は
`main` に積み、利用者へ提供する基準点を作るときだけタグと Release を作る。

初回公開は、API と対応範囲を今後も拡張する余地を明示するため、
`v0.1.0`（public technical preview）を推奨する。タグを作成していない状態は
まだリリースではなく、本書を追加しただけでは `v0.1.0` にはならない。

`bsp/VERSION` の値（現在 `0.9.0`）は Canonical BSP のバージョンであり、
リポジトリ全体の公開版番号とは別に管理する。同様に report schema と machine
API schema は、それぞれの wire contract の版であり、公開版番号の代用にはしない。

## 2リポジトリの対応付け

2リポジトリは独立しているが、PicoCalc の firmware backend を使う利用者向けには
対応する組を Release 単位で示す。

```text
picocalc_emu:    v0.1.0 / <exact commit SHA>
picoem-picocalc: v0.1.0 / <exact commit SHA>
BSP:             0.9.0
report schema:   8
machine API:     1
```

実際の対応表は `picocalc_emu` の GitHub Release notes に記録する。最低限、次を
含める。

- 両リポジトリのタグと full commit SHA
- BSP、report schema、machine API schema
- firmware target registry が固定する backend commit
- 必要な Python、Rust、Pico SDK、toolchain の条件
- ローカル品質ゲートの結果
- 既知の制限、外部 workspace が必要になる歴史的再現の範囲

target registry は backend commit を厳密に固定するため、backend の `main` や
「最新の backend」を互換性の根拠にしない。backend だけを更新した場合も、対応表と
必要な `picocalc_emu` の修正版を一緒に作る。

## 利用者の取得方法

通常の開発利用では、対象 Release のタグを指定して clone する。

```sh
git clone --branch v0.1.0 \
  https://github.com/FuyukiYoneyama/picocalc_emu.git

git clone --branch v0.1.0 --recursive \
  https://github.com/FuyukiYoneyama/picoem-picocalc.git
```

`picocalc_emu` の portable 検証、プロジェクト生成、host backend は backend や
外部 workspace なしで使える。firmware backend を使う場合だけ、同じ Release notes
に記載された `picoem-picocalc` のタグ／commit を取得する。PicoTetris、PicoEdit、
歴史的な実機 record の再現に必要な `picocalc_emu_ext` は通常利用の依存ではない。

`verify-project` は provenance のため Git metadata を利用する。したがって GitHub の
`Code -> Download ZIP` ではなく、タグを指定した `git clone` を推奨する。ZIP はソース
閲覧や単純なビルドには使えても、provenance 検査では `cannot judge` になり得る。

## リリースを作るとき

リリースは、両リポジトリの変更をまとめてローカルで検証してから作る。

1. 変更を `main` にまとめ、両リポジトリの作業ツリーを clean にする。
2. [公開手順](PUBLIC_RELEASE.md)のローカルゲートを実行する。
3. 対応する公開版番号、backend commit、schema、toolchain を確定する。
4. 両リポジトリの正確な commit に annotated tag を作る。
5. commit とタグをまとめて push し、GitHub Release を作る。
6. Release notes の対応表と既知の制限を確認する。

タグを後から別 commit へ移動したり、公開済みタグを force-push したりしない。
誤りが見つかった場合は、次の patch version を作って訂正する。GitHub Actions は
通常の開発・デバッグの検証手段にせず、リリース判定はローカルゲートを主体とする。

## 関連文書

- [公開リリース手順](PUBLIC_RELEASE.md)
- [公開前チェックリスト](RELEASE_CHECKLIST.md)
- [対応範囲](../firmware-validation/capability.json)
- [target registry](../reference-projects/firmware-targets.json)
