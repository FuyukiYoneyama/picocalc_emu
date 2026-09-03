//! PERF-Q0 scratch fixture.
//!
//! A step-start-only engagement predicate sees PIO0 as idle at the start of
//! this program.  The CPU enables PIO0 SM0 during the same quantum.  With a
//! larger quantum, the PIO scheduler therefore starts observing the state
//! only after the CPU batch has already completed.  The q1 reference exposes
//! the resulting phase difference in the PIO pin output.
//!
//! This file is intentionally kept in the Q0 scratch worktree.  It is not a
//! production regression test until a transition-barrier design is accepted.

use rp2040_emu::bus::PIO0_BASE;
use rp2040_emu::{Config, Emulator, EmulatorBuilder};

const SRAM_BASE: u32 = 0x2000_0000;
const STACK_TOP: u32 = 0x2003_0000;
const PIO0_CTRL: u32 = PIO0_BASE;

fn configure_alternating_pio(emu: &mut Emulator) {
    // SM0: alternate the output pin every PIO clock.
    emu.bus.write32(PIO0_BASE + 0x048, 0xE001); // SET PINS, 1
    emu.bus.write32(PIO0_BASE + 0x04C, 0xE000); // SET PINS, 0
    emu.bus.write32(PIO0_BASE + 0x0DC, 1u32 << 26); // SET_COUNT=1, BASE=0
    emu.bus.write32(PIO0_BASE + 0x0CC, 1u32 << 12); // wrap 0..1
    emu.bus.write32(PIO0_BASE + 0x0D8, 0xE081); // force SET PINDIRS, 1
}

fn load_cpu_enabler(emu: &mut Emulator) {
    // Thumb-16 program at SRAM_BASE:
    //   LDR  r0, [PC, #8]  ; r0 = PIO0_CTRL
    //   MOVS r1, #1
    //   STR  r1, [r0, #0]  ; enable PIO0 SM0
    //   B    .
    //   NOP; NOP; .word PIO0_CTRL
    emu.poke(SRAM_BASE, 0x2101_4802);
    emu.poke(SRAM_BASE + 4, 0xE7FE_6001);
    emu.poke(SRAM_BASE + 8, 0xBF00_BF00);
    emu.poke(SRAM_BASE + 12, PIO0_CTRL);
    emu.cores[0].regs.msp = STACK_TOP;
    emu.cores[0].regs.r[13] = STACK_TOP;
    emu.cores[0].regs.set_pc(SRAM_BASE);
    emu.cores[0].regs.xpsr = 1 << 24;
}

fn build(step_quantum: u32) -> Emulator {
    let mut emu = EmulatorBuilder::new(Config::default())
        .step_quantum(step_quantum)
        .build()
        .expect("Serial build is infallible");
    configure_alternating_pio(&mut emu);
    load_cpu_enabler(&mut emu);
    emu
}

#[test]
fn cpu_can_enable_pio_inside_a_disengaged_start_step() {
    let mut emu = build(16);
    assert!(emu.bus.pio_all_idle(), "fixture must begin disengaged");

    let consumed = emu.step().expect("Serial step is infallible");

    assert!(consumed >= 16, "quantum is a cycle target, not an instruction count");
    assert!(emu.bus.pio[0].any_sm_enabled());
    assert_eq!(emu.cycles(), consumed);
}

#[test]
fn q16_cannot_match_q1_without_observing_the_mid_quantum_transition() {
    let mut q16 = build(16);
    let consumed = q16.step().expect("q16 step is infallible");
    let target_cycles = q16.cycles();

    let mut q1 = build(1);
    while q1.cycles() < target_cycles {
        q1.step().expect("q1 step is infallible");
    }

    assert_eq!(q1.cycles(), target_cycles);
    assert_eq!(consumed, target_cycles);
    assert!(q1.bus.pio[0].any_sm_enabled());
    assert!(q16.bus.pio[0].any_sm_enabled());

    // q1 observes PIO clocks immediately after the CPU's enable instruction;
    // q16 observes PIO only after the whole CPU quantum.  The alternating SET
    // PINS program makes that phase difference guest-visible at the same
    // final guest cycle boundary.
    assert_ne!(q1.gpio_read(0), q16.gpio_read(0));
    assert!(!q1.gpio_read(0), "q1 observes the earlier PIO phase");
    assert!(q16.gpio_read(0), "q16 observes the later PIO phase");
}
