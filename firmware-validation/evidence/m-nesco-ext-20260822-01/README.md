# M-NESCO 拡張受入証拠

判定: **PASS（ローカル検証）**

この証拠は、M-NESCO拡張受入契約の3ケースを同一の診断BIN・同一clean backendで実行した結果です。GitHub Actionsは使用していません。各caseの詳細な反復値は、同じディレクトリの`mnesco-*/case.json`と`runner-manifest.json`に保存しています。

## 受入範囲

- mapper 0／小容量（RAM path）: Run Aを3回、決定的に一致。XIPは適用外。
- mapper 2／中容量（XIP staging）: Run A×3、A export再attachのRun B×3、flash SHA一致。
- mapper 1／大容量（XIP staging）: Run A×3、A export再attachのRun B×3、flash SHA一致。
- mapper 4／PRG+CHR大容量（XIP staging）: Run A×3、A export再attachのRun B×3、PRG／CHR境界sampleとflash SHA一致。
- mapper 30／大容量（XIP staging）: Run A×3、A export再attachのRun B×3、flash SHA一致。

追加のmapper 1大容量case（`mnesco-m1-large/`）も同じゲートで合格しており、計画4caseに加えた回帰カバレッジとして保存しています。
- すべてのcaseで、SD FAT32 image、ROM file SHA、ROM metadata、PRG／CHR境界sample、CPU fetch/data、PPU観測、UART/report、unknown command/errorのゲートを適用。
- XIP caseではcore 1 probeとDMA XIP probeを実行し、A/Bのdigest一致を確認。

## provenance

- NESco source: commit `7f3fa05971930e03653694117cbf6a435ec1dd4e`, clean。
- 診断BIN: `Picocalc_NESco.bin`, SHA-256 `4e601a45176ca99b0e65193a6aa2c4ee8d968177a316df95ac47526325800824`。
- backend: `picoem-picocalc` commit `d1360cbb13fd807661474b49a1b5516b12567d00`, clean。
- runner: `picocalc-run` SHA-256 `4745c256f215469c2ad554556936663261a3b3cffd67ef6622125d7712e85720`。
- host acceptance tool: `tools/mnesco_ext.py` SHA-256 `e27a4516832bfcd534c0a151c4c162871336e86b7f8eb5063ea359f4481497fe`。

source ROM、RAW image、flash実体、UART生ファイルはGitへ保存していません。記録にはbasename、header metadata、SHA-256、反復のsanitized summaryだけを残しています。入力ROMは呼び出し側がread-onlyで供給し、manifestにはローカル絶対pathを記録しません。

## clean sourceの確認

実行に使用したBINは、NESco診断変更をcommitした後にclean sourceから再buildしました。commit前の実行BINと再build後BINのSHA-256は同一であり、既存のA/B実行結果へclean provenanceを結び付けられます。A/B cross-phase（ROM identity、境界sample、観測digest、flash SHA）の検証は、最終版host toolで全XIP caseへ再適用済みです。

このgateのPASSは、記録した3ケースのSD／flash／XIP debug経路を意味します。NEScoの全mapper互換性、任意ROM、USB BOOTSEL/MSC、`uf2loader supported`への昇格は宣言しません。
