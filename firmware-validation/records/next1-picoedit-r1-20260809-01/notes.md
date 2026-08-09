# NEXT-1 PicoEdit registered regression candidate

This run reuses the exact BIN and frozen backend from the successful first
blind execution. Scenario revision `d7af28965f49cd7363ca5ac68678572d3e6975eb426b6af828dd09a70505b718`
adds only a 250 ms post-save wait so the final Ctrl release is consumed before
the final snapshot and report.

The registered `picoedit-r1` target passes through the normal
`tools/picocalc.py test --mode firmware --target picoedit-r1` path with all
report checks, normalized report hash, and scenario timeline hash enforced.
An independent clean clone reproduced the BIN and UF2 exactly; ELF bytes remain
build-path-dependent because debug sections contain the absolute source path.
