# Controls2D for PC (GOG)

A plugin for Zealot's SH4 mod loader that gives Silent Hill 4 SH2/SH3-style "2D" movement. Push the stick (or WASD) toward a direction on screen and Henry walks that way, even while the camera moves.

It works with a gamepad and with the keyboard; SH4's keyboard emulates the stick, so W/A/S/D are directions, not turns. First-person sections (Room 302) are unaffected.

## Install

1. Install [Zealot's Camera Mod v1.2](https://github.com/zealottormunds/sh4modloader/releases), which provides the plugin loader.
2. Copy `Controls2D.dll` and `Controls2D.ini` into `<SH4 folder>\plugins\`.
3. F3 toggles between Controls2D and SH4's original behaviour (with a beep).

Leave the camera mod's "Tank Controls" option off, since the two would fight. Controls2D is designed around SH4's own cameras; with the camera mod's custom camera enabled, results may differ.

## Settings (`plugins\Controls2D.ini`)

| Key | Meaning |
|---|---|
| `enabled` | 1 = on at startup |
| `toggle_key` | virtual-key code of the toggle, `0x72` = F3 |
| `hold_on_cut` | 1 = SH2 behaviour on camera cuts, 0 = switch to the new camera at once |
| `release_angle` | stick change (degrees) that ends the hold; SH2 uses 30 |
| `cut_angle` | camera turn in one frame that counts as a cut (degrees) |
| `snap_turn` | 1 = snap turning, 0 = SH4's arcs |
| `turn_speed` | how fast the walking direction turns, deg/s; 0 = instantly |
| `facing_speed` | how fast Henry's body turns to face it, deg/s; 0 = SH4's 690 |
| `deadzone` | stick dead zone |
| `verbose_log` | 1 = log every cut and release |

The log (`plugins\Controls2D.log`) records the code checks, camera cuts, scene re-initialisations and toggles.

## How it works

In short: the plugin hooks the game's only call to its input builder and recomputes, every frame, the camera yaw that SH4 otherwise samples only at scene start. It applies Silent Hill 2's rule on camera cuts and points six steering-constant operands at its own values for snap turning. It checks every byte it touches first, and F3 or unloading puts them back.

Explanations: [docs/2-engineering.md](../docs/2-engineering.md) (concepts) and [docs/3-technical.md](../docs/3-technical.md) (addresses, operand table, per-frame logic).

## Building and tests

Build with [zig](https://ziglang.org) (or `pip install ziglang` and use `python3 -m ziglang cc`):

```
zig cc -target x86-windows-gnu -shared -O2 -s -mstackrealign -o Controls2D.dll controls2d.c controls2d.def -luser32
```

The tests run the game's real input builder from your own `SILENT_HILL_4.exe` inside a 32-bit Linux process:

```
python3 -c "import pefile,sys;open(sys.argv[2],'wb').write(pefile.PE(sys.argv[1]).get_memory_mapped_image())" SILENT_HILL_4.exe sh4_image.bin
cd test && zig cc -target x86-linux-musl -D_GNU_SOURCE -mstackrealign -O1 -I inc -o harness harness.c && ./harness ../sh4_image.bin
```
