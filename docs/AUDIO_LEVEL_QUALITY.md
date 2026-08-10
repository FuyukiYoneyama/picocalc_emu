# PicoCalc音量・極端な歪みの検査

この文書は、PicoCalc向けアプリの最終digital PWM入力を測り、exactness、極端なrail使用、音量改善の
参考値を分離する手順です。DOOM固有の修正規則ではなく、PicoCalcアプリ全般のproject-level品質契約です。

## 基本方針

PicoCalcには物理ボリュームがあります。十分な音量を目指すことはできますが、音量最大化は合格条件では
ありません。控えめでもアプリとして成立し、実機で人間が許容した音はPASSです。短い、低頻度の飽和も
直ちに不合格としません。機械契約では次を分けます。

- digital levelが推奨範囲より低いというadvisory
- PWM railへ長時間または極端な比率で張り付き、聴感上の破綻が強く疑われる

underrun、drop、転送間隔、exact count/hashは従来どおり別契約で検査します。音量検査はそれを
置き換えず、追加します。

## 観測境界

firmware backendはDMAがPicoCalcのPWM slice 5 CCへ実際に書いた8-bit左右dutyを観測します。
解析値とWAVは、そのdutyを次の対応でsigned 16-bit PCMへ決定的に復元したものです。

```text
pcm = duty * 257 - 32768
```

これはアプリの最終digital PWM入力であり、speaker、アンプ、筐体、物理ボリューム、部屋、マイクを
モデル化したものではありません。`rail_sample_count`もpost-quantizerのdutyが0または255だった
回数であり、source mixer自身のclip counterと同義ではありません。

## 解析artifactとraw WAV

通常のschema 8 reportを変えず、独立したschema 1 artifactを出します。
正典schemaは
[`audio-analysis.schema.json`](../firmware-validation/audio-analysis.schema.json)です。

```sh
picocalc-run \
  <通常のPicoCalc firmware引数> \
  --audio-analysis /tmp/audio-analysis.json \
  --audio-wav /tmp/audio-raw.wav
```

`--audio-analysis`はstreaming統計だけを取り、sample列を保持しません。`--audio-wav`を指定した場合
だけinterleaved PCMを保持します。WAVは48 kHz、stereo、signed 16-bitで、**正規化もgain変更も
しません**。聞きやすく正規化した派生物を作る場合も、このraw WAVを元証拠として残します。

主な値は次のとおりです。

| field | 意味 |
|---|---|
| `peak_abs_left/right` | 各channelの最大絶対値。full scaleは32768相当 |
| `stream_rms` | 無音を含む全streamの左右合成RMS |
| `max_window_rms` | 完全な1024 frame（約21.3 ms）非重複blockの最大左右合成RMS |
| `active_frame_ratio_ppm` | どちらかが絶対値512以上だったframe比率 |
| `rail_sample_ratio_ppm` | 左右sample全体のうちduty 0/255だった比率 |
| `max_consecutive_rail_frames` | どちらかのchannelがrailだった最大連続frame数 |
| `dc_offset_left/right` | stream全体のsigned平均 |

音量改善の参考値には、長い無音で薄まる`stream_rms`ではなく`max_window_rms`を使います。ただし
これは最も大きい約21.3 ms区間であり、平均的なBGMの満足度ではなくdrumなどの過渡音を選ぶことが
あります。従ってspeaker loudnessの合否やmaster gainの目標に単独で使いません。rail値は
「1回でも発生したら失敗」には使いません。1024 frame以上のstreamでは末尾の不完全blockを
最大値候補にしないため、終了直前の短いspikeだけで音量条件を通過できません。stream全体が
1024 frame未満の場合だけ、その全streamを1 blockとして評価します。

## project quality contract schema 3

新しい音声release scenarioは、exact stream oracle、speaker安全性を証明しないdigital rail上限、任意の
音量改善目安を宣言します。

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

上の数値は仕組みを示す開始例です。8192は16-bit full scaleのおよそ1/4ですが、これを下回っても
`audio_level_below_preferred_range`というadvisoryになるだけで、総合判定はFAILになりません。
4800 frameは48 kHzで100 ms、250000 ppmはrail sample 25%です。音色、効果音、scenario区間が違えば
同じ値を機械的に流用せず、raw WAVと実機相関からアプリ固有値を固定します。軽い音割れを許容するため、
rail上限は意図的に緩く設定します。

```sh
python3 tools/picocalc.py judge-report \
  --contract /path/to/project-quality.json \
  --report /tmp/run-report.json \
  --audio-analysis /tmp/audio-analysis.json \
  --json /tmp/project-quality-result.json
```

schema 3契約で解析artifactがない、schemaが違う、backend commit/dirty状態、firmware SHA-256、
PCM SHA-256またはframe数がraw reportと一致しない場合は`cannot_judge`です。推奨音量未満は
advisory、rail上限超過は`fail`、範囲内の短い飽和は`pass`です。
schema 1はexact count/hashだけ、schema 2は`minimum_max_window_rms`未満をFAILにする旧互換契約として
意味を変えずに残します。人間が許容できる控えめな音を新しくschema 2へ固定しないでください。

## 内蔵speakerとの責任境界

この検査は「デジタル信号が小さすぎる」「極端にrailへ張り付く」を検出できますが、実際の音圧や
内蔵speaker／筐体の非線形破綻を保証しません。既知刺激とphone動画を解析する
[内蔵speaker校正](SPEAKER_CALIBRATION.md)で候補を絞りますが、最終的な聴感は
[2問式の実機通過基準](SPEAKER_LISTENING_ACCEPTANCE.md)で人間が判定します。

固定`1 kHz / -6 dBFS`信号はPWM経路比較用であり、アプリ音量の上限やspeakerの全周波数safe境界を
意味しません。

DOOM v0.1.1は`max_window_rms=7595`で控えめでしたが、BGMとして成立し、過渡音に破綻がないため、
人間が許容すればPASSです。音量改善は任意であり、追加調整を強制しません。

一方、v0.1.2は全体音量が適切でも、digital peak約`-5.9 dBFS`、`max_window_rms=11391`、rail使用0の
状態で周期的なdrum attackが拳銃音状に破綻しました。従って「railへ達していない」はspeaker-safeの
証明ではなく、大きい`max_window_rms`も良い音の証明ではありません。全体が適切で過渡音だけが破綻した
場合は、全体音量を維持し、percussion/SFX bus、compressor、最後のlimiterの順で過渡音だけを下げます。
