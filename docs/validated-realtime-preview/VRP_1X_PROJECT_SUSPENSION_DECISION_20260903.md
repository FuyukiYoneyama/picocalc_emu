# 1倍速 UX プロジェクト中断判断

Status: **suspended / non-qualifying**
Decision date: 2026-09-03
Scope: `picocalc_emu` Validated Realtime Preview and its `picoem-picocalc` backend

## 決定

1倍速UXプロジェクトは、repository-owned `LOAD-0（最大級の継続負荷性能テスト0番）`
r1のprototype、1／2 virtual-second smoke、120秒non-formal vertical slice、
preview-only targetのreceipt／admission／headless経路を確認した時点で中断する。
これはVRP-0〜VRP-4の完了やVRP-5 reusable backend-pin preflightを取り消す判断ではなく、
準備段階の成果を正式qualificationへ誤昇格させないための停止である。

`ux`モードは概念設計のみで、未採用・未実装のままとする。120秒sliceの完了を理由に、
3回determinism、10 virtual分以上の準備run、VRP-5 qualification、または条件付きVRP-7
最適化を自動開始しない。

## 確認済みの範囲

- LOAD-0のsource／fixtureはrepository-owned r1として実装済みで、固定条件のclean-clone build再現性、runtime／input smoke、120秒sliceを確認済み。
- 120秒sliceはbuild → run → report → receipt → admission → headless previewの経路確認であり、LOAD-0 completion、1倍速判定、最適化実装ではない。
- 120秒の観測値は、120仮想秒を6,219.928 wall-clock秒で実行したLOAD-0固有の値である。`real_time_percent`は`仮想実行秒 / host wall-clock秒 × 100`から導出した`1.929283%`であり、raw recordに存在する`virtual_over_wall_ratio`の表示変換である。新しいmachine-readable schema fieldを追加した結果ではない。
- `100%`がwall-clock 1倍を意味する。したがって`1.929283%`は現行エミュレーター全体、Tetris（軽ゲーム実装）、または1倍速UXの性能値ではない。

## 未完了のため正式成果物にしない範囲

- 3回determinism、10 virtual分以上の準備run、threshold／判定式の凍結、VRP-5 formal qualification。
- headless runnerのwall-clock値だけでは得られないinput-to-visible-responseのUX測定。
- 実機相関、物理キーボード操作、hardware-audio fidelity。
- `firmware-validation/records/vrp-load0-determinism-20260830-01/` は現時点でRun-01だけの未完了記録であり、manifest／Run-02／Run-03／SHA256SUMSを備えた正式determinism evidenceではない。今回のcommitには含めない。
- `LOAD0_HARDWARE_TEST_RUNBOOK.md` は実機試験未実施の手順テンプレートで、環境依存のローカルpathを含むため、公開手順として整備するまで今回のcommitには含めない。

上記の未完成ファイルは削除せず、正式証拠・公開手順として案内しない。後日再開する場合は、完全な記録パッケージまたは明示的な破棄判断を先に作る。

## 再開条件

1. LOAD-0を正式比較workload、人工高負荷regression、または保留対象のどれとして扱うかを役割レビューで決定する。
2. threshold、lag、drop、underrun、digest、run数、統計方法をqualification開始前にdecision recordへ凍結する。
3. 同一fixtureで3回分の完全なrecord、manifest、artifact hashを作成し、各runの欠落をなくす。
4. Tetris（軽ゲーム実装）とLOAD-0を別workloadとして測定し、1倍速UXを名乗る場合はinput-to-visible-responseを別途受入する。
5. hardware correlationは同一artifactを使う独立gateとして、実機実施後にのみ記録する。

## commit／push境界

今回pushする親リポジトリの変更は、状態訂正、索引、判断記録などの文書に限定する。
未完了determinism recordと未実施hardware runbookはstageしない。

`firmware-targets.json`が参照するbackend commitをremoteから取得可能にするため、pushは
`picoem-picocalc`の`main`を先に行い、その後`picocalc_emu`の`main`を行う。既存の
`v0.1.0` tagは移動・再pushせず、force pushもしない。歴史的な`c1c20d7...` pinを含む
既存evidenceは不変資料として保持する。
