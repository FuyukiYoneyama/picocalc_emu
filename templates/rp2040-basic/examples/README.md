# PicoCalc copyable examples

These files are intentionally not added to the default target. Copy one
function into `app/main.cpp` after `picocalc::init()` and keep the selected LCD
variant unchanged. They use only the public `picocalc/` headers.

The default template runs the complete smoke test and enables the copied
fixed-sine reference tone. To exercise the generic PCM path, configure with:

```sh
cmake -S . -B build -DPICO_BOARD=pico -DPICOCALC_AUDIO_REFERENCE_TONE=OFF
cmake --build build -j
```

The generated file remains `build/picocalc_app.uf2`; the mode is identified in
the first boot log line and in the audio verification line.
