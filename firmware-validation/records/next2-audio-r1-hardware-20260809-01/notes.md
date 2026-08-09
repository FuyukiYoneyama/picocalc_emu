# NEXT-2B v3 hardware correlation notes

## Verdict

The registered `picocalc-audio-r1` UF2 passed on the physical ClockworkPi
PicoCalc. This closes the same-artifact hardware-correlation requirement for
the frozen v3 contract without changing its digital or physical acceptance
criteria after the run.

The USB CDC capture contains 18 complete copies of the five-marker firmware
PASS block. Every contract value matches: 49,152 accepted and drained frames,
DMA timer 0 at `3/15625`, TREQ 59, PWM slice 5 `CC`, 32-bit fixed destination,
zero underrun/drop/clip, 976,562 Hz carrier, 512-frame ring, and an overall
firmware verdict of PASS. The first captured LCD initialization line starts
mid-byte because the monitor attached late; it precedes the 18 complete blocks
and is permitted by the frozen late-attach procedure.

The submitted 15.53-second video contains a single sustained acoustic event
from approximately 2.689 to 3.740 seconds, followed by more than ten seconds of
the held `NEXT2 AUDIO` final screen. That screen independently shows green PASS
for INIT, DMA CFG, STREAM, STATS, and FIRMWARE. The approximately 1.05-second
microphone event agrees with the programmed 49,152 / 48,000 = 1.024-second
playback after allowing for thresholding and room/device response.

## Authority boundary

The physical recording proves that the same registered firmware path produces
audible output on PicoCalc hardware and reaches the frozen firmware self-
verdict. It does not replace the emulator's exact sink oracle. The byte-exact
49,152 post-quantizer writes, sink SHA-256, DMA due cycles, 384 block starts,
383 software-retrigger boundaries, gap stream, and service-latency stream remain
the authority of the formal emulator record.

Together, the formal emulator record and this physical record establish the
bounded `audio-output` capability covered by `picocalc-audio-r1`. They do not
claim arbitrary codecs, rates, PWM slices, DMA topologies, mixing, speaker
frequency response, or waveform equality between the digital sink and a camera
microphone.

## Privacy and preservation

`usb-cdc.log` preserves the supplied bytes and CRLF line endings. The original
video is identified by SHA-256 but is not copied into the repository because it
contains camera and location metadata. `audio-capture.flac` contains the full
decoded audio track with metadata removed, and its decoded 24-bit PCM digest is
identical to the submitted video's decoded audio. `final.jpg` is a metadata-free
frame extracted at 10.000 seconds, when the five-PASS screen is stable.
