# First-run trace and failure boundary

The first integrated attempt used a FAT32 fixture with an invalid BPB media
descriptor. The emulator correctly stopped at SD mount rather than treating
the image as a valid card. The fixture was rebuilt with the BPB media byte set
to `0xf8`; the same direct-boot scenario then mounted FAT32 and reached the
ROM menu. This is the fixed fixture used by M-NESCO-S1 (its source SHA is in
the M-NESCO evidence README and report).

This record is deliberately a short failure boundary, not a claim that the
external uf2loader has already completed. U0 fixes the distinction between a
bad input image and a missing emulator feature before U3/U6 work begins.
