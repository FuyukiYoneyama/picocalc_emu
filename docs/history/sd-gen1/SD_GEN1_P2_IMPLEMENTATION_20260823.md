# SD-GEN-1-P2 最小 state machine 実装

実施日: 2026-08-23  
状態: **完了（feature-gated local candidate。P3のtrace／app回帰前）**

## 1. 実装範囲

`picoem-picocalc` commit `0e1288e4c516b7da3ad21f3cf1ec3532374ab8da`へ、
`sd-gen1-multiblock` featureを追加した。featureを有効にしたときだけ、次のstate machineが
有効になる。

- CMD18: CSを保持した2 block以上のread。各blockは`0xFE`、512 byte、CRC16を持つ。
- CMD12: CMD18のblock境界でstreamを停止する。
- CMD23: CMD25に先行するpre-erase countを保持し、stop時に実書込み数を照合する。
- CMD25: `0xFC`のblock token、512 byte、CRC16、accepted token、1 transferのbusy、
  `0xFD` stop tokenを処理する。
- CS途中解除、範囲外block、誤token、pre-erase count不一致をdiagnostic errorへ記録する。

既定featureでは従来のCMD17/CMD24のみの経路を使用し、通常のfirmware runnerや
`uf2loader-e2e` capabilityは変更していない。今回のP2は、実アプリがCMD18等を発行したことを
意味しない。P0で未観測だったcommandを、synthetic vectorで安全に試作した段階である。

## 2. byte-level vector

synthetic vectorは[`sd-gen1-p2-vectors-v1.json`](../../../firmware-validation/contracts/sd-gen1-p2-vectors-v1.json)に固定した。
代表的なcommand frameは次の通りである。

| 用途 | frame |
|---|---|
| CMD18、block 3開始 | `52 00 00 00 03 01` |
| CMD12停止 | `4c 00 00 00 00 01` |
| CMD23、count 2 | `57 00 00 00 02 01` |
| CMD25、block 3開始 | `59 00 00 00 03 01` |

readは各blockを`FE + 512 byte + FF FF`、writeは各blockを`FC + 512 byte + FF FF`
の後に`05`、busy `00`、最後に`FD`とする。payload値・block境界・tokenはfixtureに明記し、
単なる「CMDを受理した」というテストにしていない。

## 3. ローカル検証

```text
cargo test --release -p picocalc-board
  85 passed

cargo test --release -p picocalc-board --features sd-gen1-multiblock
  89 passed

cargo clippy --release -p picocalc-board -- -D warnings
cargo clippy --release -p picocalc-board --features sd-gen1-multiblock -- -D warnings
  both passed
```

feature testには、CMD18/CMD12 read、CMD23/CMD25 write、範囲外、誤token、CS abort、
single-block readbackが含まれる。既定featureの85件も再実行し、従来経路に退行がないことを確認した。

## 4. P2の境界とP3への持越し

P2で確認したのはboard-level state machineのsynthetic contractである。まだ次は行っていない。

- runner reportへの`protocol_errors`／unknown command判定の接続
- streaming SD trace replayとdigestの正式record
- U6、M-NESCO、FAT16/FAT32のproduction runner回帰
- `capability.json`の汎用SD対応への昇格
- 実アプリの一次traceに基づくbyte timingの置換・確認

したがって、CMD18/CMD25/CMD12/CMD23は「feature付きboard unit testで試作済み」だが、
「通常runtimeや汎用SD互換として対応済み」ではない。P3でtrace／mutation／report統合を閉じるまで、
既存の未対応範囲とcapability表示を維持する。
