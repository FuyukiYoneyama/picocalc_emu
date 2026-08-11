# 外部workspace（任意）

`picocalc_emu_ext`は、`picocalc_emu`の外側で管理する検証対象アプリ、実機相関用アプリ、
speaker校正ツールのworkspaceです。これはGitHubで公開する`picocalc_emu`および
`picoem-picocalc`の実行時・ビルド時必須依存ではありません。

ただし、これは「このプロジェクトの全ての検証資産が二つのrepositoryだけに含まれる」という
意味ではありません。既存targetのfirmware BINはregistryにSHA-256とsource provenanceを記録
していますが、アプリsourceやBINそのものを全て`picocalc_emu`へ同梱しているわけではありません。
したがって、フォークを既存の回帰・実機相関系列まで含めて継承する場合は、外部アプリsource
（または同じ内容を持つsource bundle）も開発入力として必要です。

## フォークの二つの開発プロファイル

| 目的 | `picocalc_emu_ext`または同等sourceの必要性 |
|---|---|
| エミュレーター／backend本体を改良する | 不要。二つのrepositoryで可能 |
| 新しいPicoCalcアプリを作り、直接runnerで検証する | 不要。アプリを別途作成すればよい |
| 既存targetのscenarioを使う | 対象BINが必要。sourceから再生成するなら外部アプリsourceが必要 |
| PicoTetris／PicoEdit／NEXT-2のtargetを再ビルドして回帰を継承する | 必要。該当アプリrepositoryまたはsource bundleを取得する |
| 実機相関recordを追加・更新する | 必要。対象アプリsource、UF2、実機証拠を固定する |
| speaker校正を行う | 必要。校正toolの外部workspaceを取得する |

つまり、フォークで「エミュレーターを発展させる」だけなら外部workspaceは不要ですが、
「このプロジェクトが現在持つPicoTetris／PicoEdit／NEXT-2までの検証系列をそのまま引き継ぎ、
さらにtargetを追加する」なら必要です。これはruntime dependencyではなく、回帰対象を再生成する
ためのdevelopment input dependencyです。

## 外部workspaceが無くてもできること

次の通常開発フローは、`picocalc_emu`と`picoem-picocalc`、必要なSDK／Rustツールチェーンだけで
完結します。

- `python3 tools/picocalc.py verify`
- `python3 tools/picocalc.py new MyApp --output /path/to/MyApp`
- 生成したアプリの`build`と`verify-project`
- host backendでのテスト
- 任意のBINを指定したfirmware backendの直接実行
- `picocalc-run`のscenario runner／headless machine API

`picocalc_emu`のCLIは外部workspaceを自動importせず、アプリのBIN、scenario、backendの場所を
引数または環境変数で受け取ります。backendは`--backend-dir`、`PICOEM_PICOCALC_DIR`、
または`picocalc_emu`の隣の`picoem-picocalc`から解決されます。

## 外部workspaceが必要になる場合

次の場合だけ、別途アプリrepositoryや校正ツールを取得します。

- PicoTetris／PicoEditなど、既存の外部アプリを同じsourceから再ビルドする
- R5、NEXT-1、NEXT-2など、外部アプリを含む歴史的な実機相関recordを再現する
- speaker校正firmwareを使って、キー入力なしの実機音声判定を行う
- 外部アプリ固有のscenario、UF2、実機証拠を参照する

これらは「その検証対象の入力が不足している」という状態であり、エミュレーター本体の
runtime errorではありません。ただし、既存targetを継承するフォークでは無視せず、対象source
またはsource bundleを取得してから回帰を実行してください。

## 配置とGit境界

共有workspaceで管理する場合の推奨配置は次です。

```text
/path/to/codex/
  picocalc_emu/
  picoem-picocalc/
  picocalc_emu_ext/       # 任意。各アプリは独立したGit repository
    picotetris/
    picoedit-picocalc/
    picocalc-audio/
    picocalc-multicore/
    picocalc-speaker-calibration/
```

target registry内の`repository_directory`やtarget IDは、上記の物理pathを意味しない論理識別子
です。固定recordのprovenanceを書き換えて配置を合わせてはいけません。新しい外部アプリを
検証するときは、BINとscenarioの絶対pathを明示し、必要なら新しいtarget revisionを追加します。

`firmware-validation/records/`とregistryは証拠・契約です。registryにあるartifact SHAだけでは
再ビルドできないため、sourceを持たないtargetを変更・再生成する場合は、再現可能なsourceを
別途用意するか、新しいtargetとしてsource、toolchain、BIN、UF2、scenarioを一緒に固定します。

## 公開clone後の最小構成

```sh
git clone https://github.com/FuyukiYoneyama/picocalc_emu.git
git clone --recursive https://github.com/FuyukiYoneyama/picoem-picocalc.git
cd picocalc_emu
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output /tmp/MyApp
```

外部workspaceをcloneしていないことによるエラーは、この最小構成では発生しません。
