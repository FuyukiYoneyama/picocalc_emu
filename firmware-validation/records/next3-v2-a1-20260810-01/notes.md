# NEXT3 v2 A1 baseline

A1 combines the current correct single-CS writer with the historical `5b12a7c`
SIO bitbang RAMRD observer. Two clean builds produced identical BIN and UF2
hashes. The first run on promoted backend `e985a9d` was intentionally preserved:
the firmware reached LCD readback, but the backend saw zero RAMRD commands because
variant A exposed only SPI1 FIFO transfers and did not connect SIO GPIO edges or
MISO to the shared panel model.

The backend was extended without promoting it. The pin observer is activated by
an actual SCK pad edge, so normal SPI1 frames are not counted twice. Bit-level
full-duplex RAMRD suppresses the model-side extra dummy only during that selected
transaction and restores same-transfer SPI timing on deselect. RGB666 RAMRD uses
the R,G,B order in the frozen historical hardware evidence; RGB565 variant B is
unchanged. Board/harness unit tests total 117, the A1 firmware run passes, and a
separate PIO/RGB565 firmware run passes on the same clean backend.

The current stop is deliberate: A1 hardware correlation is still required.
Fault B must not be implemented or run until the exact UF2 below passes through
the normal `uf2loader` path.

- UF2: `picocalc-next3-lcd-fault/build/picocalc_app.uf2`
- UF2 SHA-256: `ce15219188b35ef54edebfcb6b6df09ec8632145d8e1ce28ea750f2444742c99`
- expected final marker: `[NEXT3][LCD_CS_V2_A1][EVIDENCE] ... solid=pass pattern=pass mismatches=0 app=pass sd=pass`
- expected screen: five solid readbacks and the final four-colour pattern all PASS

No GitHub Actions run or push was used for this development cycle.
