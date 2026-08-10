# NEXT3 SD CMD8 CRC Fault B hardware result

The physical result matches every field of the frozen negative oracle. The
same frozen Fault B UF2 was launched through `uf2loader`; its identity matches
canonical commit `e78cabbe2041`. CMD0 succeeds, then CMD8 with CRC `0x85`
returns R1 `0x09`. Those bits are exactly idle-state plus COM_CRC_ERROR.
Initialization stops at CMD8, no later SD initialization command or filesystem
operation occurs, and the application reaches the stable red FAIL state.

The complete EVIDENCE marker repeats 46 times without changing. The supplied
photograph shows the expected white top strip and red center and bottom
regions. Its repository copy has location-bearing metadata removed while the
decoded RGB SHA remains identical to the untouched original.

This is not an application PASS. It is a hardware-confirmed negative case: the
injected fault failed on hardware for the exact predeclared reason. The first
run of the same BIN in frozen backend `4a908648` is now allowed exactly once.
Its result must be preserved before any backend change. The negative
denominator increases to one only when the ensuing classification record and
KPI snapshot are fixed; no percentage is asserted in this intermediate file.
