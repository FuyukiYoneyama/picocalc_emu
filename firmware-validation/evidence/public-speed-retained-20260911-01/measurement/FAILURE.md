初回系列はwarmup後の検証scriptエラーで停止した（script終了1、runner終了0）。
エラー: `target report failed: normalized report SHA-256 mismatch`。
旧commit照合用コピーでトップレベルbackend_commitを置換し忘れたことが原因。
backend_build以外を比較するとbackend_commitのみが旧R0との相違だった。
原本・実行条件・timing・当時のscriptを保持する。本測定の集計には含めない。
修正版での新規系列はmeasurement-v2を参照。
