# SH4 Controls2D

Silent Hill 2/3-style "2D" controls for **Silent Hill 4: The Room**, keeping the game's original camera. Available for the **PC (GOG)** release as a plugin and for the **PS2** release (NTSC-U) as a PCSX2 patch.

- **Camera-relative directions.** Up on the stick is always up on the screen, even while the camera pans. SH4 only reads the camera direction when a scene loads, so "up" drifts as the camera moves and jumps when a scene re-initialises. Controls2D recomputes it every frame. On a camera cut while you hold a direction, Henry keeps going the same way until you let go or move the stick more than 30 degrees, which is the rule from Silent Hill 2's own code.
- **Snap turning.** Henry turns straight to the new direction instead of curving round in a wide arc. SH4 steers his walking direction toward the stick at only 360 deg/s while walking and 180 deg/s while running, so a 90-degree change takes 8 and 15 frames while he keeps moving.

| Version | Folder | What you need |
|---|---|---|
| PC (GOG, `SILENT_HILL_4.exe`) | [`pc/`](pc/) | [Zealot's Camera Mod v1.2](https://github.com/zealottormunds/sh4modloader/releases) (provides the plugin loader) |
| PS2 NTSC-U (`SLUS-20873`) | [`ps2/`](ps2/) | PCSX2 |

Ready-to-use files are on the [Releases](../../releases) page.

## Quick install

**PC:** install Zealot's Camera Mod v1.2, then copy `Controls2D.dll` and `Controls2D.ini` into `<SH4 folder>\plugins\`. F3 toggles between Controls2D and SH4's original controls. Leave the camera mod's "Tank Controls" option off. More detail is in [pc/README.md](pc/README.md).

**PS2 / PCSX2:** copy `SLUS-20873_3919136D.pnach` into PCSX2's `patches` folder, then right-click the game, open Properties → Patches and tick the patches you want. More detail is in [ps2/README.md](ps2/README.md).

## How it was made

Everything here comes from reverse-engineering the game executables: SH4's input code on PC and PS2, and Silent Hill 2's 2D control logic for reference. Each version also has tests that run the game's own input code from your copy of the game (natively on PC, and in a small PS2 CPU interpreter for the PS2 version) to check the behaviour frame by frame.

Made by andrewjose, reverse-engineered and written with [Claude](https://claude.ai).

No game files are included; you need your own copy of the game.

## License

[MIT](LICENSE). Silent Hill is a trademark of Konami. This is an unofficial fan project, not affiliated with or endorsed by Konami.
