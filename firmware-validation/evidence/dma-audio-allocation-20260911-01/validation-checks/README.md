# Validation repository checks

今回のdocs／evidence更新後に標準gateを実行した。

- `python3 tools/picocalc.py verify`: **85 pass / 1 fail**、exit 1。
- `python3 -m unittest discover -s tests -p 'test_*.py'`: **242 tests / 239 pass / 3 failures**、exit 1。
- 通常文書・Python・JSON・SHA256SUMSのstaged whitespace checkを実行し合格した。
  再適用用patch、UART raw、採取logはbyte-preserving evidenceとして通常の整形対象から除外。

failは`release:no-conformance-target`が既存recovery evidence内の13個の`.bin`を列挙することに起因する。
内訳はUART採取データ12個とG5-Aの`raw/flash-output.bin`。今回のevidenceへfirmware BINは追加していない。

未変更commit `c7e79757a3ae10f5f86dfa00e392fddfb3043a18`のdetached worktreeを作成し、
次の3 testを対照実行して同じfailureを確認した。

1. `test_ci_scopes_separate_core_from_target_schema`
2. `test_hardware_record_accepts_complete_evidence`
3. `test_portable_verification_and_json_schema`

さらに未変更の`verify_release_conditions`へ旧rootと今回rootを渡し、検出する13 pathが一致することを
assertした。`tools/verify_environment.py`と`tests/test_tools.py`にも今回の変更はない。
これは既存validatorと凍結evidenceの配置・拡張子の不整合であり、今回の性能修正の回帰ではない。
ただし、全体gateがgreenであると報告したり、過去のevidenceを削除して通過させたりはしない。
この修正は今回の単一候補検証へ追加せず、別scopeとして保留する。

実行ログはこのdirectoryの`verify.log`、`unit-tests.log`、`baseline-core-test.log`、
`baseline-portable-tests.log`、`release-layout-comparison.log`に保存する。
test用fixtureが意図的に出すREFUSEDやcontract mismatchは、それ自体では追加failureではない。

保存後の追加auditでは、6 reportのcommit／dirty=false、cycles／elapsed、verdict、
host timingとmanifestのCPU値、strict projection、集計の停止判断を再照合して合格した。
projection関数がstep quantum、PSRAM tick count、audio expectationを保持することも確認した。
