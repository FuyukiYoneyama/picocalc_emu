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
including the GPL-2.0 DOSBox patch, PicoGUS distribution, MIT OneROM firmware
fixtures and MIT `epio`/`apio` submodules, and the LGPL-3.0 SeaBIOS payload.
Do not add a third-party source or binary without adding its license and
provenance to the appropriate notice first.

Frozen validation records may retain historical build paths because those
paths are evidence fields. New public-facing instructions must use relative
paths or placeholders such as `<workspace>` and must not contain personal
credentials, private keys, access tokens, or device secrets.

Public hardware JPEG evidence is metadata-sanitised before publication: GPS,
capture time, camera make/model, and other EXIF fields are removed while the
ICC colour profile and decoded pixels are retained. The private camera
originals are not part of the public repository or its rewritten history.

The current `picocalc_emu` public-preparation history includes a separately
reviewed rewrite that removes the three superseded hardware JPEG blobs
containing GPS metadata. The replacement images preserve decoded pixels and
all dependent record and contract SHA values were updated before the rewrite.
The old blobs are absent from the rewritten reachable history.

The backend intentionally retains its upstream history, and old commits may
contain historical author metadata or development paths. That history is a
separate visibility decision; no backend history rewrite is implied by the
JPEG sanitisation. Any future sensitive-data rewrite must be separately
reviewed and completed before creating a release tag.

## Publication order

1. Complete and review this document, `RELEASE_CHECKLIST.md`, and
   `VERSIONING.md` locally.
2. Run the local gates and confirm both working trees are clean.
3. Commit the release-preparation changes in each repository.
4. Choose the release number and create matching annotated tags on the exact
   paired commits. Do not move or force-push these tags.
5. Push the paired commits and tags while the repositories are still private;
   do not publish the GitHub Release yet. This fixes the public starting point
   without exposing an untagged release candidate.
6. Change `picoem-picocalc` to public first, then change `picocalc_emu` to
   public. Confirm that the two tagged repositories are anonymously reachable.
7. From a fresh unauthenticated clone of each tag, run the portable local
   checks and confirm the README, licenses, notices, and dependency URLs.
8. Create and publish the primary GitHub Release for the `picocalc_emu` tag,
   including the compatibility table, exact SHAs, known limitations, and
   acquisition instructions. A private draft may be prepared earlier, but
   the user-facing Release is published only after repository visibility is
   public.
9. Do not use a push or a workflow run as a substitute for the local gate
   above. Do not re-run Actions merely because visibility changed.

The existing `picocalc_emu` firmware workflows use a read-only deploy key for
the pinned backend. Keeping that secret is compatible with public visibility;
changing the workflows to HTTPS or changing their triggers requires a separate
explicit approval because it affects GitHub Actions usage.
