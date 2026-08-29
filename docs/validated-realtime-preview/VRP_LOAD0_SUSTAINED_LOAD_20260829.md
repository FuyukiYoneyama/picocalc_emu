# VRP-LOAD-0: repository-owned sustained-load profile

Status: **prototype implemented; 1- and 2-virtual-second clean-clone runtime/input smokes passed; 120-second vertical slice and preview-only target admission passed; three-run determinism and preparation gate pending**
Date: 2026-08-30

## Purpose

`VRP-LOAD-0` is the repository-owned workload preparation required before a
future `realtime-1x-qualified` decision.  Its purpose is to measure whether the
preview preserves UX timing under continuous display, audio, CPU, and virtual
time pressure.  The qualification requirement is therefore a load profile,
not a dependency on the semantics or implementation of an external emulator
project.

## Current implementation status

The repository-owned r1 fixture is implemented at source commit
`40a9e07ca34c895cb90b4a1af550e5ed236a26c6` under
`reference-projects/vrp-load0-sustained/`. Its bounded smoke build is
reproducible: two independent clean clones with the same toolchain, timestamp,
and CMake cache produced identical BIN/UF2 hashes. A clean backend runner at
`65c795e87321e79b960ac8a7495a205de6a24ec0` then passed one- and two-
virtual-second input smokes with 320x320 full-screen writes, core-0/core-1
work, 48 kHz audio, four delivered keyboard events, and complete UART result
records. The two-second smoke used the checked-in 1,000 ms-offset scenario.

This does not complete `VRP-LOAD-0`. The checked-in 120-second scenario has
passed the vertical-slice run and is now connected to the preview-only target
`vrp-load0-r1-vslice` revision 1. Its wrapper report passed the load-specific
receipt/admission path and the headless preview consumer. This target is only
an admission-path record; it does not close the three-run 10-minute
preparation gate. The slice observed a high frame lag and report-wide
timer-miss diagnostic; these remain inputs to the later baseline and threshold
decision, not an unrecorded pass or failure.

The non-formal slice record is
`firmware-validation/records/vrp-load0-vslice-120s-20260829-01/record.json`.
It fixes the successful run as `scenario_done` after 120,000,000 virtual
microseconds and preserves the report, audio-analysis, and UART artifacts.
The run produced 3,600 scheduled frames with zero presentation drops, 0
firmware audio underruns, 0 audio write drops, 48,000 Hz audio observation,
and four delivered fixed keyboard events. Both CPU cores reported sustained
work. The measured virtual/wall ratio was `0.019292827826945906`, so this is
not a 1x result. The report-wide audio timer-miss and block-boundary counters
are retained as observations rather than being hidden or converted into a
threshold pass.

The formal VRP-5 workload pair is defined at the logical-workload level as:

- `picotetris-opt1b` revision 5 as the baseline workload identity
- `VRP-LOAD-0`

The launch record must additionally name a reachable, clean, versioned target
id/revision for the `picotetris-opt1b` workload.  The old
`picotetris-opt1b-vrp2f` revision 8, which pins the unreachable
`c1c20d7d86a3006569375bc333cf72494e95eb46`, is not reusable for VRP-5 until it
has been revalidated under the backend-pin preflight.  The baseline revision,
the VRP-2-f revision, and the VRP-4 revision 9 must not be described as the
same target.

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

## Implementation contract for the prototype and qualification

The six requirements above are necessary but are not yet an executable
fixture specification.  The r1 source was coded against the versioned profile
record, and future source or scenario changes must create a new profile
revision rather than silently changing this contract. The record contains all
of the following:

- repository-owned source directory, license, target id/revision, artifact
  names, and source/fixture/BIN SHA-256 values;
- exact display update rate, RGB565 frame-generation algorithm, seed, LCD
  device profile, and frame/event marker;
- audio channel count, sample format, DMA timer/block/buffer configuration,
  deterministic pattern/seed, and expected audio observation/digest;
- CPU/core-1 workload, allowed waits, the `step_until` exact-idle-fast-forward
  policy, and the observation proving that the workload still applies timing
  pressure;
- fixed key or UART input sequence, input virtual cycles, virtual duration,
  cycle limit, stop marker, and expected authoritative observation digest;
- clean-clone build commands, SDK/BSP/compiler/CMake/Ninja identity, reachable
  backend commit, backend executable SHA-256, and output manifest; and
- separate definitions for core throughput/timing metrics and GUI
  input-to-visible-response metrics.

The profile must provide a runnable command for the deterministic headless
qualification path and a separate command or procedure for the same-BIN
preview API/GUI UX smoke.  A timer around the release runner alone is not
evidence of GUI UX.  If input-to-visible-response cannot be measured, the
result must be labelled `continuous-load timing`, not `1x UX`.

The first implementation gate is a 1--2 virtual-minute vertical slice from a
clean clone: build, run, report/receipt, existing admission, and preview path.
The current one-virtual-second smoke is deliberately shorter than that gate
and is recorded only as implementation progress. The 120-second slice has now
passed this path through preview-only target `vrp-load0-r1-vslice` revision 1.
The profile fields and artifacts are therefore available for the next gate,
but the workload is not called complete until at least three deterministic
runs and the 10-virtual-minute preparation run pass.

The existing backend may exactly fast-forward a proven both-cores-blocked
interval to an event boundary.  This is not automatically an invalid shortcut;
the profile must explicitly state whether it is allowed and how semantic
equivalence and sustained timing pressure are evidenced.

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

The decision record is not a post-hoc pass recipe.  It must contain the
non-negotiable conditions (for example digest mismatch, drop, or underrun),
the ratio/lag statistic, qualification run count, threshold-selection rule,
and the mechanical `REALTIME OK` / `REALTIME NOT MET` decision.  A baseline
may inform a threshold only under that predeclared rule; target revision,
measurement path, threshold, and included runs must not be changed after
qualification results are visible.

## External-project boundary

`Picocalc_NESco` is not an input to this profile.  `picocalc_emu` must not
create, modify, publish, or push an NESco branch to satisfy VRP-LOAD-0.
Diagnostic branches from an external project are not formal evidence or
qualification inputs.

The existing `VRP-NES-0` synthetic NROM fixture and local evidence remain
historical, non-qualifying records.  If NES-specific conformance is later
desired, it must be a separate optional test using an owner-supplied,
unmodified public clean ref or reproducible artifact.

## Backend prerequisite

The `VRP-LOAD-0` source and vertical slice may be implemented in parallel with
backend-pin recovery. Formal validation of the preview-only vertical-slice
target became allowable after the backend commit was reachable and the clean
checkout was fixed; it is recorded as `vrp-load0-r1-vslice` revision 1. Final
LOAD-0 completion and VRP-5 qualification still require the preparation gate
and the separately frozen threshold decision. As of 2026-08-29,
`c1c20d7d86a3006569375bc333cf72494e95eb46` is not reachable from a branch or
tag; the current `main` is `65c795e87321e79b960ac8a7495a205de6a24ec0`.
Existing c1-pinned evidence is immutable historical evidence, not a reason to
rewrite old records.

Any existing uncommitted backend changes must be classified separately before
revalidation.  They must either be recorded in a dedicated backend commit
with its own identity or be removed by the owner; they must not be silently
included in a preview implementation commit.

## Completion gate

VRP-LOAD-0 is complete only when its source and fixture are repository-owned,
the clean-clone build is reproducible, the repeated runs satisfy the frozen
determinism and observation checks, and the resulting record can be consumed by
the same admission and preview path used by the existing registered targets.
Completion does not itself mean that the realtime threshold is met; that
decision belongs to VRP-5.
