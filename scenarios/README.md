# Scenarios

実行ループの内側で評価されるJSON手順書を置く。形式と操作・条件の一覧は
[`../docs/SCENARIO_RUNNER.md`](../docs/SCENARIO_RUNNER.md)にある。

## `tetris-line-clear.json`

**目的は、ドッグフーディングで一度も発火させられなかったコード経路を発火させること。**

`DOGFOODING_20260805.md`は、`--keys`が起動前に固定文字列を積むだけであるために
「着地したら左へ3つ」のような条件付き操作が書けず、その結果PicoTetrisの
ライン消去が**一度も走らなかった**と記録している。このscenarioはそれを走らせる。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target picotetris-r3 --firmware <PicoTetris.bin> \
  --backend-dir <picoem-picocalc> \
  --snapshot-dir out/ --json out/report.json
```

結果は13ライン消去、スコア1400。所要は仮想3.7秒、実時間で約1分。

### 配置をどう決めたか

ゲームの乱数は種を固定したxorshiftで、`spawn()`は状態を更新するが決定的である。つまり
**ピース列は事前に分かる**。`tools/plan_tetris.py`はPicoTetrisの`src/game.cpp`の規則
（同じ形状表、同じ衝突判定、同じ壁蹴り順）をPythonへ書き写し、各ピースの置き場所を
定石のヒューリスティック（消去数・穴・高さ・凸凹）で選び、そこへ至るキー列を出力する。

出力前に**同じモデルで自己検証する**。計画した配置とキー列を再生した配置が食い違えば、
scenarioを書かずに落とす。

そのうえで、このscenarioは計画が予測した**最終スコアと行数を`assert`している**。
エミュレーターは「たまたま何か消えた」では通らず、プランナーが使った規則と
一致しなければならない。

### バーストを短く保つ理由

最初の版は「9回左へ寄せてからN回右」という素朴なキー列を使い、1バーストが
21キー＝42イベントになった。キーボードコントローラは31イベントしか保持できないため
（`SCENARIO_RUNNER.md`「コントローラの深さ」節）、末尾は捨てられていた。

現在は必要な回数だけ動かすので、最長でも9キー＝18イベントに収まる。プランナーは
出力前にこの上限を検査し、超えたら落ちる。

### このscenarioが見つけたもの

キーボードモデルのFIFOに上限がなく、滞留が32の倍数に達するとBSPの
`key_info[0] & 0x1f`が0を読んで**ドライバが恒久的に停止していた**。実機のコントローラは
5ビットでしか深さを報告できないので、その状態になり得ない。エミュレーター側の欠陥で
あり、`picoem-picocalc`の`Keyboard::MAX_QUEUED_EVENTS`で修正した。

### 再生成

```sh
python3 scenarios/tools/plan_tetris.py <ドロップ数> <ドロップ間の待ち ms> > out.json
```

対象は`~/pico_dvl/codex/picotetris`のPicoTetrisである。ゲーム側の
形状表・乱数種・重力周期のいずれかが変われば、プランナーもそれに合わせないと
予測スコアの`assert`が落ちる。**落ちるのは正しい**。それが、この2つが同じ規則を
見ているという主張の担保である。
