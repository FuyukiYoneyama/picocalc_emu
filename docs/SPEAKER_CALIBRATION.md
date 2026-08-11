# 内蔵speakerの動画校正

この文書の校正firmwareは任意の外部workspace（`picocalc_emu_ext`）で管理します。
外部workspaceを取得していない場合は、この校正手順だけを実行できませんが、通常のアプリ生成・
ビルド・エミュレーター検証には影響しません。配置と取得方法は
[外部workspaceの説明](EXTERNAL_WORKSPACE.md)を参照してください。

## 目的

firmware backendのaudio sinkと`AUDIO_LEVEL_QUALITY.md`は、PWMへ到達したdigital streamのexactness、
level、rail使用を検査します。しかしPicoCalcのamp、内蔵speaker、筐体が特定の低音やtransientで
非線形破綻するかはdigital sampleだけから決められません。

この層を埋めるため、任意の外部workspaceの`picocalc-speaker-calibration`に、キー入力不要の自動再生firmwareと
動画解析器を用意します。DOOMなど個別アプリを校正信号として使いません。既知波形をPicoCalc実機で
鳴らし、phone動画の音声を同期signatureで自動分割して、speaker側の破綻境界を測ります。

## 責任分担

| 層 | 権威を持つ判定 |
|---|---|
| firmware/backend | DMA/PWM timing、count/hash、underrun/drop、digital level、極端なrail使用 |
| speaker calibration | amp/speaker/筐体を通したharmonic growth、compression、transient破綻の候補抽出 |
| 人間の実機聴取 | 全体音量とpercussion／破裂音の最終合否 |
| アプリ | mixer balance、意図した音色、移植元との整合 |

アプリ開発者へ全責任を押し戻しません。校正で既知の危険候補を除外し、通常開発ではエミュレーター上の
digital signalを既知recordへ照合します。ただしphone録音からspeakerの完全なtransfer functionを
逆算せず、最終release候補は[2問式の実機聴取](SPEAKER_LISTENING_ACCEPTANCE.md)で人間が判定します。
控えめな音でも人間が許容すればPASSであり、音量改善は任意です。

## 初回と定常運用

初回recordingでは、同一周波数の低level caseをbaselineとして、明確なharmonic増加やlevel compressionを
自動FAILにします。同期signatureを識別できない録音品質不足は`cannot_judge`です。個別刺激だけが
noise floor未満ならspeakerの再生限界として`unobservable`に分け、残る境界ケースだけ人間へ問い合わせます。

```text
自動FAIL             -> 不合格境界の候補
自動的に問題なし     -> 暫定safe（初回だけでは正式PASSにしない）
境界付近             -> review/*.wavだけ人間確認
同期全体の識別不足     -> cannot_judge、再撮影
個別caseがnoise未満   -> unobservable、speaker/profileの再生限界
```

人間が確認したrecordをversioned hardware evidenceに固定すると、その後は同じ既知刺激の再測定を自動で
比較できます。recordには少なくともcalibration-plan SHA-256、UF2 SHA-256、video SHA-256、設置条件、
各caseのmetricを含めます。一つの合成刺激から得た閾値を「PicoCalc一般の音楽・ゲーム音声の安全値」として
扱いません。

## 実行

詳細な撮影手順とUF2の場所は、外部workspaceを取得した場合に、その中の
`picocalc-speaker-calibration/README.md`を参照します。
解析器は次です。

```sh
python3 tools/analyze_speaker_calibration.py recording.MOV \
  --plan /path/to/picocalc_emu_ext/picocalc-speaker-calibration/calibration-plan.json \
  --output /tmp/picocalc-speaker-analysis
```

解析器はplan内容のSHA-256を再計算し、動画自体のSHA-256もrecordします。複数同期markerから動画のoffset、
clock scale、最大residualを求めるため、uf2loader操作を含む長い冒頭やphone clock driftを時刻ずれとして
誤判定しません。同期不足、clock scaleが1%を超える記録、residual 200 ms超は拒否します。
終了コードは`0=versioned profileによるPASS`、`1=既知の破綻でFAIL`、`2=人間確認が必要または判定不能`
です。初回解析の`review_required`を成功終了にせず、人間の聴取を省略できないようにします。

## 現在の境界

2026-08-11に全域v1と低域stress v2を実機測定しました。v1は315〜6300 Hzで明確な破綻を示さず、
v2は低音だけの160→60 Hz chirpが0 dBFSでもspeaker／phoneの観測限界以下でした。したがってv2の
`automatic_failures=0`をPASSへ昇格していません。

元のDOOM不良動画を再確認すると、問題音は約2.22秒周期の打撃音に伴い、3 kHz以上の広帯域成分が
約0.11秒残る拳銃音状の破裂でした。正常だが小音量だった動画では対応するattackが約0.02秒で減衰します。
このためpercussion v3は、100 Hzの負荷と1 kHzの可聴attackを持つ同一120 ms波形を-18〜0 dBFSで
段階再生し、3 kHz以上のresidue growthを測ります。DOOMの音源やデータは含みません。

percussion v3実機recordでは、観測可能な-12〜0 dBFSがほぼ線形で、DOOMの拳銃音状破裂を再現しません
でした。これは「高levelの打撃音がすべて壊れる」という仮説を否定しますが、DOOM-safe境界にはなりません。

最初のcontent-specificな人間判定基準は、既知良品v0.1.1と既知不良v0.1.2です。v0.1.1は全体が
控えめでもBGMとして成立し、過渡音が破綻していないaccepted safe referenceです。人間がその音量でよいと
判断すれば追加調整しません。v0.1.2は全体音量が適切でもpercussionが過大かつ破綻したknown-bad
referenceです。合成刺激とphone解析はこの人間判定を置き換えず、未知候補を減らす補助層として維持します。
