# NEXT-2B first backend run (retained failure)

契約 `next2-audio-v2-20260809` が要求した「最初のbackend runは失敗しても保存する」ための
時点証拠である。後からPASS recordへ置換しない。

## Invocation preflight

最初のrunner起動は `picocalc_emu` をcwdにしていたため、backendが相対path
`roms/rp2040/bootrom-rp2040-b2.bin` を解決できず、firmware実行前にexit 2となった。
所要は0.00秒だった。backend repoをcwdにする正規呼出しへ直し、同じBINと判定条件で
最初のfirmware runを行った。

## First firmware run

- firmware app commit: `dd95162ec161b05efa02a7f0ede78fca82d185aa`
- BIN SHA-256: `95ed84bf89381e6644f6650b0ad2fecf5d6604d75b3903367a63631ce02009ca`
- backend commit: `94818f8a4c95a0d8e458843f163556be83411a6a`
- scenario: `scenarios/next2-audio-v2.json`
- wall time: 27.80秒
- virtual cycles: 277,523,041
- firmware authority: 5 markerと最終LCDはPASS
- backend verdict: **FAIL** (`audio_sink_mismatch`)
- observed DMA-origin PWM5_CC writes: 24,895 / 49,152
- observed stream SHA-256: `845ae384fa617b774c95aec35f2696e61c65328235b6afcc48e2222397bdc954`

`run-report.json`、`uart.log`、`snapshots/next2-audio-final.png`をそのまま保持する。firmwareの
自己申告だけなら通過していたが、DMA境界oracleが偽陽性を拒否した実例である。

## Root cause and versioning

調査で3点を分離した。

1. active中の同一level IRQをNVICへ再pendingし、DMA handlerが二重実行されていた。
2. v2 oracleはcanonical error-diffusion quantizerを通さず、producer dutyをsink dutyと
   誤認していた。
3. v2は128-frame DMA block内のtimer cadenceと、IRQ refill後のsoftware-retrigger境界gapを
   区別していなかった。

v1/v2の履歴は書き換えず、訂正は `next2-audio-v3-20260809` としてversioningした。
