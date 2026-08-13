# U0 provenance / fixture / clean-build evidence

Date: 2026-08-13

This record fixes the external `uf2loader` and `Picocalc_NESco` inputs without
vendoring GPL source or generated firmware into `picocalc_emu`.

## Sources

| input | clean checkout | commit |
|---|---|---|
| `pelrun/uf2loader` | clean detached checkout | `5c44a4b64749062b0200507ceeff3ef2b475e288` |
| `Picocalc_NESco` | clean detached checkout | `ce67aa76e86dec700f086cd70214c247d6317da8` |
| Pico SDK | clean pinned checkout | `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` |

The uf2loader checkout was clean and had no submodules at the pinned commit.
The original external checkout was not modified.

## Toolchain

The clean builds used CMake 3.28.3, Ninja 1.11.1, and
`arm-none-eabi-gcc` 13.2.1 (20231009). Both local SDK checkouts used the same
SDK commit shown above.

## Rebuilt artifact identities

These hashes are recorded instead of storing the external artifacts here:

| artifact | SHA-256 |
|---|---|
| `uf2loader/stage3/boot2_custom.bin` | `c1bc77ebe5edf656c1e70d4f2d8b46bcbf64ce2eeb66dca8c7c3e2ca1edd2ec6` |
| `uf2loader/stage3/bootloader_pico.bin` | `eb448043080cb8e000bf52a1c8ce6cc3ebcd651b472e1d98bb61075ad05354f9` |
| `uf2loader/ui/BOOT2040.bin` | `6cc0d0fd78bbd0fe8501ffdf9ef59d3fa333bb72602133bdad87b20df4dbe717` |
| `uf2loader/diag/diag_pico.bin` | `4779e824a63ee509a546c0f334f0ba9bbbd074bbff3223a783b722a9cf64a4fe` |
| `Picocalc_NESco.bin` | `ce865f2a26fecc55cfd033abfc71590c9918499c477fee81897f7ca5ababeb1c` |
| `Picocalc_NESco.uf2` | `2b2228d3b91212b133f6789f9c7a826e45af0fccf27efdc21ed4e6599cba3407` |

The external source and artifact paths are intentionally not part of the
runtime contract. Reproduce them in a temporary workspace using the pinned
commits and the toolchain above.

## U0 result

U0 is closed: source, SDK, toolchain, and artifact provenance are fixed; the
GPL uf2loader source and generated binaries are not tracked in this repository.
