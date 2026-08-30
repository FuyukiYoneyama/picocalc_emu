# P0-B profiler compile-out evidence

Date: 2026-08-31

The profile build was produced from backend `c123933423477b878a1dde8b1f80fb3d731bc8e3` with
`cpu-application-profiler`; the production build was produced from the same clean checkout
without that feature.  The profiler build is only a diagnostic executable and is not used for
wall-time acceptance.

## Binary identity

| build | effective features | runner SHA-256 | size |
|---|---|---|---:|
| candidate production | `sd-gen1-multiblock` | `009313f88c2cdc42b78e6922b666221e80e5b47437b988837ac3231d410e09e4` | 1,377,376 |
| candidate profile | `cpu-application-profiler, sd-gen1-multiblock` | `50bd1683eec5502c61a0c2434e3cee28c6aa8349fa0128de431ef7638216be1b` | 1,415,008 |

The production binary has no defined symbol matching `cpu_application_profile`,
`CpuApplicationProfileSnapshot`, or `build_cpu_application_profile_report`, and no strings
matching `cpu-application-profiler`, `retired_instructions`, `profile_valid`, or
`cpu_application_profile`.  The profile binary contains the expected profiler symbols and
strings.

## Hot-function disassembly check

`decode_execute` is inlined into the core step path in this release build.  The directly emitted
hot symbols were checked with `nm -C -S --defined-only` and `objdump -d --no-show-raw-insn`.

| function | production address/size | production disassembly SHA-256 | profile address/size | profile disassembly SHA-256 |
|---|---|---|---|---|
| `CortexM0Plus::step` | `0xd73a0 / 0x16ac` | `19bd547a37bf9a3f1a106956c24def008abd13d42102ae7ef7b76961ea8798f7` | `0xdf660 / 0x1ec5` | `ec4eb65c67456a632caa0a9ba94eb694e8dfd1bc998e53a8426d86619da35f35` |
| `CortexM0Plus::try_take_any_pending_exception` | `0xcd240 / 0x1f3` | `433c29e5a1c54582fe67480fc2bb4a6a09d2ce9ec7c548488e8773d8e311e42e` | `0xd4ce0 / 0x321` | `f80e0ae0999b45b2a81b9343149d62470e86d3a917a1549aee067b027660e924` |
| `CortexM0Plus::populate_decode_cache` | `0xc5260 / 0xc5` | `fda476fd9597f8cac9beb183a654484dffaf0357f2dcff7e9f3392dfa0779155` | `0xccb70 / 0xc5` | `f81f75a5a2830468dcb7a348c061f29e96c01ed5f49b6a2af28a15df30b44ac0` |

The production hot path therefore has no profiler-specific symbols, strings, or profile report
call path.  This is a compile-out proof; it is not a claim that the production binary is faster.

## Reproduction

```bash
nm -C -S --defined-only <runner> \
  | rg 'cpu_application_profile|CpuApplicationProfileSnapshot|build_cpu_application_profile_report'
strings -a <runner> \
  | rg 'cpu-application-profiler|retired_instructions|profile_valid|cpu_application_profile'
objdump -d --no-show-raw-insn <runner> \
  --start-address=<symbol address> --stop-address=<symbol address + size>
```
