# NEXT3 v2 Fault B artifact freeze

Fault B is derived from the canonical A1 tree. The net tree diff from A1 has
exactly three paths: identity in `CMakeLists.txt`, evidence marker in
`app/main.cpp`, and `begin_window()` write-side CS framing in the RGB666 vendor
driver. The historical SIO bitbang observer and every oracle input remain
unchanged.

Two clean builds at the A1 timestamp produced identical BIN and UF2 hashes.
The source bundle contains the complete linear repository history and resolves
HEAD to canonical Fault B commit `3a073fbf206b`.

Fault B has deliberately not been executed in the emulator. Hardware must run
first. Only an exact match to the pre-existing oracle—five solid fills pass,
the pattern reads red/red/red/red with three mismatches, app fail, SD pass—may
unlock the first backend run. Any other result is `inconclusive`; the oracle
must not be changed afterward.
