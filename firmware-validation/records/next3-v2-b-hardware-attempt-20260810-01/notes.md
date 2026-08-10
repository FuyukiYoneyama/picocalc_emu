# NEXT3 v2 Fault B hardware-first result

The first complete PicoCalc run used the frozen Fault B identity and produced
15 stable evidence markers. It failed the LCD test, but it did not reproduce
the oracle frozen before implementation.

Black and white solid fills passed. Red, green, and blue returned the same
rotated values already seen in v1 and each had four mismatches. The final
pattern returned `0x7c00` for all four samples and had four mismatches. The
frozen oracle required all five solids to pass and the pattern to have three
mismatches. `app=fail` and `sd=pass` were as expected.

This is `inconclusive`, not a hardware-confirmed negative case. The negative
denominator remains zero. The oracle is unchanged, no retry is requested, and
the Fault B BIN must not be run in the emulator.

The log's `window_cs=held_from_caset_through_ramwr` diagnostic is stale: that
string came from A1 and was outside the deliberately narrow writer/identity
change. The canonical source diff proves Fault B uses the CS-separated writer.
The stale string is preserved as evidence and is not treated as the writer
mode authority.

The supplied photograph contained location metadata. The repository copy has
all metadata removed; its decoded RGB SHA-256 is identical to the supplied
image.
