# 外部プロジェクトのprovenanceと音声品質ゲート

この文書は、`picocalc.py new`で生成したプロジェクトや既存コードを持ち込んだプロジェクトで、
BSPの由来と音声の合否を曖昧にしないための現行手順です。

## BSP provenance

生成プロジェクトの`.picocalc-project.json`は、BSP生成元のfull commitと`bsp/`全体の
SHA-256を保持します。次の検査は、現在の`bsp/`がその固定treeと完全一致するときだけ成功します。

```sh
python3 /path/to/picocalc_emu/tools/picocalc.py verify-project \
  --project /path/to/MyApp
```

終了コードは`0=一致`、`1=tree不一致`、`2=metadata欠落・破損等で判定不能`です。
schema 1の旧project metadataにはBSP source commit/tree hashがないため移行不能です。現在の
generatorでprojectを再生成し、アプリsourceだけを移してください。

生成プロジェクトで直接`cmake -S . -B build`を実行した場合も、コピーされた
`bsp/cmake/bsp_provenance.py`が同じmetadataとtree hashを読みます。BSPは外側の
アプリGit repositoryを探索しません。

- 一致: `bsp_git=<生成元commitの先頭12桁>`
- tree不一致: `bsp_git=<commit>-dirty`
- metadataなしのstandalone BSP: `bsp_git=untracked`
- metadataが存在するが壊れている: CMake configure失敗

tree SHA-256は、意図的に`bsp/`配下の**全regular file**を対象にします。`__pycache__`や`.pyc`も
追加tree内容なので、除外して同一扱いにはしません。検査がそのような一時ファイルを示した場合は
BSPから削除して再実行してください。この定義は既存の凍結provenanceと同じです。

release用の直接CMake configureでは、tree不一致も即時失敗させられます。

```sh
cmake -S . -B build -DPICOCALC_REQUIRE_CLEAN_BSP_PROVENANCE=ON
```

生成metadataがある場合は、`PICOCALC_BSP_GIT`を明示しても自動計算値と照合され、不一致なら
configureが失敗します。metadataのないstandalone BSPで明示した場合だけ、呼出側がidentityの
責任を持ちます。通常は`picocalc.py build`または上記の自動検査を使い、手入力しません。

## raw reportとproject-level判定を分ける

firmware backendのschema 8 reportは、runnerへ実際に渡された受入条件の結果です。
`audio_sink.status`にはdigital sinkの観測状態も出ますが、`expected_count`と
`expected_sha256`を指定していないrunは、プロジェクトの音声品質を判定していません。

既存のschema 8とversioned recordは不変証拠なので、フィールドの意味を後から変更しません。
外部プロジェクトではproject quality contractを追加し、観測と評価を別の結果へ正規化します。

契約例:

```json
{
  "schema_version": 1,
  "contract_id": "my-audio-v1",
  "report_schema": 8,
  "required_capabilities": {
    "audio_sink": {
      "expected_count": 49152,
      "expected_sha256": "<64 lowercase hex>"
    }
  },
  "report_checks": [
    {"path": "unsupported_mmio", "op": "length_eq", "value": 0}
  ]
}
```

正典schemaは
[`project-quality-contract.schema.json`](../firmware-validation/project-quality-contract.schema.json)
です。backend実行時にも同じoracleを渡します。

```sh
picocalc-run ... \
  --expect-audio-sink-count 49152 \
  --expect-audio-sink-sha256 <64-lowercase-hex> \
  --json /tmp/run-report.json

python3 tools/picocalc.py judge-report \
  --contract /path/to/project-quality.json \
  --report /tmp/run-report.json \
  --json /tmp/project-quality-result.json
```

project quality resultは次を区別します。

- `observation_status`: backend modelが観測した生の状態
- `oracle_present`: reportにcountとSHA-256の両方があるか
- `oracle_matches_contract`: project契約と同じoracleで走ったか
- `evaluation_status`: `not_evaluated`、`pass`、`fail`
- schema 3の`advisories`: 合否を変えない音量改善候補

契約が音声を必須としているのにoracleなしで走った場合、raw reportの総合verdictが`pass`でも
project qualityは`cannot_judge`（終了コード2）です。oracleが一致したうえでsinkが不一致なら
`fail`（終了コード1）、すべて一致したときだけ`pass`（終了コード0）です。
report schemaが契約と違う場合は、内部フィールドを信用せず常に`cannot_judge`です。schemaが一致し、
runner自体または明示report checkに既知の失敗がある場合は、音声が未評価でも既知の`fail`を優先します。

schema 1契約はexact count/hashの互換経路です。新しい音声release projectではschema 3を使い、
独立した`--audio-analysis` artifactに対して推奨区間RMSと、極端なPWM rail使用の上限を宣言します。
解析artifact自体は、48 kHzの凍結形式がschema 1、その他の実効サンプルレートがschema 2です。
固定48 kHzを要求する既存targetのoracleを、別レートへ緩めてはいけません。別レートのアプリは
新しいtarget／contractとして、観測したcount・SHA・タイマー分数を別途固定します。
推奨RMS未満はadvisoryでありFAILではありません。短い、低頻度のrail到達も許容し、単なるclip発生
だけでは不合格にしません。ここでいうproject quality contract schema 2は最低区間RMSを必須にした
旧契約であり、解析artifact schema 2（可変サンプルレート）とは別物です。

```json
{
  "schema_version": 3,
  "contract_id": "my-audio-v3",
  "report_schema": 8,
  "required_capabilities": {
    "audio_sink": {
      "expected_count": 49152,
      "expected_sha256": "<64 lowercase hex>",
      "quality": {
        "advisory_minimum_max_window_rms": 8192,
        "maximum_rail_sample_ratio_ppm": 250000,
        "maximum_consecutive_rail_frames": 4800
      }
    }
  },
  "report_checks": [
    {"path": "unsupported_mmio", "op": "length_eq", "value": 0}
  ]
}
```

backend実行時に`--audio-analysis /tmp/audio-analysis.json`を追加し、判定時にも同じartifactを渡します。

```sh
python3 tools/picocalc.py judge-report \
  --contract /path/to/project-quality.json \
  --report /tmp/run-report.json \
  --audio-analysis /tmp/audio-analysis.json \
  --json /tmp/project-quality-result.json
```

値の意味、非正規化WAV出力、PicoCalcの物理ボリュームを前提にした判定方針は
[`AUDIO_LEVEL_QUALITY.md`](AUDIO_LEVEL_QUALITY.md)を参照してください。これはdigital
DMA-to-PWM境界の判定です。実機のspeaker、アナログ波形、実際の音圧と聴感は、同一UF2を
[`SPEAKER_LISTENING_ACCEPTANCE.md`](SPEAKER_LISTENING_ACCEPTANCE.md)の2問で別に確認します。
`acceptable_quiet`を人間が許容した場合はPASSであり、音量向上を強制しません。
