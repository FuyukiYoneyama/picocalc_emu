# VRP-LOAD-0: repository-owned sustained-load profile

Status: **planned; implementation and measurement not started**
Date: 2026-08-29

## Purpose

`VRP-LOAD-0` is the repository-owned workload preparation required before a
future `realtime-1x-qualified` decision.  Its purpose is to measure whether the
preview preserves UX timing under continuous display, audio, CPU, and virtual
time pressure.  The qualification requirement is therefore a load profile,
not a dependency on the semantics or implementation of an external emulator
project.

The formal VRP-5 workload pair will be:

- `picotetris-opt1b` revision 5
- `VRP-LOAD-0`

`picoedit-r1` remains a useful preview candidate and contrast workload, but it
is not a substitute for the sustained-load qualification profile.

## Required profile

The implementation must define and freeze all of the following in
repository-owned source or reproducible, redistributable fixtures.

1. Continuously update the complete 320x320 RGB565 display at a fixed rate.
2. Stream continuous 48 kHz DMA-paced audio concurrently with display updates.
3. Keep the CPU under sustained work so idle fast-forward cannot hide timing
   pressure.
4. Use fixed input, fixed seed, fixed device configuration, and no host wall
   clock as an emulated source of nondeterminism.
5. Run for at least 10 virtual minutes per qualification workload.
6. Build from a clean clone with fixed backend, SDK, compiler, and other
   toolchain identity.

The profile must not skip CPU cycles, emulated frames, IRQs, PIO/DMA events,
device events, or virtual audio events to reach 1x.

## Preparation gate

Before VRP-5 qualification, execute the same input at least three times and
record:

- source, fixture, firmware BIN, runner, backend, and toolchain identity;
- virtual and wall-clock duration, session ratio, and rolling ratio;
- pacer backlog/overrun, presentation drops, and audio underrun/overrun;
- authoritative observation projection and digest;
- CPU/RSS as supplementary measurements; and
- the exact command and output manifest needed for clean-clone reproduction.

The preparation gate is not a hardware verdict.  A dirty checkout, mutable
input, missing provenance, inconsistent digest, or unmeasurable load condition
must fail closed.

The realtime tolerance and lag ceiling are fixed in a separate decision record
after the initial baseline review but before the qualification run.  They must
not be adjusted per run after seeing the result.

## External-project boundary

`Picocalc_NESco` is not an input to this profile.  `picocalc_emu` must not
create, modify, publish, or push an NESco branch to satisfy VRP-LOAD-0.
Diagnostic branches from an external project are not formal evidence or
qualification inputs.

The existing `VRP-NES-0` synthetic NROM fixture and local evidence remain
historical, non-qualifying records.  If NES-specific conformance is later
desired, it must be a separate optional test using an owner-supplied,
unmodified public clean ref or reproducible artifact.

## Completion gate

VRP-LOAD-0 is complete only when its source and fixture are repository-owned,
the clean-clone build is reproducible, the repeated runs satisfy the frozen
determinism and observation checks, and the resulting record can be consumed by
the same admission and preview path used by the existing registered targets.
Completion does not itself mean that the realtime threshold is met; that
decision belongs to VRP-5.
