# R2 Template B再現手順

この文書は、`reference-projects/firmware-targets.json`の
`picocalc-template-b`に固定したR2時点のBIN/UF2を、別の作業者が同じSHA-256で
再生成するための正規手順です。現行generatorで新しい成果物を作る手順ではなく、
generator commit `82e943ab1942ef869e9bff38ae6fcf8074930361`の履歴再現です。

期待値は次のとおりです。

| 成果物 | SHA-256 |
|---|---|
| `picocalc_app.bin` | `1e6abac252c28a349d172254c0bc08976786023597a1c44002bfcb1bfbd02a3d` |
| `picocalc_app.uf2` | `1ab0d16f4f05207934f6d63b77d2ae5437231ee3762381b82505a3d4acefc757` |

## 由来を決める二つのGit境界

この成果物には二つの異なるsource identityが入ります。両者を混同してはいけません。

- `bsp_git=82e943ab1942`: `picocalc.py`を実行するsourceが、上記commitをcheckoutした
  **本物のclean Git clone**であることを表す。sourceから`.git`を削除したコピーは使わない。
- `app_git=untracked`: `picocalc.py new`の生成先が、source cloneを含む**どのGit working
  treeの内側にもない**ことを表す。生成先をsource cloneの子に置かない。

`project_commit()`はR2時点では親directoryのGit repositoryまで探索します。このため、生成物に
`.git`がなくてもsource cloneの内側へ生成すると`app_git=82e943ab1942`となり、別のBINになります。
反対にsourceの`.git`を削除すると`bsp_git`まで`untracked`となり、やはり別のBINになります。

## 固定環境

R2受入時と再確認時に一致した環境は次のとおりです。

| 項目 | 固定値 |
|---|---|
| OS | Ubuntu 24.04 / WSL |
| Pico SDK | tag `2.2.0`, commit `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` |
| ARM GCC/G++ | `13.2.1 20231009` |
| CMake | `3.28.3` |
| generator | `Unix Makefiles` |
| GNU Make | `4.3` |
| picotool | `v2.2.0-a4`, CMake directory `/usr/local/lib/cmake/picotool` |
| Python | `3.12.3` |
| build timestamp | `2026-08-06T00:00:00Z` |
| parallel jobs | `2` |

Pythonのpatch版等が成果物へ影響するという主張ではありません。誰が再検証しても同じ入力を
選べるよう、実際に一致した環境を省略せず記録しています。

SDKを新しく取得する場合はtag名だけに依存せず、checkout後のcommitも検査します。

```sh
git clone --branch 2.2.0 --recurse-submodules \
  https://github.com/raspberrypi/pico-sdk.git /absolute/path/to/pico-sdk-2.2.0
git -C /absolute/path/to/pico-sdk-2.2.0 checkout --detach \
  a1438dff1d38bd9c65dbd693f0e5db4b9ae91779
git -C /absolute/path/to/pico-sdk-2.2.0 submodule update --init --recursive
```

## 正規コマンド

`PICOCALC_R2_ROOT`自身がGit working tree内にないことを先に確認します。source cloneと
生成先は兄弟directoryにします。

```sh
PICOCALC_R2_ROOT="$(mktemp -d /tmp/picocalc-r2-repro.XXXXXX)"
PICOCALC_SDK_DIR=/absolute/path/to/pico-sdk-2.2.0

test "$(python3 --version)" = "Python 3.12.3"
test "$(cmake --version | sed -n '1s/^cmake version //p')" = "3.28.3"
test "$(make --version | sed -n '1s/^GNU Make //p')" = "4.3"
test "$(arm-none-eabi-gcc -dumpfullversion)" = "13.2.1"
test "$(picotool version | sed -n 's/^picotool \(v[^ ]*\).*/\1/p')" = "v2.2.0-a4"
test -f /usr/local/lib/cmake/picotool/picotoolConfig.cmake

if git -C "$PICOCALC_R2_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "reproduction root must be outside every Git working tree" >&2
  exit 1
fi

git clone https://github.com/FuyukiYoneyama/picocalc_emu.git \
  "$PICOCALC_R2_ROOT/source"
git -C "$PICOCALC_R2_ROOT/source" checkout --detach \
  82e943ab1942ef869e9bff38ae6fcf8074930361

test "$(git -C "$PICOCALC_R2_ROOT/source" rev-parse HEAD)" = \
  82e943ab1942ef869e9bff38ae6fcf8074930361
test -z "$(git -C "$PICOCALC_R2_ROOT/source" status --porcelain)"
test "$(git -C "$PICOCALC_SDK_DIR" rev-parse HEAD)" = \
  a1438dff1d38bd9c65dbd693f0e5db4b9ae91779
test -z "$(git -C "$PICOCALC_SDK_DIR" status --porcelain)"

unset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
unset CMAKE_GENERATOR PICO_SDK_PATH PICOTOOL_DIR

python3 "$PICOCALC_R2_ROOT/source/tools/picocalc.py" new R2Template \
  --output "$PICOCALC_R2_ROOT/run"

if git -C "$PICOCALC_R2_ROOT/run" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "generated project must be outside every Git working tree" >&2
  exit 1
fi

python3 "$PICOCALC_R2_ROOT/source/tools/picocalc.py" build \
  --project "$PICOCALC_R2_ROOT/run" \
  --sdk "$PICOCALC_SDK_DIR" \
  --picotool-dir /usr/local/lib/cmake/picotool \
  --lcd-variant pio-rgb565 \
  --jobs 2 \
  --build-timestamp 2026-08-06T00:00:00Z
```

GitHub repositoryがprivateの場合は、認証済みの同じURL、または手元のclean cloneを元にした
`git clone --no-local <source> "$PICOCALC_R2_ROOT/source"`を使えます。directory copyや
`.git`削除は代替になりません。

R2時点の`picocalc.py`には`--generator`オプションがありません。Ubuntu上の既定である
`Unix Makefiles`を使用します。`CMAKE_GENERATOR=Ninja`を設定したり、現行toolの
`--generator Ninja`を混ぜたりしません。

## 合否確認

```sh
test "$(sed -n 's/^CMAKE_GENERATOR:INTERNAL=//p' \
  "$PICOCALC_R2_ROOT/run/build/CMakeCache.txt")" = "Unix Makefiles"

strings "$PICOCALC_R2_ROOT/run/build/picocalc_app.bin" | grep -Fx 82e943ab1942
strings "$PICOCALC_R2_ROOT/run/build/picocalc_app.bin" | grep -Fx untracked

printf '%s  %s\n' \
  1e6abac252c28a349d172254c0bc08976786023597a1c44002bfcb1bfbd02a3d \
  "$PICOCALC_R2_ROOT/run/build/picocalc_app.bin" | sha256sum --check
printf '%s  %s\n' \
  1ab0d16f4f05207934f6d63b77d2ae5437231ee3762381b82505a3d4acefc757 \
  "$PICOCALC_R2_ROOT/run/build/picocalc_app.uf2" | sha256sum --check
```

BINとUF2が両方一致した場合だけ再現成功です。ELFは絶対build pathを保持するため、異なる
生成先間での一致をR2契約は要求しません。

## 一致しない場合の確認順

1. sourceが`.git`を保持したclean cloneで、HEADが`82e943a...`か確認する。
2. 生成先がsource cloneや別repositoryの内側にないことを`git rev-parse`で確認する。
3. BIN内に`82e943ab1942`と`untracked`の両方が独立した文字列として存在するか確認する。
4. Pico SDKのtag名だけでなくcommitが`a1438dff...`か確認する。
5. `CMakeCache.txt`が`Unix Makefiles`と上記picotool directoryを記録しているか確認する。
6. 外部`CFLAGS`等を消し、固定timestampでbuild directoryを新規作成する。

履歴証拠`firmware-validation/records/r2-20260806-01/report.json`は時点記録なので
書き換えません。現行generatorの親Git継承を将来修正しても、このR2成果物の再現には
固定commitのtoolと本書の境界条件を使用します。
