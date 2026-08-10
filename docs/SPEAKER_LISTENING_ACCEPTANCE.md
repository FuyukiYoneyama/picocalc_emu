# 内蔵speakerの実機聴取と通過基準

## 目的

内蔵speakerの最終的な音量、音源間のバランス、破裂音や聴感上の歪みは、人間がPicoCalc実機を
聴いて判定します。エミュレーターのdigital PCM解析とphone動画解析は候補の絞り込みと証拠保存を
担当しますが、人間の聴感を自動判定で置き換えません。

音量の最大化は合格条件ではありません。破綻のない音がアプリとして成立し、人間が許容した場合は
その時点でPASSです。「もう少し大きくしたい」は任意の改善要求であり、追加調整を強制しません。

## 必須の2問

物理ボリュームを最大にし、内蔵speakerでrelease候補を聴いて次の2点だけを回答します。

1. 全体の音量は適切か
2. パーカッションや破裂音は、大きすぎたり小さすぎたりせず、破綻していないか

機械可読値は次です。

| 項目 | 値 | 意味 |
|---|---|---|
| `overall_loudness` | `unacceptably_quiet` | アプリとして成立しないほど小さい |
|  | `acceptable_quiet` | 控えめだが成立し、このまま採用できる |
|  | `appropriate` | 適切 |
|  | `too_loud` | 全体として過大 |
| `percussion_and_transients` | `too_quiet` | 相対的に弱すぎる |
|  | `appropriate` | 適切で破綻なし |
|  | `too_loud` | 相対的に過大 |
|  | `distorted` | 破裂音、異常な割れ、その他の破綻がある |

通過条件は、`overall_loudness`が`acceptable_quiet`または`appropriate`であり、かつ
`percussion_and_transients=appropriate`であることです。`acceptable_quiet`を選び、追加調整を
希望しなければ、advisoryも追加作業もなくPASSにします。

## 判定から調整指示への対応

| 全体 | パーカッション／過渡音 | 判定と指示 |
|---|---|---|
| `acceptable_quiet` | `appropriate` | PASS。人間が許容すれば調整終了 |
| `appropriate` | `appropriate` | PASS |
| `acceptable_quiet` | `appropriate`、かつ改善希望 | PASSのまま、安全基準から任意調整 |
| 許容範囲 | `too_loud`／`distorted` | FAIL。全体音量を維持して過渡音だけ下げる |
| 許容範囲 | `too_quiet` | FAIL。全体音量を維持して過渡音だけ上げる |
| `unacceptably_quiet` | `appropriate` | FAIL。過渡音を保護しながら平均音量を上げる |
| `too_loud` | 任意 | FAIL。全体を下げた後に過渡音を再確認 |

全体音量が適切で過渡音だけが破綻する場合、master gainを一律に下げるという曖昧な指示を返しません。
推奨順序は、個別percussion/SFX busの調整、最終mix compressor、最後の安全limiterです。digital
clipがないのに実機だけ破綻する場合、単純なsample peak limiterだけでは十分ではありません。

調整は破綻のない既知の基準から`0.5`〜`1 dB`ずつ行い、最初に破綻した候補の一段前を上限候補に
します。装置差と電源状態を考慮し、破綻境界そのものではなく安全余裕を残します。

## 移植アプリ

移植元の音色と音量バランスを原則として尊重します。問題が見つかった場合は、可能なら次を区別します。

1. 移植処理が移植元と異なるバランスを作った場合は、移植を修正する
2. 移植元とdigital balanceが一致し、PicoCalcだけで破綻する場合は、PicoCalc最終出力段で適応する
3. 移植元と一致し、PicoCalcでも人間が許容した場合は、追加調整しない

移植元比較をまだ行っていないことは、それ自体を聴取FAILにはしません。記録の
`source_mix_comparison=not_checked`で未確認範囲を明示します。

## 初期基準

最初の相関pairはPicoCalc DOOMの実機結果です。この名称は汎用speaker profileではなく、今回の
判断を固定する識別子です。

- `v0.1.1`: 全体は控えめだがBGMとして成立し、過渡音の破綻なし。人間が許容すればPASSとなる
  accepted safe reference
- `v0.1.2`: 全体音量は適切だが、drum／percussionが過大で拳銃音状に破綻。既知のFAIL reference

`v0.1.2`はdigital peak約`-5.9 dBFS`、`max_window_rms=11391`、rail使用0でした。したがって
rail未到達や大きい`max_window_rms`をspeaker-safeの証明にしてはいけません。逆に`v0.1.1`の
`max_window_rms=7595`が開始例8192を下回ることも、実機PASSを覆す理由にはなりません。

## 記録と判定

入力schemaは
[`speaker-listening-assessment.schema.json`](../firmware-validation/speaker-listening-assessment.schema.json)、
判定器は`tools/judge_speaker_listening.py`です。BIN、UF2、動画のSHA-256と、実際の起動経路を結びます。
一般ユーザーの経路を優先し、通常は`launch_method=uf2loader`を使います。BOOTSEL固有の試験だけ
`bootsel`を選びます。既存動画で起動経路を証明できない場合は推測せず`not_recorded`とします。

```json
{
  "schema_version": 1,
  "assessment_id": "example-safe-reference",
  "application": {"name": "Example", "version": "1.0"},
  "artifact": {
    "bin_sha256": "<64 lowercase hex>",
    "uf2_sha256": "<64 lowercase hex>"
  },
  "evidence": {
    "video_file": "recording.MOV",
    "video_sha256": "<64 lowercase hex>"
  },
  "conditions": {
    "audio_path": "built_in_speaker",
    "physical_volume": "maximum",
    "launch_method": "uf2loader"
  },
  "porting_context": {"source_mix_comparison": "not_checked"},
  "human_assessment": {
    "overall_loudness": "acceptable_quiet",
    "percussion_and_transients": "appropriate",
    "adjustment_requested": false,
    "notes": "BGMとして成立しており、この音量で許容する"
  }
}
```

```sh
python3 tools/judge_speaker_listening.py assessment.json \
  --json listening-result.json
```

終了コードは`0=PASS`、`1=FAIL`、`2=記録不備で判定不能`です。人間の回答をツールが推測したり、
動画のphone AGC値だけで書き換えたりしません。
