# PicoCalc音量・極端な歪みの検査

この文書は、PicoCalc向けアプリがエミュレーター上では正常でも、実機で必要以上に小さい音のまま
完成することを防ぐための現行手順です。DOOM固有の修正規則ではなく、PicoCalcアプリ全般の
project-level品質契約です。

## 基本方針

PicoCalcには物理ボリュームがあります。ソフトウェアは原則として利用可能なデジタルレンジを十分に
使い、最終音量は利用者が物理ボリュームで下げます。音量を確保するための短い、低頻度の飽和は
直ちに不合格としません。問題にするのは次の2点です。

- 有音区間でもデジタルレベルが必要以上に低い
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

低音量判定には、長い無音で薄まる`stream_rms`ではなく`max_window_rms`を使います。rail値は
「1回でも発生したら失敗」には使いません。1024 frame以上のstreamでは末尾の不完全blockを
最大値候補にしないため、終了直前の短いspikeだけで音量条件を通過できません。stream全体が
1024 frame未満の場合だけ、その全streamを1 blockとして評価します。

## project quality contract schema 2

音声を出すrelease scenarioは、exact stream oracleに加えてアプリ固有の範囲を宣言します。

```json
{
  "schema_version": 2,
  "contract_id": "my-audio-v2",
  "report_schema": 8,
  "required_capabilities": {
    "audio_sink": {
      "expected_count": 49152,
      "expected_sha256": "<64 lowercase hex>",
      "quality": {
        "minimum_max_window_rms": 8192,
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

上の数値は仕組みを示す開始例です。8192は16-bit full scaleのおよそ1/4、4800 frameは48 kHzで
100 ms、250000 ppmはrail sample 25%です。音色、効果音、scenario区間が違えば同じ値を機械的に
流用せず、raw WAVの試聴と実機相関から契約値を固定します。軽い音割れを許容するため、rail上限は
意図的に緩く設定します。

```sh
python3 tools/picocalc.py judge-report \
  --contract /path/to/project-quality.json \
  --report /tmp/run-report.json \
  --audio-analysis /tmp/audio-analysis.json \
  --json /tmp/project-quality-result.json
```

schema 2契約で解析artifactがない、schemaが違う、backend commit/dirty状態、firmware SHA-256、
PCM SHA-256またはframe数がraw reportと一致しない場合は`cannot_judge`です。低音量または契約を
超える極端なrail使用は`fail`、
範囲内の短い飽和は`pass`です。schema 1契約は従来のexact count/hashだけを評価する互換経路として
残します。

## 実機との責任境界

この検査は「デジタル信号が小さすぎる」「極端にrailへ張り付く」を検出できますが、実際の音圧や
聴感を保証しません。最終判断は同一UF2をPicoCalcで鳴らし、物理ボリューム、内蔵speaker、必要なら
headphone出力で確認します。固定`1 kHz / -6 dBFS`信号はPWM経路比較用であり、アプリ音量の上限を
意味しません。
