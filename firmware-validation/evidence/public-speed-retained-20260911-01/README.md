# 公開版Tetris速度の再測定（生データ保全）2026-09-11

公開backend `32d27ff4179a993ae9fac6ff4a1d5e8999570fa9`を無変更・clean release buildして直接測定。
本測定3回の実時間比中央値は **15.1482949826%**、経過時間中央値は **24.524212159秒**。
固定Tetrisのこの環境での値であり、全アプリの速度や新しい高速化の達成を意味しない。

| 回 | プロセス全体の経過秒 | 実時間比% |
| --- | ---: | ---: |
| 1 | 24.467043156 | 15.1836900614 |
| 2 | 24.524212159 | 15.1482949826 |
| 3 | 24.582967075 | 15.1120895564 |

warmup 1回を除外。全回仮想時間3.715秒、927528660 cycles、scenario_done、verdict pass。
レポート全体のhashは3回一致。UART・画面・85-step scenario・旧登録の正確性契約を照合済み。
raw reportには実際の公開commitとdirty=falseを保持している。
旧commitのnormalized report照合時だけ、コピーの二つのcommit欄を旧値に置換する。

## 証拠

- `measurement-v2/summary.json`: 集計と各測定値。
- `measurement-v2/manifest.json`: 対象・hash・環境・計測方法。
- `measurement-v2/{warmup,run-001,run-002,run-003}/`: 各回のargv、raw report、timing、UART、PNG、標準出力／エラー、検証結果。
- `binaries/`: 使用runnerおよび固定firmware BINの実体。
- `REPRODUCE.md`と`measure.py`: buildと再実行手順。既存出力は上書きしない。
- buildログ・Cargo.lock・feature tree・toolchain情報・firmware build history。
- `measurement/`: 初回warmupの照合script不備で停止した記録。削除せず、正式集計から除外。
- `SHA256SUMS`: 本ファイル以外も含めた全ファイル（checksum一覧自身を除く）の検証用hash。

## 解釈と前回の訂正

今回は以前の会話で削除した測定ファイルの復元ではなく、新規実測である。
前回の14.914631%は同一treeの旧commitを測った値だったが、今回は公開commitを直接測った。
旧高速地点e985a9dと公開commitのtreeは33b60b9f7d3721fca074ece8ec69737239bc943cで一致。
約14%の旧速度帯にあることを支持するが、過去の6倍等の時間差の原因や、1倍速達成を証明しない。
前回との差をコード改善とは扱わない。同一ソースでも実行環境・build・測定条件により値は変動する。
補助のprocess CPU時間がwall時間を上回っているため、CPU時間を速度%の分母に混ぜない。
ここでの速度は既存手順どおり外部wall時計のみから計算した。

実測の目的は、第三者が条件と原本を確認できる形で判断根拠を残すこと。
今回の生データは検証リポジトリのGit管理対象として保全し、build用の一時領域とは別に保持する。
