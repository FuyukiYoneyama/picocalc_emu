# 局所テストと独立レビュー

## supervisor実行

製品sourceを変更する前に、新規integration testを`f32eba1`へ追加して実行した。
初回はBusのprivate field参照によりcompile error（E0616）。公開accessor
`Bus::audio_sink_snapshot()`へtestだけを修正した後、実際の回帰条件へ到達した。
どちらの失敗も共有`workspace-management/OPERATION_FAILURE_LOG.md`に記録した。

```text
cargo test --locked --release -p rp2040-emu --test dma_idle_allocations -- --nocapture
assertion failed: 1,000 direct DMA updates
left: (3000, 3000)
right: (0, 0)
test result: FAILED. 0 passed; 1 failed
exit: 101
```

三つの確保を遅延する製品変更後、次を実行した。

```text
cargo test --locked --release -p rp2040-emu --lib audio_sink::tests
test result: ok. 10 passed; 0 failed; 1257 filtered out

cargo test --locked --release -p rp2040-emu --test dma_idle_allocations
test result: ok. 1 passed; 0 failed

rustfmt --edition 2024 --check crates/rp2040-emu/tests/dma_idle_allocations.rs
exit: 0

git diff --check
exit: 0
```

既存audio sourceには今回より前の整形差があるため、workspace全体のformatを変更していない。
新規testを含む最終candidateは`e83759f68e4d6ee58731fc98e26e84838a8170bd`へcommitし、
cleanな状態でharness releaseをbuildした。短い起動preflightでもdirty=falseを確認した。
上のログは実行結果の抜粋であり、全体性能や全packageの合格を意味しない。

## Lunaの読み取り専用レビュー

ユーザーが許可した`gpt-5.6-luna`へ、baselineからcandidateまでの2ファイルだけを指定して依頼した。
audio観測、preview上限、repeated-enable、reset、無音の契約について具体的欠陥の指摘はなかった。
Lunaは編集・build・test・commit・pushを実行していない。採否はsupervisorが実測と併せて判断する。

## 追加回帰入力の棚卸し

PicoEdit／音声／multicoreは固定sourceとBSPが既存外部workspaceに残る。
Lunaが確認した復元候補の条件は次のとおり。Tetrisの事前条件成立前にbuildしない。

| source | commit | UTC timestamp | BSP identity | reference tone |
|---|---|---|---|---|
| picoedit-picocalc | 82a6e4c76272e8f520d2f8cba42f1a7e549d4933 | 2026-08-09T08:00:00Z | a0041b56516e | OFF |
| picocalc-audio | 724b3ac74f1401a19d6310af387c65ad1e5476a4 | 2026-08-09T12:00:00Z | c55a63bdcbd0 | OFF |
| picocalc-multicore | e9e99f0bfde7b2706fbe7f5a2a92331eed141c98 | 2026-08-09T11:30:00Z | 0224204f6305 | ON |

SDK 2.2.0、GCC 13.2.1、CMake 3.28.3、Ninja 1.11.1、Release、pico、pio-rgb565。
共通BSP tree SHAは`997a68966d6c38c786e7045a2b703f6c02a247b5e0a8956f0153d809080cb73c`。
sourceがあることと固定BINの再現成功は別であり、Tetris以外の再現はこの棚卸し時点では未検証。
