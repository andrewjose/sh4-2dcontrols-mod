# Controls2D for PS2 (NTSC-U, SLUS-20873): PCSX2 pnach

The PS2 version of Controls2D: Silent Hill 2/3-style "2D" controls with SH4's original camera, as PCSX2 patches.

## Patches

Enable or disable each one in PCSX2:

- **Snap turning.** Henry turns straight to the stick direction instead of curving round to it. SH4 steers his walking direction toward the stick at 360 deg/s walking and 180 deg/s running, so a 90-degree change takes 8 and 15 frames while he keeps moving. This patch makes the change instant and turns his body to face it at about 1430 deg/s (SH4: 690).
- **Snap turning (fast, not instant).** The same, but the direction turns at 1080 deg/s (90 degrees in 3 frames). Use this one *or* Snap turning, not both.
- **Camera-relative directions (SH2 style).** Up on the stick is always up on the screen, even while the camera pans; SH4 only reads the camera direction when a scene loads. On a camera cut while you hold a direction, Henry keeps going the same way until you let go or move the stick more than 30 degrees.

## Install (PCSX2 2.x)

1. Copy [`SLUS-20873_3919136D.pnach`](SLUS-20873_3919136D.pnach) into PCSX2's `patches` folder (Settings → Folders shows where it is).
2. Right-click the game in the game list, open Properties → Patches, and tick the patches you want.
3. The file is named after the game's CRC, `3919136D`. If PCSX2 shows a different CRC for your game, you have a different version and these addresses won't match it.

**PCSX2 1.6:** put the file in the `cheats` folder as `3919136D.pnach` and turn on "Enable Cheats". 1.6 applies every section in the file, so delete the sections you don't want, and keep only one of the two Snap turning sections.

## Building it into your ISO instead

[`src/patch_iso.py`](src/patch_iso.py) writes the mod into the game's executable on your own ISO. The patched copy then works without patches, on a real PS2 (e.g. through OPL) or in any emulator. It needs Python 3, no extra packages, and the pnach next to it, which is where it reads the patches from:

```
python3 src/patch_iso.py "Silent Hill 4.iso"
```

This writes `Silent Hill 4 (Controls2D).iso` and leaves the original alone.

- `--turn fast` uses the 1080 deg/s turning instead of instant, and `--turn off` leaves turning out.
- `--no-camera` leaves out camera-relative directions.
- `--in-place` patches the file itself instead of making a copy; back up first.
- It also accepts an extracted `SLUS_208.73` instead of an ISO.
- It only accepts the original, unmodified game executable (CRC `3919136D`), so it can't double-patch or hit the wrong version.

What it changes:

- **Inside the disc:** only the executable `SLUS_208.73`. Its size and position on the disc stay the same, so nothing else moves.
- **Turning:** the same nine instructions as the pnach.
- **Camera routine:** the executable gets a fourth load segment, so the PS2 itself loads the routine to `0x000FC000` at boot. The segment's bytes take the place of the file's tail, which held only data no loader reads: a compiler comment, `.reginfo`, section names and the section header table. The section table is dropped, which is valid for an executable since loaders use program headers.

The patched executable has a new CRC, which the script prints:

- **This mod's pnach:** keyed to the original CRC, so it won't load on the patched copy. Leave it off there.
- **PCSX2's built-in widescreen patch:** also keyed to the original CRC. To keep using it, copy it into your `patches` folder under the new CRC's name.

Don't share patched ISOs. Share the script; everyone runs it on their own copy.

Tested by running the patched executable's code in the PS2 interpreter with no pnach applied (same turning and camera behaviour as the pnach), and by patching a test ISO and checking that every changed byte lies inside the executable. Not yet run on real hardware. Booting it in PCSX2 with **Fast Boot off** exercises the PS2's own disc loader, which is what loads the extra segment.

## How it works

- **Snap turning** edits nine instructions in place. On PS2 the steering constants are built inside the instructions (`lui`/`ori` pairs at `0x15B794`–`0x15B7B0`, `0x15B208` and `0x1B5A38`).
- **Camera-relative directions** redirects the player update's call to the input builder (`0x1B53C0`) to a small routine at `0x000FC000`, with its data at `0x000FC400` ([`src/cave.S`](src/cave.S)). Each frame the routine:
  1. reads the camera direction (`0x15A1E0`), the left stick (`0x1AAF30`/`0x1AAF90`) and atan2 (`0x121548`);
  2. applies SH2's rule;
  3. writes the result to the camera yaw the builder uses (`0x45A4B0`);
  4. jumps to the builder.

The game never uses memory between `0x80000` and `0xFFFFF`: it loads at `0x100000` and its stack sits at the top of RAM.

## Building and tests

[`src/make_pnach.py`](src/make_pnach.py) assembles `cave.S` (needs `clang` with the MIPS target, or zig) and writes the pnach:

```
python3 src/make_pnach.py --elf path/to/SLUS_208.73
```

`--elf` checks every patched game word against your copy of the game first.

The tests run SH4's real input builder from your `SLUS_208.73` in a small Emotion Engine interpreter ([`test/ee.py`](test/ee.py)), with the pad, camera and atan2 functions stubbed:

```
pip install rabbitizer pycdlib
python3 test/test_ps2.py path/to/SLUS_208.73
python3 test/test_iso.py path/to/SLUS_208.73     # the ISO patcher
```

They cover the following:
- the original game's arcs (12, 24, 36 … 90 degrees over 8 frames walking, 15 frames running) and the patched next-frame turn;
- camera pans and cuts, hold and release, scene re-initialisation, the game's stick inversion and a camera looking straight down;
- that the routine leaves every register the game relies on untouched;
- that the committed pnach matches the source.
