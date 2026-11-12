# SH4 Controls2D: what this mod does

*Level 1 of 3: plain-language overview. For software engineers: [2-engineering.md](2-engineering.md). For ROM hackers and reverse engineers: [3-technical.md](3-technical.md).*

## The problem

*Silent Hill 4: The Room* uses fixed, cinematic camera angles like Silent Hill 2 and 3. But it handles the controls differently, and many players find it frustrating:

- **"Up" drifts.** When you push up on the stick, Henry walks away from the camera, but only from where the camera was when the area loaded. If the camera then pans to follow him, "up" no longer means "up on the screen." When the game reloads its idea of the camera (for example, going through some doors), the meaning of the stick changes under your thumb, and Henry can suddenly turn around.
- **Wide, slow turns.** When you change direction, Henry doesn't turn to face where you pushed. He curves round in a wide arc, slower the faster he's moving. A right-angle turn while running takes about half a second, which is enough to run into a wall or an enemy.

Silent Hill 2 and 3 don't have these problems. Their "2D" control style always treats the stick as "the direction on screen," and James and Heather turn straight to it.

## What Controls2D changes

- **Camera-relative directions.** Up on the stick is always up on the screen, even while the camera moves.
- **Sensible camera cuts.** When the camera cuts to a new angle while you're holding a direction, Henry keeps walking the same way instead of suddenly changing course. Once you let go, or move the stick a fair amount (more than 30 degrees), the new camera takes over. This is the same rule Silent Hill 2 uses.
- **Snap turning.** Henry turns straight to the direction you push instead of arcing round.

Everything else is unchanged: the camera itself, walking and running speed, the quick-turn button, combat, and the first-person sections in Room 302.

## Two versions

| Version | What you need | How it's installed |
|---|---|---|
| PC (the GOG release) | Zealot's Camera Mod v1.2, which provides the plugin loader | Copy two files into the game's `plugins` folder. F3 switches the mod on and off while you play. |
| PS2 (US release, SLUS-20873) | PCSX2 | Copy one patch file into PCSX2 and tick the patches you want. Or run a script that builds the mod into your own ISO, so it also works on a real PS2. |

On PC you can tune the behaviour in `Controls2D.ini`, such as how fast Henry turns. On PS2 there's a choice between instant turning and fast (but not instant) turning.

Install steps are in the [main README](../README.md), with more detail in [pc/README.md](../pc/README.md) and [ps2/README.md](../ps2/README.md). Ready-made files are on the Releases page.

## How it was checked

The mod was tested by running the game's own movement code (taken from your copy of the game) in a test program and checking frame by frame where Henry goes: during camera pans, during cuts, at scene changes, at a run, and with the camera looking straight down. Both versions passed. The ISO-patching option hasn't been tried on a real PS2 yet.

## Limits

- Only the GOG PC release and the US PS2 release are supported. On any other version, the PC plugin refuses to load (and says why in its log), and the PS2 script refuses to patch.
- On PC, leave the camera mod's "Tank Controls" option off. With the camera mod's free camera turned on, the results may differ, since Controls2D was designed around the game's own cameras.
- A 60 fps fix was tried during development but is not included, because it was buggy.
- No game files are included. You need your own copy of the game.
