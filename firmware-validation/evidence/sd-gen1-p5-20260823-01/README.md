# SD-GEN-1-P5 versioned validation

Date: 2026-08-23

P5 accepts the P4 default-runtime regression as a bounded capability.  It does
not rewrite the existing U6, M-NESCO, FAT, or firmware target records.  The
P4 evidence remains the immutable runtime artifact; this directory records the
promotion decision that is derived from it.

## Decision

`sd-multi-block` is **supported_bounded** in the default PicoCalc runtime.
The accepted wire surface is:

- CMD17/CMD24 single-block read/write;
- CMD18 read, CMD12 stop;
- CMD23 pre-erase and CMD25 multi-block write;
- 512-byte blocks, data tokens, CRC fields, CS boundaries, busy transitions,
  COW overlay, and atomic RAW export.

The P4 synthetic firmware exercised CMD18, CMD12, CMD23, CMD25 and CMD17 over
the real CPU → SIO → SPI0 → SD wire path.  It wrote block 6, read it back, and
the exported image contained 512 bytes of `0xA5`.  Three runs matched in stable
report projection, structured trace, and exported image.

## Evidence and boundaries

The source artifact is the P4 manifest:
`../sd-gen1-p4-20260823-01/manifest.json`.
The versioned decision contract is:
`../../contracts/sd-gen1-p5-validation-v1.json`.

The capability does not claim complete SD compatibility, CSD/CID beyond
bring-up, card removal, write-protect, live directory synchronization, USB
BOOTSEL/MSC, arbitrary SD drivers, or arbitrary uf2loader forks.  The existing
`uf2loader-e2e` capability remains fixed-source and unchanged.

No GitHub Actions run was used.  All validation was local.
