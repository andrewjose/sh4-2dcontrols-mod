# How SH4 Controls2D works

*Level 2 of 3: for software engineers who don't know game development or reverse engineering. The plain overview is [1-overview.md](1-overview.md). Exact addresses, byte patterns and test coverage are in [3-technical.md](3-technical.md).*

## The starting point

There's no source code for Silent Hill 4. What we have is the shipped program: a 32-bit Windows `.exe` on PC and a MIPS executable (`SLUS_208.73`) on the PS2 disc. Every change is made by patching the compiled machine code. Think of it as fixing a bug in a stripped, statically linked binary with no symbols and no compiler.

The work came down to four problems: understand what the game does, decide what it should do, get new code into the running game, and test it without playing for hours.

## 1. Understanding the game's movement code

We read the executables in a disassembler (a tool that turns machine code back into readable assembly instructions) and traced from the controller-reading functions to the code that moves Henry. On PC, the "input builder" runs once per frame. It turns the stick position into a target walking direction:

```
target_direction = angle_of_stick + camera_yaw
```

This is already the right formula for screen-relative controls. The bug is in `camera_yaw`, a single global variable. The game fills it in only when the player controller is initialised for a scene, so it's a stale cached value: a cache that's never invalidated while the camera moves, then refreshed all at once at a scene change.

The arcing turns come from a second piece of code. It doesn't set Henry's direction to the target. Instead it rotates his direction toward the target at a limited rate, and that rate gets lower the faster he moves. It works like a rate limiter or a low-pass filter on the direction.

For reference, we also read Silent Hill 2's executable to find its version of this logic. SH2 recomputes the camera yaw every frame and has a specific rule for camera cuts, which we copied.

## 2. Deciding the new behaviour

Each frame, Controls2D:

1. reads the camera's current forward direction and computes its yaw (the same way the game does);
2. detects a camera *cut*: the yaw jumping by more than 20 degrees in a single frame, or the game overwriting the cached value itself (a scene change);
3. on a cut while the stick is held, keeps using the old yaw ("latches" it), until the stick is released or moves more than 30 degrees from where it was at the cut;
4. otherwise uses the live camera yaw;
5. writes the result into the game's `camera_yaw` variable, right before the input builder reads it.

This is a small state machine (following, latched) with hysteresis, the same idea as a debounced switch. The latch exists because the player's thumb is still pointing for the old camera when a cut happens. Switching instantly would send Henry back the way he came.

For turning, we don't rewrite the steering code. It's still the game's own code. We only change the constants it reads: the turn rate becomes very high (effectively instant), and the slow-down at running speed becomes zero. Speed, the running cap, turn-arounds and everything else still go through the original logic.

## 3. Getting new code into the game

### PC: a plugin with a function hook

Zealot's Camera Mod includes a plugin loader: it loads DLLs from the `plugins` folder into the game's process and calls their exported functions (`LoadPlugin`, then `Update` every frame, then `UnloadPlugin`). Controls2D is one of those DLLs, written in C.

Once loaded, it installs a *hook*. The game has exactly one call to the input builder. The plugin overwrites the 5-byte `call` instruction there so it calls a tiny stub instead. The stub calls the plugin's C function and then jumps on into the real input builder. To the game, it looks like the original call. This is the same technique as monkey-patching a method, done at the machine-code level.

The turning constants are changed differently. Each x87 floating-point instruction that reads one of them contains the constant's address as an operand. The plugin rewrites just that operand so the instruction reads the plugin's own variable instead. Pressing F3 or unloading the plugin puts the original bytes back, so the toggle is cheap and fully reversible.

Before touching anything, the plugin compares the bytes at every address it will patch with what it expects. If any differ (a different game build, or another mod already patched it), it refuses and writes the reason to its log. Patching the wrong bytes in a running process would crash it, or worse, corrupt it quietly.

### PS2: a cheat file and a code cave

PCSX2 (the PS2 emulator) supports `.pnach` files: lists of "write this 32-bit value to this memory address," applied while the game runs. Think of it as a declarative patch file.

- **Turning** is nine instruction words. On MIPS, a float constant is often built inside the instructions themselves: one instruction loads the upper 16 bits, the next ORs in the lower 16. So changing a constant means rewriting those two instructions.
- **Camera-relative directions** need real new code, written in MIPS assembly. It needs somewhere to live. We found a block of RAM (`0x80000`–`0xFFFFF`) that the game never uses: its program loads above it and its stack sits at the top of memory. Unused space like this is called a *code cave*. The pnach writes the routine there and redirects the game's call to the input builder through it, just like the PC hook.

The routine has to be invisible to the game. MIPS has a calling convention: some registers belong to the caller and must come back unchanged. The routine uses only scratch registers, saves its return address in its own data block, and ends by jumping to the builder, so the builder returns straight to the game's original caller.

### PS2 without the emulator: patching the executable on the disc

A pnach only works in an emulator that supports it. For a real PS2, `patch_iso.py` writes the same changes into the game's executable on your ISO. The nine turning words are simple in-place edits. The code cave is harder: on a real console, nothing writes it into RAM for us.

The solution is to add a fourth *load segment* to the executable. An ELF file has a table of program headers that tells the loader "copy these bytes from the file to this memory address at boot." We add an entry for the cave's address, so the PS2's own loader puts the routine in RAM. To keep the file the same size (so nothing else on the disc has to move), the new segment's bytes replace the end of the file. That area only held data no loader reads: a compiler comment, debug section names, and the section header table.

## 4. Testing without playing

You can't unit-test a 2004 console game in the usual way, so we built harnesses that run the game's real code:

- **PC.** A small test program maps your `SILENT_HILL_4.exe` into memory at the address Windows would load it, then calls the real input builder each "frame" with a fake camera and stick. It compiles the plugin's actual C source in. The tests check the direction the game itself computes. It runs on Linux because the game's input builder is plain 32-bit x86 math. It barely touches Windows, and the few Windows calls it makes are stubbed.
- **PS2.** We wrote a small interpreter for the PS2's main CPU (the Emotion Engine, a MIPS variant) in Python. It runs the game's real input builder and our code cave from your copy of `SLUS_208.73`, with the controller, camera and `atan2` functions replaced by stubs that return test values.

The scenarios cover: a fixed camera (which should behave exactly like the original game), pans, cuts, hold and release, scene changes, the one scripted scene where the game deliberately inverts the stick, and a camera looking straight down. The PS2 tests also check that the routine leaves every register the game relies on untouched, and that the committed pnach file is exactly what the source builds. A separate test patches an ISO and checks that every changed byte lies inside the executable.

## Trade-offs

- **Reuse the game's code wherever possible.** Controls2D changes one input (the camera yaw) and a few constants, and the game does the rest. That keeps speed, animations, turn-arounds and scripted events behaving as they always did. The cost is that the turning behaviour is limited to what the original steering code can do with different constants.
- **Exact version matching.** Both versions are tied to one specific build of the game, and they refuse to run on anything else. That's deliberate, since patching by address on an unknown build would crash or corrupt the game.
- **The cave on PS2 depends on a static argument.** The game's code, data and stack layout show it never uses that RAM range. Testing in PCSX2 agrees, but nobody has run it on a real PS2 yet.
