# Preview presentation asset

`picocalc-device-skin.png` is an optional presentation-only image used by
`python3 tools/picocalc.py preview-gui`.  It is a sanitized, downscaled copy of
the PicoCalc photograph supplied by the project owner on 2026-08-28.  EXIF and
other camera metadata were removed before it was added to the repository.

The asset is not part of the emulator model, validation report, receipt, or
observation digest.  It may be replaced or omitted by a downstream user; use
`--skin none` to show a plain integer-scaled LCD.  The calibrated LCD opening
for this 607x1026 image is `(x=38, y=69, width=520, height=475)` pixels.  The
frontend stretches only the displayed RGB565 presentation into that opening;
the raw 320x320 framebuffer remains unchanged.

Asset SHA-256:

```text
382c5d0a33225e3771c40ab0c3b0a421a87b82bc6104a1cb2bd22d8711d467da
```

If the image is redistributed outside this repository, confirm that the
photograph owner's permission still covers that use.  Do not use a file from
the shared `log/` directory as a runtime dependency.
