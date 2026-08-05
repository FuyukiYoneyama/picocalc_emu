# Host backend（Milestone 2）

## これは何か

BSPの公開APIを**RP2040ではなくホストのモデルに対して**ビルドする。アプリのロジックを
RP2040バイナリを作らずに、ネイティブで直接検査できる。

```sh
python3 tools/picocalc.py test --mode host
```

これは[`DOGFOODING_20260805.md`](DOGFOODING_20260805.md)の穴3に必要な基盤である。
ライン消去や衝突判定は純粋な関数なのに、試すにはRP2040イメージを作って
エミュレーターで走らせるしかなかった。Host backendはその試験面を提供するが、
PicoTetris自身の関数分離とunit test接続は別作業であり、`MILESTONES.md`のR3で行う。

## 2つのbackendの役割

| | firmware backend | host backend |
|---|---|---|
| 実行するもの | 実際のRP2040バイナリ | アプリのソースをネイティブビルド |
| 所要 | 数十秒〜数分 | 1秒未満 |
| 答えられる問い | ハードウェアの挙動 | アプリのロジック |
| 答えられない問い | — | ハードウェアの挙動すべて |

**firmware backendが権威である。** hostにはPIOもDMAもI2Cトランザクションも割り込みも
ない。display書き込みは即座に配列へ入る。タイミングやペリフェラルのワイヤプロトコルに
依存する正しさは、hostには**問いとして存在しない**ので、答えも出せない。

その代わり速い。そして次の性質がある。

## framebuffer digestが両backendで一致する

hostの`framebuffer_sha256()`は、firmware backendとまったく同じ正規形
（row-major、リトルエンディアンのRGB565生バイト列のSHA-256）を返す。

つまり**同じ絵を描いたアプリは、両方で同じ64文字を出す**。`picocalc-run`のレポートの
`framebuffer.rgb565_sha256`と直接比較できる。安いhost実行が高いfirmware実行の
代わりを務めてよい根拠は、この比較で得る。

PNGをhash対象にしていたら、エンコーダ設定が変わるたびに絵が変わっていなくても
一致しなくなる。だから生バイト列を正規形にしている。

## 実装の要点：共有しているソース

`src/filesystem.cpp`と`src/fatfs_diskio.cpp`は**Pico SDKに一切依存していない**
（`picocalc::sdcard`とChanFatFSとしか話さない）。したがってhostビルドは
**デバイスとまったく同じファイルをコンパイルする**。差し替えるのは下のブロック
デバイスだけである。

hostのファイルシステム試験は、代用品ではなく**出荷するコード**を動かしている。

SDカードは**フォーマット済みで始まる**。BSPはmountするだけでformatせず、この
ビルドもformatできない（ChanFatFSが`FF_USE_MKFS 0`で構成されており、その構成は
実機検証済みのデバイスビルドの一部なので、hostの都合で変えない）。そこで
購入時付属32 GBカードに合わせたFAT32レイアウトを既定で直接書き込む。
`format_sd(SdFormat::Fat16)`でFAT16も明示選択できる。`sd_formats_test`は両形式に対して
共有Chan FatFsのmount/write/sync/read/compare/removeを実行する。

## モデル化しているもの / していないもの

| API | host |
|---|---|
| `display` | 320×320のframebuffer。window/write_pixelsの意味論は同じ（書き込みポインタのラップを含む） |
| `keyboard` | 上限31イベントのFIFO。溢れは数える |
| `psram` | 8 MiBのホストメモリ。境界検査あり。`info().id`は実機が返した値 |
| `filesystem` | **デバイスと同じソース**。ブロックデバイスだけホストメモリ |
| `sdcard` | セクタ配列。SPIのbring-upはない |
| `audio` | サンプル数の集計のみ。出力デバイスなし |
| Pico SDK | `stdio_init_all`と`sleep_ms`だけ |

**キーボードの31イベント上限はホスト都合ではない。** 公式STM32 firmware自身が
`FIFO_SIZE 31`、status mask `0x1f`と定義し、BSPは`key_info[0] & 0x1f`として読む。
32件保持したコントローラは
自分を空だと報告して二度と読まれなくなる。firmware backendはこの欠陥に実際にぶつかった
（滞留224件でドライバが恒久停止）。hostで上限に当たったテストは、ホスト固有の
現象ではなく**実機の制約を再現している**。

**`audio`の`underrun_count`は常に0である。** これは「underrunしない」という主張では
なく、**主張の不在**である。hostにはサンプルを定期消費するものがないので、何も
測っていない。この0を根拠として読むのは誤りである。

Pico SDKのshimを意図的に狭くしてあるのも同じ理由による。モデル化していない部分を
使うコードは**コンパイルエラーになる**。それが正しい答えで、広いshimは「hostで
動いた」という誤った安心を与える。

## 時間

`sleep_ms`は待たない。仮想クロックを進めるだけである。壁時計は一切読まない。
PicoTetrisは16 ms周期でポーリングするので、実際に待っていたらテストにプレイと
同じ時間がかかる。

`picocalc::host::now_us()`が現在の仮想時刻を返す。

## テストから使う

アプリは`picocalc/host.h`をincludeしない。これは**テストが握るハンドル**であり、
デバイスには存在しない。アプリがこれに手を伸ばすとRP2040向けビルドが失敗する
——それが意図した答えである。

```cpp
#include "picocalc/bsp.h"
#include "picocalc/host.h"

picocalc::host::reset_all();
picocalc::init();

picocalc::host::queue_keys("aaw ");        // キーを積む
run_one_frame_of_my_app();                 // アプリを1フレーム進める
assert(picocalc::host::pixel(42, 300) == 0xF81F);
assert(picocalc::host::framebuffer_sha256() == expected);
```

`reset_all()`をテストの間に呼ぶ。呼ばないと前のテストの残骸を引き継ぎ、
テストの実行順序が結果を左右しはじめる。

## `emu_smoke`

Milestone 2の完了条件——「専用アプリがPC上で起動し、画面・キー・ファイル結果を
決定的に生成できる」——そのものである。`bsp/host/tests/emu_smoke.cpp`にあり、
25個の明示的`check()`と、その前提となる`picocalc::init()`成功を検査して1行ずつ
結果を出す。テストフレームワークに依存しないので
CIからそのまま使える。

初回evidence recordの`checks=26`は25個の明示的checkに初期化前提を加えた数として読む。
時点証拠は改変せず、現在の文書では内訳を明示する。

決定性は**外から**確認する。`picocalc.py test --mode host`が3回実行して出力を
バイト比較する。中身が壁時計・乱数・アドレスを読まないことが前提であり、
読んでいれば比較が落ちる。

```
host backend: 3 run(s), byte-identical, output sha256 3a4c400f3034da4e
```

## まだできないこと

- **directory-backed Fast SDモード**（Milestone 2の項目）は未実装。カードは
  ホストメモリ上のセクタ配列であり、ホストのディレクトリを見せる経路はない
- multicore、割り込み、DMA、PIOは存在しない。これらに依存する挙動はfirmware
  backendでしか見えない
- LCDのwire形式（A/B系統の違い）はhostに存在しない。`verify_pixels`は
  常に`transport_ok=true`を返す
- scenario runnerはfirmware backend専用である。hostのテストはC++で書く
