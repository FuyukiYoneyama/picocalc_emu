# Contributing

改造・backend変更・新しいtarget追加を行う人とAIは、まず
[`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md)を読みます。そこに、リポジトリ間の責任範囲、
ローカル検証、target／evidence更新、I2C optional profileの追加手順をまとめています。

Issues and pull requests are welcome. Before opening one, please run the
smallest relevant local checks and include the command, host toolchain, and
result in the report.

The normal verification boundary is local. Do not use GitHub Actions as a
debugging loop or add workflow jobs without an explicit project decision. Keep
changes scoped, preserve the fail-closed contracts, and do not commit firmware
artifacts, probe identifiers, credentials, or private operator notes.

For cross-repository changes, update the pinned backend/target metadata and
the corresponding documentation in the same change when the contract changes.
See [`docs/PUBLIC_RELEASE.md`](docs/PUBLIC_RELEASE.md) and
[`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) before preparing a
release batch.

There is no promise of review time or merge acceptance. Fork the repository if
you need an independently maintained variant.
