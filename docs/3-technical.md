# SH4 Controls2D: technical reference

*Level 3 of 3: for ROM hackers and reverse engineers. Lower levels: [1-overview.md](1-overview.md), [2-engineering.md](2-engineering.md).*

The source files are the primary record. They carry the same notes in their header comments:

| Topic | File |
| --- | --- |
| PC plugin (hook, SH2 rule, turning operands, config) | `pc/controls2d.c` |
| PC test harness | `pc/test/harness.c` (+ `pc/test/inc/windows.h` shim) |
| PS2 code cave | `ps2/src/cave.S` |
| PS2 pnach generator | `ps2/src/make_pnach.py` |
| PS2 ISO / ELF hard-patcher | `ps2/src/patch_iso.py` |
| EE interpreter, input-builder sim, tests | `ps2/test/ee.py`, `ps2/test/ps2sim.py`, `ps2/test/test_ps2.py`, `ps2/test/test_iso.py` |

## Supported builds

| Platform | File | Identifier |
| --- | --- | --- |
| PC (GOG) | `SILENT_HILL_4.exe` | PE timestamp `0x41071F62`, image base `0x400000` |
| PS2 NTSC-U | `SLUS_208.73` (SLUS-20873) | ELF CRC `3919136D` (PCSX2's game CRC) |
| Reference | Silent Hill 2 PC `sh2pc.exe` | 2D control-style logic at `0x547FA0` |

## Game behaviour (from the executables)

### Direction

| | PC | PS2 |
| --- | --- | --- |
| Third-person input builder | `0x52F260` | `0x15AA70` |
| Its only call site (player update) | `0x534B2E` (`E8 2D A7 FF FF`) | `0x1B53C0` (`jal`) |
| Latched camera yaw the builder adds | `[0x10A1918]` (read at `0x52F5D5`, `D9 05 18 19 0A 01`) | `[0x45A4B0]` |
| Where the game sets that yaw | player-controller init `0x52ED80` / `0x52EEA0`, via per-camera scene tables; yaw computed at `0x52ECE0` | scene init `0x15A3C0`; yaw computed at `0x15A400` |
| `GetCameraForward(float out[4])` | `0x55BFC0` | `0x15A1E0` |
| Left stick X / Y (`float f(int port)`) | `0x4F8610` / `0x4F8660` | `0x1AAF30` / `0x1AAF90` |
| `atan2f` | (CRT) | `0x121548` (`f12` = y, `f13` = x) |
| Scripted stick inversion flag | `[0x10A19DC]` | `[0x45A488]` |
| Turn-around check (> 135°) | `0x537B80` | not separately located |

- The builder computes `target = atan2(stickX, -stickY) + camYaw`, and the camera yaw is `atan2(fwd.x, fwd.z)`. Controls2D uses the same two formulas, so with a static camera the result is bit-identical to the game.
- The yaw is written only at controller initialisation, so within a camera zone it never follows pans, and a re-init re-bases the stick instantly. This is the whole "drifting up" bug.

### Turning (PC addresses; the PS2 code has the same structure)

- Steering at `0x52FCDB` turns the walking direction toward the target at `rate = 6π − speed·(4π + run·π)` rad/s: 1080°/s standing, 360°/s walking, 180°/s running. Running is capped at 60% while a turn is in progress.
- At 30 fps a 90° change takes 8 frames walking and 15 frames running. The PS2 test prints the original arc: 12, 24, 36 … 90° over 8 frames.
- A second stage at `0x52F90D` applies when the camera's horizontal forward component is < 0.95 (threshold compared at `0x52F8CE`). It limits the turn to 0.2 × that component per frame.
- Body facing follows the walking direction at 12 rad/s (≈ 690°/s), at `0x535062`.

### SH2's rule (`sh2pc.exe` `0x547FA0`)

Camera yaw = `atan2(target − eye)` every frame. On a camera change while the stick is held, it keeps the previous yaw until the stick is released or moves > 30° from its angle at the cut.

## PC plugin (`pc/controls2d.c`, v1.1)

**Loader interface.** Zealot's mod loader takes `__stdcall` exports looked up by name: `LoadPlugin(int base)`, `Update()` (once per frame), `UnloadPlugin()`. `controls2d.def` fixes the undecorated names.

**Install** (first `Update`, so the game is fully mapped):

1. Verify signature bytes:

   | VA | Bytes | What |
   | --- | --- | --- |
   | `0x534B2E` | `E8 2D A7 FF FF` | call to the builder |
   | `0x52F5D5` | `D9 05 18 19 0A 01` | `fld [0x10A1918]` |
   | `0x55BFC0` | `55 8B EC 8B 45 08 8B 0D 60 41 2E 01` | GetCameraForward prologue |
   | `0x4F8610` | `D9 05 4C BE 07 01` | GetLeftStickX |
   | `0x4F8660` | `D9 05 50 BE 07 01` | GetLeftStickY |

   If any check fails with `strict=1` (the default), the plugin installs nothing.
2. `VirtualAlloc` an RWX stub containing `call Controls2D_BeforeInput` and `jmp 0x52F260`. Rewrite the `rel32` at `0x534B2E` to call the stub. The builder's `ret` goes straight back to the game.
3. If `snap_turn=1`, verify and redirect six x87 memory operands (`D8 xx <abs32>`). Each operand moves from the shared constant to a plugin-owned `volatile float`, so only that one instruction changes:

   | Instruction VA | Op | Original constant | Value | Replacement |
   | --- | --- | --- | --- | --- |
   | `0x52FCE1` | `fmul` (`D8 0D`) | `0x5B79DC` | π | `g_zero` (0: no running penalty) |
   | `0x52FCE7` | `fsubr` (`D8 2D`) | `0x5B7D28` | 2π | `g_turnRate` |
   | `0x52FCED` | `fsubr` (`D8 2D`) | `0x5B7ED8` | 6π | `g_turnRate` |
   | `0x52FCF9` | `fsubr` (`D8 2D`) | `0x5B7ED8` | 6π | `g_turnRate` (standing) |
   | `0x52F8CE` | `fcomp` (`D8 1D`) | `0x5B7DB4` | 0.95 | `g_always` = −1 (steep stage always takes the stick direction) |
   | `0x535062` | `fmul` (`D8 0D`) | `0x5B8160` | 12.0 | `g_faceRate` |

   - `turn_speed=0` sets `g_turnRate` to 1e6 rad/s, which is instant. Nonzero values are clamped to ≥ 90°/s.
   - `facing_speed=0` leaves the facing operand alone. The default is 1440°/s.
   - A turning-check failure disables only snap turning. The camera part still installs.

**Per frame (`Controls2D_BeforeInput`):**

- `gameWrote = (yaw != lastWritten)` detects a controller re-init.
- If the camera's horizontal forward² ≤ 1e-8 (looking straight down), the game's value is left in place.
- **Cut** = `|wrap(cam − prevCam)| > cut_angle` (20°), or `gameWrote` after a previous write.
- On a cut with the stick pushed (dead zone 0.10) and `hold_on_cut=1`, the plugin latches the stick angle. The latch is released when the stick returns to the dead zone or moves > `release_angle` (30°).
- When disabled with F3, it restores the game's own last-written yaw. F3 also swaps the turning operands back.

**Unload** restores the call bytes, all operands and the game's yaw, then frees the stub.

## PS2 pnach (`ps2/SLUS-20873_3919136D.pnach`)

### Snap turning: nine words

| Address | Instant | Fast | Original meaning |
| --- | --- | --- | --- |
| `0x15B794` / `0x15B79C` | `lui/ori` → 0.0 | same | running penalty π |
| `0x15B7A4` / `0x15B7A8` | → `0x49742400` (1e6) | → `0x4196CBE4` (6π = 1080°/s) | 2π term |
| `0x15B7AC` / `0x15B7B0` | → `0x49742400` | → `0x4196CBE4` | 6π term |
| `0x15B208` / `0x15B20C` | → `0xBF800000` (−1.0) | same | steep-camera threshold 0.95 |
| `0x1B5A38` | `lui` → `0x41C80000` (25 rad/s ≈ 1432°/s) | same | body facing 12 rad/s |

### Camera-relative directions: code cave

- **Hook.** `0x1B53C0` is changed to `jal 0x000FC000` (`0x0C03F000`).
- **Code** is at `0x000FC000`–`0x000FC277`. **Data** starts at `0x000FC400`:

  | Offset | Contents |
  | --- | --- |
  | `+0x00`–`+0x38` | state: ref, prev, latch stick, last written, flags, saved `ra` |
  | `+0x40` | 16-byte camera-forward buffer |
  | `+0x60` | π |
  | `+0x64` | 2π |
  | `+0x68` | cut 20° (0.349 rad) |
  | `+0x6C` | release 30° (0.5236 rad) |
  | `+0x70` | dead zone² 0.01 |
  | `+0x74` | ε 1e-8 |
  | `+0x78` | magic `"SH2D"` (`0x53483244`) |

- **First-run reset.** If `D_MAGIC != K_MAGIC`, the state flags are zeroed. This covers RAM left over from the boot loader.
- **Register discipline:**
  - Only caller-saved registers are used (`t0`–`t5`, `t9`, `f0`–`f3`, `f12`/`f13`).
  - Values that must survive the `jal`s to game functions are kept in the data block, not in registers.
  - `ra` is saved at `+0x38` and restored before the tail jump `j 0x15AA70`, so the builder returns to the original caller.
  - The base register `t9` is rebuilt (`lui/addiu`) after every call.
- Branch-delay slots are filled explicitly (`.set noreorder`). `.set oddspreg` is required because the EE has 32 single-precision FPRs.
- **Why the RAM is free.** `SLUS_208.73` loads at `0x100000` (main segment file offset `0x100`, size `0x2C9B80`). The stack is at the top of RAM, and no code or data reference falls in `0x80000`–`0xFFFFF`.
- **Building.** `make_pnach.py` assembles `cave.S` with clang (MIPS target) or zig. With `--elf`, it checks every original word against your executable before writing.

## ISO hard-patch (`ps2/src/patch_iso.py`)

- Accepts only the unmodified ELF (CRC `3919136D`), so it can't double-patch. It reads the patch words from the pnach, so the pnach is the single source of truth.
- Words inside the main segment are written at `addr − 0x100000 + 0x100`.
- Cave words (`0xFC000`, size `0x480`) go into a new **4th `PT_LOAD`** header:
  - fields: `p_offset` = `0x2C9C80` (the old tail), `p_vaddr = p_paddr = 0xFC000`, `p_filesz = p_memsz = 0x480`, flags RWX, align `0x80`;
  - the tail held only `.comment`, `.reginfo`, `.shstrtab` and the section header table;
  - `e_shoff`, `e_shnum` and `e_shstrndx` are zeroed;
  - the program header table has room for the 4th entry before offset `0x100`, and the script asserts this.
- File size and LBA are unchanged, so the ISO9660 directory and every other file are untouched.
- The patched ELF gets a new CRC. The pnach and PCSX2's built-in widescreen patch are keyed to the old one.
- In PCSX2, test with Fast Boot **off**. With Fast Boot on, PCSX2 loads the ELF itself instead of using the BIOS loader, which is what real hardware uses for the extra segment.

## Verification

**PC (`pc/test/harness.c`).** The test flattens the PE image with `pefile` and maps it with `mmap` at `0x400000` in a 32-bit Linux process. It `#include`s `controls2d.c` and shims the few Win32 calls. Each frame runs the installed stub, so the code under test is the plugin's C plus the game's real builder, and the result is read from `0x10A1A70` (input + `0x70`). It checks that:

- signature checks pass and the call is redirected to the stub;
- a static camera matches the original;
- a 60° pan is followed;
- a cut to 150° holds at 60°;
- a 20° nudge steers relative to the old camera, and a 40° move releases to the new one;
- a re-init is detected and held through;
- the scripted inversion gives 180°;
- F3 off restores the game's own yaw, F3 on follows again;
- unload restores the original 5 bytes;
- `hold_on_cut=0` takes the new camera immediately;
- turning reaches 90° on the next frame and flips to 270° on the next frame;
- the original arc still applies with F3 off;
- a steep camera (0.8) still turns straight;
- `facing_speed=0` leaves the operand alone;
- `turn_speed=720` gives 24°/frame at 30 fps and 12°/frame at 60 fps, so the rate is frame-rate independent;
- a corrupted signature makes it refuse and install nothing.

**PS2 (`ps2/test/test_ps2.py`).** `ee.py` is an R5900 interpreter covering enough of the integer ISA, the FPU (including ACC ops) and VU0 macro mode to run the builder. Decoding uses `rabbitizer`. `ps2sim.py` loads the ELF's segments and stubs the pad, camera and `atan2` functions. Test sections:

| # | Checks |
| --- | --- |
| 0 | every patched word matches the original game |
| 1–7 | static camera, pan, cut hold, release, re-init as cut, scripted inversion, camera straight down |
| 8 | register discipline: the patched `jal` enters the cave, the cave ends at the builder with the original `ra`, and `s0`–`s7`, `gp`, `sp`, `fp` and `f20`–`f31` are untouched |
| 9 | turning: original arc vs. next-frame turn, for both the instant and fast variants |
| 10 | both parts together |
| 11 | the committed pnach equals what `cave.S` + `make_pnach.py` build |

`test_iso.py` checks the hard-patched ELF:

- it's the same size as the original;
- its segments load at `0x100000` and `0xFC000`, `readelf` parses it cleanly, and it has 4 `LOAD` headers and no sections;
- outside the cave, exactly 21 words differ: 10 turning and hook words, 3 header fields, and the 8-word program header;
- run in the interpreter with no pnach applied, it gives next-frame turning, follows pans, and holds and releases on cuts (the unpatched ELF still arcs);
- `--no-camera` changes only the 9 turning words, and `--turn fast` gives 36°/frame;
- an ISO round trip changes bytes only inside the executable's extent.

## Dead ends and known issues

- **Tank-control approach.** The camera mod's "Tank Controls" option and Controls2D both rewrite the stick's meaning, so they conflict. Leave that option off.
- **Free camera.** The SH2 rule and the cut threshold (> 20°/frame) were designed around SH4's authored cameras. With Zealot's free camera turned on, the results may differ. That combination isn't tested.
- **60 fps.** A 60 fps fix was developed alongside this and left out of the repo because it was buggy. The turning rates are per second, so they are frame-rate independent (see the 720°/s test above). The cut threshold, however, is per frame: at 60 fps a pan must be twice as fast to count as a cut.
- **Turn-around.** The > 135° turn-around (`0x537B80`) is left as SH4's own.
- **Not done.** Other regions and PC builds; real-hardware testing of the hard-patched ISO; locating the PS2 turn-around routine (not needed, because the camera part feeds the same builder).
