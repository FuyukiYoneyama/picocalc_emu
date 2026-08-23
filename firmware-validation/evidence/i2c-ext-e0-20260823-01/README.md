# I2C-EXT E0 evidence

This directory freezes the source provenance and observed byte-level wire contract
for the optional private I2C modules before E1 changes the emulator controller.

The canonical machine-readable contract is:

[`../../contracts/i2c-ext-e0-wire-v1.json`](../../contracts/i2c-ext-e0-wire-v1.json)

The source manifest contains hashes for the selected RTC application and the
standalone DS3231 probe. `RTC/Picocalc_RTCtest` has no Git metadata, so its
individual source-file SHA-256 values are the identity. The `PicoCalc` checkout
had one unrelated pre-existing worktree file (`Code/PicoMite/main.c`); it was not
modified and is outside the selected reference scope.

E0 changes no production code and does not claim an emulator capability. The next
stage is E1: explicit I2C address-phase routing, data-NACK propagation, shared
virtual-time extraction, and legacy ACK isolation.
