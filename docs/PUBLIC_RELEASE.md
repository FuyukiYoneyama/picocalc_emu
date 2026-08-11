# Public release procedure

This document is the final release procedure for the two public repositories:

- `FuyukiYoneyama/picocalc_emu`
- `FuyukiYoneyama/picoem-picocalc`

The repositories are intentionally independent. `picocalc_emu` contains the
canonical BSP, host runner, target registry, reports, and documentation.
`picoem-picocalc` contains the RP2040 firmware backend. A normal new-project,
host-backend, portable-verification, or direct-runner workflow does not require
`picocalc_emu_ext`; that workspace is only an optional source input for
rebuilding historical external applications and hardware records.

The public versioning policy is defined in
[`VERSIONING.md`](VERSIONING.md). In short, `main` is the development head,
while users select a GitHub Release backed by an immutable SemVer tag. The
first public technical-preview pair is intended to be `v0.1.0`; creating that
tag is a separate release action and is not implied by ordinary commits or
pushes.

Each paired release records both repository tags and full commit SHAs, the BSP
version, report and machine-API schemas, the registry-pinned backend commit,
toolchain requirements, and known limitations. The tag is the user-facing
entry point; the full SHA is the reproducibility anchor.

## Local gate

Run these commands before pushing a release batch. They do not invoke GitHub
Actions:

```sh
cd picocalc_emu
python3 tools/picocalc.py verify
python3 -m unittest tests.test_tools

cd ../picoem-picocalc
cargo test --locked -p picocalc-board -p picocalc-harness -p rp2040-emu
cargo build --locked --release -p picocalc-harness
cargo fmt -p picocalc-board -p picocalc-harness --check
cargo clippy --locked -p picocalc-board -p picocalc-harness --all-targets -- -D warnings
```

The backend workspace intentionally contains inherited upstream crates. The
release quality boundary is the PicoCalc crates and the explicitly listed
diagnostic modules in `.github/workflows/ci.yml`; a workspace-wide
`cargo fmt --check` is not the release gate.

## Public dependency boundary

The public `picocalc_emu` clone must pass `picocalc.py verify` without a sibling
backend or external app workspace. Firmware target execution requires a clean
checkout of the public backend at the commit named by the target registry.
Historical target reproduction additionally requires the corresponding app
source or source bundle; this is a missing-input condition, not a runtime error.

## Provenance and licenses

The root notices are authoritative. The PicoCalc LCD RGB888 adapter is an
independent implementation; ClockworkPi and GPL-3.0 repositories are not
vendored. The backend preserves its upstream history and third-party notices,
including the GPL-2.0 DOSBox patch and PicoGUS distribution. Do not add a
third-party source or binary without adding its license and provenance to the
appropriate notice first.

Frozen validation records may retain historical build paths because those
paths are evidence fields. New public-facing instructions must use relative
paths or placeholders such as `<workspace>` and must not contain personal
credentials, private keys, access tokens, or device secrets.

This preparation sanitises the current public-facing tree; it does not rewrite
the existing Git history. The backend intentionally retains upstream history,
and old commits may contain historical author metadata or development paths.
Before changing visibility, the repository owner must explicitly choose between
preserving that history and performing a separately reviewed history rewrite.
No history rewrite or force-push is part of this preparation.

## Publication order

1. Complete and review this document, `RELEASE_CHECKLIST.md`, and
   `VERSIONING.md` locally.
2. Run the local gates and confirm both working trees are clean.
3. Commit the release-preparation changes in each repository.
4. Choose the release number and create matching annotated tags on the exact
   paired commits.
5. Push both repositories and their tags in one planned batch, then create the
   GitHub Release with the compatibility table and limitations.
6. Confirm each repository has the intended public README, license, notices,
   tag, and Release notes.
7. Change visibility to public only after the two repositories are mutually
   reachable. Do not use a push or a workflow run as a substitute for the
   local gate above.

The existing `picocalc_emu` firmware workflows use a read-only deploy key for
the pinned backend. Keeping that secret is compatible with public visibility;
changing the workflows to HTTPS or changing their triggers requires a separate
explicit approval because it affects GitHub Actions usage.
