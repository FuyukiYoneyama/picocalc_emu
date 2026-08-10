# NEXT3 LCD CS fault v1 hardware attempt

The exact UF2 fixed by `next3-lcd-cs-fault-v1-20260810-01` was copied to the
PicoCalc SD card and launched through the installed uf2loader application menu.
This is the normal application launch path; BOOTSEL was not used to install the
application.

The hardware produced a definite LCD failure, but it did not satisfy the oracle
frozen before the first emulator run. Black and white solid fills passed. Red,
green, and blue solid fills each failed with four mismatches. The four-colour
pattern also failed with four mismatches. The repeated final marker was:

```text
[NEXT3][LCD_CS_FAULT][EVIDENCE] app_git=d7f0668db17e bsp_git=6bd826e7dcaf-dirty solid=fail pattern=fail mismatches=4 app=fail sd=pass
```

The frozen oracle required all five solid fills to pass and the pattern to fail
with three mismatches. The oracle is not changed after observing hardware. This
attempt is therefore `inconclusive`, contributes zero to the negative denominator,
and does not authorize the first emulator run.

The supplied JPEG contained GPS and device metadata. Only the repository copy
was stripped; its decoded RGB SHA-256 remains identical to the supplied original.
The supplied UART log used CRLF line endings. Only the repository copy was
normalized to LF; both source and normalized SHA-256 values are recorded.
