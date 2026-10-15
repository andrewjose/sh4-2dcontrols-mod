#!/usr/bin/env python3
"""Builds ../SLUS-20873_3919136D.pnach.

Assembles cave.S (needs clang with the MIPS target, or zig), then writes the
pnach with three patch groups. Run:  python3 make_pnach.py
Optionally pass --elf path/to/SLUS_208.73 to check every patched game word
against your copy of the game first."""
import os, sys, math, shutil, struct, subprocess, tempfile, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
PNACH = os.path.join(os.path.dirname(HERE), 'SLUS-20873_3919136D.pnach')
CAVE, DATA = 0x000FC000, 0x000FC400
AUTHOR = 'andrewjose (made with Claude)'

def fbits(x): return struct.unpack('<I', struct.pack('<f', x))[0]

def elf_section(obj, name):
    """Bytes of one section of a little-endian ELF32 object file."""
    shoff, = struct.unpack_from('<I', obj, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', obj, 0x2E)
    secs = [struct.unpack_from('<IIIIIIIIII', obj, shoff + i * shentsize) for i in range(shnum)]
    strtab = secs[shstrndx]
    for s in secs:
        n = obj[strtab[4] + s[0]:obj.index(b'\0', strtab[4] + s[0])].decode()
        if n == name: return obj[s[4]:s[4] + s[5]]
    raise KeyError(name)

def assemble_cave():
    src = os.path.join(HERE, 'cave.S')
    if shutil.which('clang'): cc = ['clang', '--target=mipsel-unknown-none-elf']
    elif shutil.which('zig'): cc = ['zig', 'cc', '-target', 'mipsel-freestanding-none']
    else: cc = [sys.executable, '-m', 'ziglang', 'cc', '-target', 'mipsel-freestanding-none']
    with tempfile.TemporaryDirectory() as d:
        obj = os.path.join(d, 'cave.o')
        subprocess.run(cc + ['-mcpu=mips2', '-c', src, '-o', obj], check=True)
        code = elf_section(open(obj, 'rb').read(), '.text')
    words = struct.unpack('<%dI' % (len(code) // 4), code)
    assert len(code) <= DATA - CAVE, 'cave overruns its data block'
    # The EE FPU only has C.F/C.EQ/C.LT/C.LE (funct 0x30/32/34/36)
    for w in words:
        if (w >> 26) == 0x11 and ((w >> 21) & 31) == 0x10 and (w & 0x30) == 0x30:
            assert (w & 0x3f) in (0x30, 0x32, 0x34, 0x36), 'FPU compare %08x does not exist on the EE' % w
    return words

def turning(rate_rad_s, facing_rad_s):
    """(address, original word, new word, note). The steering constants are
    built inline with lui/ori in the input builder (0x15AA70)."""
    def luiori(a_lui, w_lui, a_ori, w_ori, val, what):
        b = fbits(val)
        return [(a_lui, w_lui, (w_lui & 0xffff0000) | (b >> 16), what),
                (a_ori, w_ori, (w_ori & 0xffff0000) | (b & 0xffff), what)]
    p = []
    p += luiori(0x15B794, 0x3c024049, 0x15B79C, 0x34420fdb, 0.0, 'turn rate: no slow-down while running (pi -> 0)')
    p += luiori(0x15B7A4, 0x3c0340c9, 0x15B7A8, 0x34630fdb, rate_rad_s, 'turn rate at speed (2pi -> new rate)')
    p += luiori(0x15B7AC, 0x3c024196, 0x15B7B0, 0x3442cbe4, rate_rad_s, 'turn rate standing (6pi -> new rate)')
    p += luiori(0x15B208, 0x3c023f73, 0x15B20C, 0x34423333, -1.0, 'steep cameras: use the stick direction directly (0.95 -> -1)')
    fb = fbits(facing_rad_s)
    assert fb & 0xffff == 0, 'facing speed must have a zero low half (single lui)'
    p.append((0x1B5A38, 0x3c024140, 0x3c020000 | (fb >> 16), 'body facing speed (12 -> 25 rad/s)'))
    return p

def camera(cave_words):
    p = [(CAVE + 4 * i, None, w, 'code cave (src/cave.S)') for i, w in enumerate(cave_words)]
    k = [(0x60, fbits(math.pi)), (0x64, fbits(2 * math.pi)), (0x68, fbits(math.radians(20))),
         (0x6C, fbits(math.radians(30))), (0x70, fbits(0.01)), (0x74, fbits(1e-8)), (0x78, 0x53483244)]
    p += [(DATA + o, None, v, 'cave constants') for o, v in k]
    p.append((0x1B53C0, 0x0c056a9c, 0x0C000000 | (CAVE >> 2), 'player update: call the cave instead of the builder'))
    return p

def patches():
    return {'turn': turning(1.0e6, 25.0),
            'turn_fast': turning(6 * math.pi, 25.0),
            'camera': camera(assemble_cave())}

def pnach_text(P):
    def lines(p):
        out, last = [], None
        for a, orig, new, what in p:
            if what != last: out.append('// ' + what); last = what
            out.append('patch=1,EE,%08X,word,%08X' % (a, new))
        return out
    L = ['gametitle=Silent Hill 4: The Room (NTSC-U) [SLUS-20873]',
         'comment=SH4 Controls2D: Silent Hill 2/3-style "2D" controls with the original camera. Enable the patches you want in Game Properties > Patches.',
         '',
         '// https://github.com/andrewjose/sh4-2dcontrols-mod  (MIT license)',
         '// Built for SLUS_208.73 (ELF CRC 3919136D). Every game address patched here was checked',
         '// against that executable; on any other version these lines would corrupt code.',
         '',
         '[Snap turning]',
         'author=' + AUTHOR,
         'description=Henry turns straight to the stick direction instead of curving round in a wide arc. SH4 steers at 360 deg/s walking and 180 deg/s running; this makes it instant and turns his body at about 1430 deg/s.']
    L += lines(P['turn'])
    L += ['', '[Snap turning (fast, not instant)]', 'author=' + AUTHOR,
          'description=Same as Snap turning but the walking direction turns at 1080 deg/s (90 degrees in about 3 frames). Enable this OR Snap turning, not both.']
    L += lines(P['turn_fast'])
    L += ['', '[Camera-relative directions (SH2 style)]', 'author=' + AUTHOR,
          'description=Up on the stick always means up on the screen, even while the camera pans. On a camera cut, Henry keeps going the same way until you let go or move the stick more than 30 degrees (Silent Hill 2 rule). Uses a small routine at 0x000FC000.']
    L += lines(P['camera'])
    return '\r\n'.join(L) + '\r\n'

def load_elf(path):
    """{vaddr: bytes} for every loadable segment of a PS2 ELF."""
    d = open(path, 'rb').read()
    phoff, = struct.unpack_from('<I', d, 0x1C)
    phentsize, phnum = struct.unpack_from('<HH', d, 0x2A)
    segs = {}
    for i in range(phnum):
        ptype, off, vaddr, paddr, filesz = struct.unpack_from('<IIIII', d, phoff + i * phentsize)
        if ptype == 1 and filesz: segs[vaddr] = d[off:off + filesz]
    return segs

def check_against(elf, P):
    segs = load_elf(elf)
    def word(a):
        for v, b in segs.items():
            if v <= a < v + len(b): return struct.unpack_from('<I', b, a - v)[0]
    bad = [(a, orig, word(a)) for g in P.values() for a, orig, new, w in g if orig is not None and word(a) != orig]
    for a, o, w in bad: print('MISMATCH at %08X: expected %08X, your game has %s' % (a, o, '%08X' % w if w is not None else 'nothing'))
    return not bad

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', help='your SLUS_208.73, to check the patched addresses against it')
    args = ap.parse_args()
    P = patches()
    if args.elf and not check_against(args.elf, P): sys.exit('not writing the pnach: this is a different game version')
    open(PNACH, 'w', newline='').write(pnach_text(P))
    print('wrote', PNACH, '(%d patch lines)' % sum(len(v) for v in P.values()))
