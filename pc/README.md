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

## How SH4 works (from the exe)

**Directions.** SH4's movement is already screen-relative under the hood. The input builder (`0x52F260`) computes *walk direction = stick angle + camera yaw*, with a turn-around when the new direction is more than 135 degrees off (`0x537B80`), which is the same scheme as SH2. The difference is the camera yaw (`0x10A1918`): SH4 only samples it when the player controller initialises for a scene, so within a scene it never follows the camera, and when it is re-sampled the stick's meaning changes instantly.

**SH2's rule** (`sh2pc.exe`, function `0x547FA0`). Camera yaw is recomputed every frame. On a camera change it keeps the previous camera's yaw while the stick is held, and switches once the stick is released or moves more than 30 degrees.

**Turning.** SH4 doesn't point Henry at the stick direction. It steers his walking direction toward it (`0x52FCDB`) at *6π − speed × (4π + run × π)* radians per second: 1080 deg/s standing, 360 deg/s walking and 180 deg/s running. While a turn is in progress it also holds his run at 60%. When the camera looks down steeply, a second stage (`0x52F90D`) limits the turn per frame as well. His body then turns to face the walking direction at 12 rad/s.

## What the plugin changes

- **Directions:** the call to the input builder at `0x534B2E` is redirected through a small stub. The stub applies SH2's rule, writes the result to `0x10A1918`, and continues into the game's own builder.
- **Turning:** six float operands in the steering code are pointed at the plugin's own values: the turn-rate terms, the steep-camera threshold, and the body-facing speed. F3 and unloading put them back.
- **Safety:** before patching, it checks the bytes of every game function it touches and refuses, logging why, on any mismatch.

Everything else (speed, running, turn-arounds, the quick-turn button, the scripted stick inversion) is still SH4's own code.

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
