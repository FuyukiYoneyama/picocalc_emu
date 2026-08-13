# 最短手順：生成から最初の検証まで

コマンドは`picocalc_emu`のrootで実行します。

## 1. checkout

```sh
git clone https://github.com/FuyukiYoneyama/picocalc_emu.git
cd picocalc_emu
python3 tools/picocalc.py verify
```

安定版を使う場合は公開済みのrelease tagまたは指定commitをcheckoutします。`main`は開発中の先端です。

## 2. アプリを生成

```sh
python3 tools/picocalc.py new MyApp --output ../MyApp
```

通常変更する場所は次だけです。

```text
../MyApp/app/
../MyApp/assets/   # 必要な場合だけ
```

`../MyApp/bsp/`、`../MyApp/generated/`、board設定、LCD／SD／keyboard／PSRAMの初期化を
アプリ側へコピーして書き直さないでください。BSPの公開APIを使います。
公開APIの入口は[`README.md`](README.md)の最小API表です。関数の詳細が必要な場合だけ、そこから
対象headerまたはBSP READMEへ進みます。

## 3. RP2040向けにビルド

```sh
export PICO_SDK_PATH=/absolute/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
python3 tools/picocalc.py verify-project --project ../MyApp
```

標準出力先は次です。

```text
../MyApp/build/picocalc_app.bin
../MyApp/build/picocalc_app.uf2
```

通常はLCD variantを指定しません（`pio-rgb565`）。互換・診断用のSPI1経路が必要な場合だけ
`--lcd-variant hwspi-rgb888`を使います。

## 4. 最初の確認

まずhost backendを実行します。

```sh
python3 tools/picocalc.py test --mode host
```

hostは高速ですが、PIO、DMA、I2C transaction、interrupt、multicore、LCD wire形式の判定は
しません。そこまで確認するときは[`TESTING.md`](TESTING.md)のfirmware手順へ進みます。

## 5. 実機へ渡すとき

同一artifactのBIN／UF2 SHA-256とbuild条件を記録し、通常はPicoCalcの`uf2loader`でUF2を転送します。
BOOTSELは、flash書込み経路そのものを検証する明示的な目的がある場合だけ使います。
色、見え方、キーの物理感触、実際の聞こえ方はエミュレーターだけでは判定できません。

## 終了コード

- `0`: pass
- `1`: 実行でき、判定した結果のfailure
- `2`: `cannot judge`（backend、artifact、schemaなど不足）
