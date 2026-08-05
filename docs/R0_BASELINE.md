# R0 基準点・生成契約・provenance

R0は2026-08-05に完了した。目的は、以後のbackend hardeningやPicoTetris回帰を、
「どのソースと契約に対する変更か」が再現できる状態から始めることである。
機械可読な正典は`provenance/r0-baseline.json`とする。

## 固定したもの

開始点はR0編集直前の各`main`、固定点はR0で契約または復元状態を確定したcommitである。

| repository | 開始点 | R0固定点 |
|---|---|---|
| `picocalc_emu` | `b6efb2e956b46432423fc1f3eaab111188e4c7db` | `1330a15183f986e34d0c7b415a72618e079ebf0b` |
| `picoem-picocalc` | `6a618010dc8b8217b6035951b361dc859f472301` | `07ce135b7bc4646eb3df8f52dd193ba66347570b` |
| `picotetris` | `396ed5cb415d95289475032754a4931d915bb3a6` | `0a2735a4dc1c4aaf892fbf2364b7076535ef94e2` |

この文書とmanifestを収録するcommit自身をmanifestへ書くことはできないため、
`picocalc_emu`固定点は生成・検証契約を導入した直前commitに固定する。後続の記録commitは
その契約を変更せず、固定値、bundle、完了状態を収録する。

合否契約はproject metadata schema 2、firmware report schema 6、host report schema 1、
scenario schema 1、firmware target registry schema 1、capability schema 1で固定した。
runner終了コードは0=pass、1=判定済みfailure、2=判定不能である。R1で解消する既知gapも
manifestに残し、R0完了をverdict hardening完了とは扱わない。

## 新規生成プロジェクト

`tools/picocalc.py new`は次を`.picocalc-project.json` schema 2へ書く。

- project name、target、template
- `bsp/VERSION`から読んだBSP版
- generator repository、source commit、作業ツリーdirty状態
- BSP source commit、BSPだけのdirty状態、コピーしたBSP全fileのdirectory SHA-256
- build targetとtemplate smoke marker

生成先には`LICENSE`と、生成先だけで参照が完結する`THIRD_PARTY_NOTICES.md`も含める。
directory SHA-256は相対path昇順で、path長・path bytes・content長・content bytesをSHA-256へ
順に投入する。生成元がdirtyならその事実を隠さない。配布用固定点ではclean sourceを使う。

## PicoTetrisの履歴復元

元のschema 1 metadataはリポジトリ外の旧生成先に残っていたが、生成commitは記録されて
いなかった。そのため元commitを推測せず、`kind: reconstructed`として復元した。
PicoTetrisの`bsp/`全体は`picocalc_emu` commit
`cbfc90467e2b8392fbd0429c83925b94ca365824:bsp`と完全一致する。

- Git tree: `9c29d5261cbcfe51f6b34c14054497443180a31b`
- directory SHA-256: `8198311924ff6d30867bcadfa81b46fd7fa9cb8857499a49f49f496e97545e7d`

現行canonical BSPには後からhost層が加わっているため、現行全treeのhashをPicoTetrisへ
流用しない。device subtreeが現行と一致することと、全treeの歴史的source identityを
区別する。

R0完了時点のPicoTetrisには意図的にremoteを設けなかった。代わりに完全履歴を含む
`provenance/picotetris-r0.bundle`を保存し、SHA-256をmanifestに固定した。R4準備で
2026-08-06にprivate GitHub repositoryを追加した後も、R0の時点証拠であるmanifestの
`remote: null`とbundleは書き換えない。R0状態の再取得は次で行う。

```sh
git clone -b main provenance/picotetris-r0.bundle /tmp/picotetris-r0
git -C /tmp/picotetris-r0 rev-parse HEAD
```

期待HEADは`0a2735a4dc1c4aaf892fbf2364b7076535ef94e2`である。

## 検証

通常のportable検査には生成契約検査が常に含まれる。3リポジトリとbundleを含むR0全体は
workspace rootを指定して検査する。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py verify --r0 --workspace-root ..
python3 -m unittest discover -s tests -p 'test_*.py'
```

これにより、開始点・schema、固定commit object、PicoTetris metadata/BSP実体、license、
notices、bundle SHA-256を検査する。
