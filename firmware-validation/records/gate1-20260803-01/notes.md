# Gate 1 notes — clock freeze while every core is idle

`picocalc_helloworld` free-running (no `--stop-pc`) always stops at
`cycles=1529101`, `pc=0x1000198e`, with `stop_reason="error"` and
`error="clock stalled: core0 wfe, core1 halted"`. `0x1000198e` is the
instruction after the `WFE` in `sleep_until`, reached from `lcd_init`'s
delay path. Raising `--cycles` from 10M to 200M does not move the stop
point, so this is a stall, not a budget effect.

Cause: `Emulator::step_serial`'s inner loop exits as soon as every core
is halted or `wfe_waiting`, so the quantum consumes 0 cycles. The
peripheral work that follows (`tick_peripherals` /
`advance_lazy_scheduled` / `tick_pio`) is all scaled by that consumed
count, so the TIMER never advances, the alarm never fires, no event is
latched, and `wake_checks` can never un-park the core. Time is frozen
and no further `step()` can make progress — the runner detects this and
stops rather than spinning.

Impact: Gate 1 acceptance is unaffected (`main` is reached at cycle
127,826, well before the stall). But every later Gate needs execution
past ~1.53M cycles — the LCD draw path, the PSRAM test and the key-input
loop all sit behind SDK sleeps — so this blocks Gate 2 onward. The fix
is an "advance virtual time to the next scheduled event when all cores
are idle" mechanism, which touches core execution semantics and so is
out of scope for the Gate 1 runner work.
