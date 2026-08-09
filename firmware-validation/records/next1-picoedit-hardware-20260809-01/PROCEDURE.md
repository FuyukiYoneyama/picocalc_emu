# PicoEdit NEXT-1 実機相関手順

## 使用するUF2

このファイルだけを使用する。

```text
/home/fuyuki/pico_dvl/codex/picoedit-picocalc/build/picocalc_app.uf2
```

実行前に確認する。

```sh
sha256sum /home/fuyuki/pico_dvl/codex/picoedit-picocalc/build/picocalc_app.uf2
```

正しい値は次である。

```text
730281ef0070a5cf00610471fec9033a2f53aabebf24f52c3b6f0e520f5c6b73
```

これはエミュレーター合格BINと同じbuildから作ったUF2である。アプリを再buildした別UF2へ
置き換えない。

## 事前準備

1. SDカードの既存内容を必要ならバックアップする。
2. FAT32のカードを使う。標準32 GBカードはFAT32のままでよく、再formatは不要である。
3. rootにある`INPUT.TXT`、`OUTPUT.TXT`、`OUTPUT.TMP`、`OUTPUT.BAK`だけを削除する。
   他のファイルは削除しない。既存データを消したくない場合は専用のFAT32カードを使う。
4. 電源OFFでSDカードをPicoCalcへ戻す。
5. 既知のPicoCalc UF2書込み手順でBOOTSEL mass-storage modeへ入り、上記UF2をコピーする。
6. UART/USB CDCログを、起動前から保存する。UARTを使う場合は115200 8N1である。保存先は
   `next1-picoedit-hardware-20260809-01/uart.log`とする。

## 人間が行う操作

タイミング合わせ、途中写真、長い連続キー列は不要である。各画面を確認してから次へ進む。

1. 一覧画面に`INPUT.TXT`が選択表示されるまで待ち、`Enter`を1回押す。
2. editorに61 bytesの文書が表示されたら、`Ctrl+F`を押す。
3. 検索欄へ`draft`と入力し、入力内容を目で確認して`Enter`を押す。
4. statusが`FOUND - End moves to line end`になったことを確認する。
5. `Shift`を押しながら`Del`を1回押す。これがPicoCalc公式keyboard firmwareの`End`である。
6. 半角space、`o`、`k`の順に入力する。2行目が`status: draft ok`になったことを確認する。
7. `Ctrl+S`を1回押し、他のキーには触れず、statusが
   `SAVED - 64 bytes SHA PASS`になるまで待つ。
8. その最終画面を写真1枚に撮る。
9. UARTログを保存してからPicoCalcの電源を切る。
10. SDカードの`OUTPUT.TXT`をこの証拠directoryへコピーし、次を実行する。

```sh
wc -c OUTPUT.TXT
sha256sum OUTPUT.TXT
```

合格値は64 bytesと次のSHA-256である。

```text
5c704b1e8055cf77d3600eb4663c5b4ecf651c8b1085da2d0ada6e669ffc249e
```

## 誤入力・反応しない場合の復旧

- 検索欄で間違えた場合は`Backspace`で直してから`Enter`を押す。
- `NOT FOUND`になった場合は`Ctrl+F`から`draft`を入力し直す。
- ` ok`を間違え、まだ`Ctrl+S`を押していない場合は`Backspace`または矢印で直せる。
- キーが反応したか不明、cursor位置が分からない、または編集内容に自信がない場合は、
  **保存せず電源を切って最初からやり直す**。文書正本はPSRAMなので未保存編集は再起動で消え、
  `INPUT.TXT`は変化しない。
- `Ctrl+S`後に`SAVE FAILED`となった場合は、その画面とUARTを保存する。電源を切り、SDカードの
  `OUTPUT.TXT`、`OUTPUT.TMP`、`OUTPUT.BAK`を退避してから、新しい試行としてやり直す。失敗証拠を
  成功試行で上書きしない。
- キーを連打しない。反応が見えない場合は同じキーを直ちに重ねず、画面またはUARTの変化を待つ。

## 提出する4点

1. `uart.log`
2. 最終画面写真1枚
3. `OUTPUT.TXT`
4. `wc -c`と`sha256sum`の結果

`emulator PASS -> hardware FAIL`の場合も結果を破棄せず、そのままfalse accept候補として記録する。
