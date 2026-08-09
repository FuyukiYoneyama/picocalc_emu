# NEXT-1 PicoEdit blind app契約

## 1. 目的

PicoEditは、既存のPicoTetris回帰へ合わせてエミュレーターを調整するのではなく、先に固定した
新しい実用workloadを、現在promotedされているbackendで初めて動かすblind appである。
対象はFAT32上のASCIIテキストを閲覧・編集・検索・安全保存する単一coreアプリとする。

この文書と[`picoedit-contract-v1.json`](../blind-validation/picoedit-contract-v1.json)を、アプリ実装、
firmware target登録、backend変更より先に固定する。後から期待値を実装結果へ合わせて変更しない。

## 2. Blind規則

1. アプリはCanonical BSPの公開API、C++17標準ライブラリ、`stdio`、`sleep_ms`だけを使用する。
2. `ff.h`、`picocalc/host.h`、emulator内部型、structured report、scenario実装、`PICOEM_*`や
   emulator専用compile definitionをアプリへ含めない。
3. hardware-free editor coreはPico SDKとBSPをincludeしない。
4. 最初のfirmware runまではbackend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`を変更しない。
5. 最初のfirmware runは成功・失敗を問わず保存する。失敗した観測を削除して再実行だけを残さない。
6. emulator合格後のBINと実機へ渡すUF2は同一buildから生成し、その間にapp/BSPを変更しない。
7. `emulator PASS -> hardware FAIL`はfalse acceptとして記録し、NEXT-3 negative conformanceへ渡す。
8. 実機結果を見て修正する場合は、元artifactと失敗記録を保持し、新revisionとして扱う。

## 3. 固定機能範囲

- 320×320 RGB565のファイル一覧・editor・検索欄・status bar
- FAT32 root directoryの列挙と`INPUT.TXT`の選択
- LF改行のASCIIファイル、最大64 KiB
- cursor上下左右、行頭・行末、insert、Backspace、Delete、改行
- forward search。未発見時に文書とcursorを変更しない
- PSRAMをauthoritativeな文書storeとして使用し、SRAMだけのshadow documentを正本にしない
- `OUTPUT.TMP`へのwrite/sync後、`OUTPUT.BAK`を使って`OUTPUT.TXT`を置換する安全保存
- 保存直後の再読込、byte数とSHA-256の照合
- 公式keyboard firmware由来のASCII、矢印、Enter、Backspace、Delete、End、Ctrlを使用

multicore、PCM audio出力、UTF-8編集、directory-backed SD、複数ファイル同時編集、undo/redo、
syntax highlightはNEXT-1 v1に含めない。

## 4. 先に確認されたBSP capability gap

基準commit `08275fd0d5a58dc26d2ef8bf21d6f0125bbe355b`の公開filesystem APIには、一般用途の
write/sync/rename/removeがない。固定payload用`smoke_test()`は存在するが、PicoEditから利用しては
ならない。アプリ生成前にCanonical BSPへ次の公開primitiveを追加し、deviceとhostで同じ
`bsp/src/filesystem.cpp`をコンパイルする。

- 明示的なcreate/truncate write open
- partial write結果
- sync
- statまたは同等の存在確認
- remove
- rename
- not-foundとwrite/sync/remove/rename失敗を区別できるError

この追加はemulator専用機能ではなく、同じBSP sourceを実機とhostが使用する。API追加後にBSP版を
更新し、そのclean commitから正規generatorで`picoedit-picocalc`を生成する。

## 5. 固定入力と期待結果

初回起動で`INPUT.TXT`が存在しない場合、アプリは次の61 bytesを作成する。

```text
PicoEdit blind validation
status: draft
alpha beta gamma
end
```

入力SHA-256は`4e666f9e499a64cd564915d71233b02818e567c72183dc12e1ce34e4f8ec2ea7`である。

固定操作は、`INPUT.TXT`を開き、`draft`を検索し、その行の末尾へ` ok`を追加して保存する。
`OUTPUT.TXT`の正規内容は次の64 bytesとする。

```text
PicoEdit blind validation
status: draft ok
alpha beta gamma
end
```

期待SHA-256は`5c704b1e8055cf77d3600eb4663c5b4ecf651c8b1085da2d0ada6e669ffc249e`である。

## 6. 検証順序

### Host

- hardware-free coreで空文書、境界cursor、insert/delete/newline、行移動、検索、64 KiB上限、
  PSRAM風chunked store、SHA-256既知vectorを検査する。
- 最低100 assertion、全件合格、同一入力のstdout byte-identicalを要求する。
- host結果はRP2040 peripheral timingの証拠として扱わない。

### 最初のfirmware blind run

- Pico SDK 2.2.0 commit `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`
- ARM GCC 13.2.1、CMake 3.28.3、Ninja 1.11.1
- FAT32、PIO0/RGB565、LCD DMA OFF、Serial、quantum 1、単一core
- promoted backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 固定scenarioで実UIを操作し、`OUTPUT.TXT` 64 bytes、期待SHA、再読込一致、key drop 0、
  exceptionなし、unsupported MMIO 0、PSRAM使用、最終画面を検査する。

初回runの前にbackend source、scenario期待値、expected SHAを変更しない。runnerが未対応のSD内容を
直接観測できない場合も、アプリの再読込SHAとSD block counterを固定し、後から都合のよいPASS条件へ
弱めない。

### 同一artifact実機相関

実機操作はタイミングを要求せず、各段階を画面で確認してから進める。

1. `INPUT.TXT`が選択された一覧でEnter。
2. Ctrl+F、`draft`、Enter。誤入力はBackspaceで修正できる。
3. End（PicoCalc物理操作はShift+Del）で行末へ移動。
4. ` ok`を入力。誤入力はBackspaceで修正できる。
5. Ctrl+S。保存完了表示が出るまで他キーを押さない。
6. 最終画面を1枚撮影し、UARTログとSD上の`OUTPUT.TXT`を保存する。

途中の押し損ねは同じキーを再入力でき、連続成功回数、途中写真、時刻同期は要求しない。

## 7. 合否

Host、最初のfirmware run、同一artifact実機runを別々に判定する。最終PASSには、同一source/buildの
BIN/UF2、期待する64 bytesとSHA、再読込一致、最終画面、UART、例外・unsupported MMIO・key dropなしが
必要である。画面が似ているだけ、UART markerだけ、実機だけ、emulatorだけでは最終PASSにしない。
