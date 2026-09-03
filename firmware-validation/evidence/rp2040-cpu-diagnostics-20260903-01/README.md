# RP2040 CPU 補助診断アーカイブ

このディレクトリは、RP2040 CPU高速化計測で生成した補助診断データを、元の一時領域からGit管理下へ保存したものである。候補の採否recordや新しい候補ブランチではない。

保存したデータ:

- `cpu-time-diagnostic-p1-a-20260902-01.json`: P1-A再測定前のbaseline-only CPU時間帰属診断。warm-up 1回、測定4回、CPU 11、60秒cooldown。候補効果の採否には使わない。
- `host-stability-cpu-v3-20260902-01.json`: CPU 11で実施したhost-stability sentinel v3。P2-A production A/Bの補助的なhost provenanceであり、候補効果そのものではない。

元ファイルは `/tmp/picocalc-rp2040-cpu-opt.PoEwYE/diagnostics/` にあり、`manifest.json`に元パス、record ID、関連するimmutable record、SHA-256を記録している。`SHA256SUMS`はこのディレクトリ内の全ファイルを対象とする。

既存のP1-A/P2-A A/B recordは変更していない。これらの診断値を候補効果へ再解釈したり、A/B recordへ追記したりしてはならない。
