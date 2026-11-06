#!/usr/bin/env python3
"""Builds SH4 Controls2D into your Silent Hill 4 (NTSC-U, SLUS-20873) ISO, so it
works without PCSX2 patches: on a real PS2, or in any emulator.

    python3 patch_iso.py "Silent Hill 4.iso"                  # writes "Silent Hill 4 (Controls2D).iso"
    python3 patch_iso.py "Silent Hill 4.iso" out.iso
    python3 patch_iso.py "Silent Hill 4.iso" --in-place       # no copy (back up first)
    python3 patch_iso.py SLUS_208.73 SLUS_208.73.patched      # an extracted executable works too

Options: --turn instant|fast|off  (default instant), --no-camera.

It reads the patches from SLUS-20873_3919136D.pnach (keep the two files together)
and changes only the game executable's own bytes inside the ISO; its size and
position stay the same, so nothing else on the disc moves. Python 3, no extra
packages. Only the original, unmodified executable is accepted (ELF CRC 3919136D).
"""
import os, re, sys, shutil, struct, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
PNACH_CANDIDATES = [os.path.join(HERE, 'SLUS-20873_3919136D.pnach'),
                    os.path.join(os.path.dirname(HERE), 'SLUS-20873_3919136D.pnach')]
ELF_NAME = 'SLUS_208.73'
ORIGINAL_CRC = 0x3919136D
SECTOR = 2048

# Layout of the original executable (checked by the CRC above)
MAIN_VADDR, MAIN_OFF, MAIN_SIZE = 0x00100000, 0x100, 0x2C9B80
TAIL_OFF = MAIN_OFF + MAIN_SIZE         # .comment/.reginfo/.shstrtab/section headers: never loaded
CAVE_VADDR, CAVE_SIZE = 0x000FC000, 0x480
GROUPS = {'turn_instant': 'Snap turning',
          'turn_fast': 'Snap turning (fast, not instant)',
          'camera': 'Camera-relative directions (SH2 style)'}


def elf_crc(d):
    """The CRC PCSX2 identifies games by: XOR of the ELF's 32-bit words."""
    c = 0
    for (w,) in struct.iter_unpack('<I', d[:len(d) // 4 * 4]): c ^= w
    return c


def read_pnach(path):
    groups, cur = {}, None
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        m = re.match(r'\[(.*)\]$', line)
        if m: cur = m.group(1); groups[cur] = []; continue
        m = re.match(r'patch=\d,EE,([0-9A-Fa-f]{8}),word,([0-9A-Fa-f]{8})', line)
        if m and cur: groups[cur].append((int(m.group(1), 16), int(m.group(2), 16)))
    return groups


def hardpatch_elf(elf, turn='instant', camera=True, pnach=None):
    """Returns the patched executable (same size as the original)."""
    if elf[:4] != b'\x7fELF': raise ValueError('not an ELF file')
    crc = elf_crc(elf)
    if crc != ORIGINAL_CRC:
        raise ValueError('this executable has CRC %08X, not %08X: it is a different version of the game, '
                         'or it has already been patched' % (crc, ORIGINAL_CRC))
    if pnach is None:
        pnach = next((p for p in PNACH_CANDIDATES if os.path.exists(p)), None)
        if not pnach: raise FileNotFoundError('SLUS-20873_3919136D.pnach not found next to this script')
    groups = read_pnach(pnach)
    words = []
    if turn == 'instant': words += groups[GROUPS['turn_instant']]
    elif turn == 'fast': words += groups[GROUPS['turn_fast']]
    if camera: words += groups[GROUPS['camera']]
    if not words: raise ValueError('nothing to patch')

    d = bytearray(elf)
    cave = bytearray(CAVE_SIZE)
    for addr, val in words:
        if MAIN_VADDR <= addr < MAIN_VADDR + MAIN_SIZE:
            off = addr - MAIN_VADDR + MAIN_OFF
            struct.pack_into('<I', d, off, val)
        elif CAVE_VADDR <= addr < CAVE_VADDR + CAVE_SIZE:
            struct.pack_into('<I', cave, addr - CAVE_VADDR, val)
        else:
            raise ValueError('patch address %08X is outside the executable and the routine area' % addr)

    if camera:
        # The routine is loaded by a 4th program header from the executable's
        # tail, which held only data the loader ignores (compiler comment,
        # .reginfo, section names and section headers). The section header table
        # is removed (allowed for an executable; loaders use program headers).
        assert len(d) - TAIL_OFF >= CAVE_SIZE
        d[TAIL_OFF:] = bytes(cave) + bytes(len(d) - TAIL_OFF - CAVE_SIZE)
        phoff, = struct.unpack_from('<I', d, 0x1C)
        phentsize, phnum = struct.unpack_from('<HH', d, 0x2A)
        new = phoff + phnum * phentsize
        assert phnum == 3 and new + phentsize <= MAIN_OFF and not any(d[new:new + phentsize])
        struct.pack_into('<8I', d, new, 1, TAIL_OFF, CAVE_VADDR, CAVE_VADDR, CAVE_SIZE, CAVE_SIZE, 7, 0x80)
        struct.pack_into('<H', d, 0x2C, phnum + 1)          # e_phnum
        struct.pack_into('<I', d, 0x20, 0)                  # e_shoff
        struct.pack_into('<HH', d, 0x30, 0, 0)              # e_shnum, e_shstrndx
    assert len(d) == len(elf)
    return bytes(d)


def find_in_iso(f, name):
    """(byte offset, size) of a file in the ISO 9660 root directory."""
    f.seek(16 * SECTOR)
    pvd = f.read(SECTOR)
    if pvd[1:6] != b'CD001' or pvd[0] != 1: raise ValueError('not an ISO 9660 image (is it a .bin/.chd/.cso? convert to .iso first)')
    root_lba, root_len = struct.unpack_from('<I', pvd, 156 + 2)[0], struct.unpack_from('<I', pvd, 156 + 10)[0]
    f.seek(root_lba * SECTOR)
    data = f.read(root_len)
    pos = 0
    while pos < len(data):
        n = data[pos]
        if n == 0:                                  # records don't cross sectors
            pos = (pos // SECTOR + 1) * SECTOR; continue
        lba, size = struct.unpack_from('<I', data, pos + 2)[0], struct.unpack_from('<I', data, pos + 10)[0]
        ident = data[pos + 33:pos + 33 + data[pos + 32]].decode('latin1').split(';')[0]
        if ident.upper() == name.upper(): return lba * SECTOR, size
        pos += n
    raise ValueError('%s is not on this disc image (wrong game or region?)' % name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input', help='your Silent Hill 4 ISO, or an extracted SLUS_208.73')
    ap.add_argument('output', nargs='?', help='where to write the patched copy')
    ap.add_argument('--in-place', action='store_true', help='patch the input itself instead of a copy')
    ap.add_argument('--turn', choices=['instant', 'fast', 'off'], default='instant')
    ap.add_argument('--no-camera', action='store_true', help='leave out camera-relative directions')
    a = ap.parse_args()

    with open(a.input, 'rb') as f:
        is_elf = f.read(4) == b'\x7fELF'
        if is_elf:
            off, size = 0, os.path.getsize(a.input)
        else:
            off, size = find_in_iso(f, ELF_NAME)
        f.seek(off)
        elf = f.read(size)
    patched = hardpatch_elf(elf, a.turn, not a.no_camera)

    if a.in_place:
        out = a.input
    else:
        out = a.output or ('%s (Controls2D)%s' % os.path.splitext(a.input) if not is_elf else a.input + '.patched')
        if os.path.abspath(out) == os.path.abspath(a.input): sys.exit('output is the input; use --in-place')
        print('copying %s -> %s ...' % (a.input, out))
        shutil.copyfile(a.input, out)
    with open(out, 'r+b') as f:
        f.seek(off)
        f.write(patched)
    with open(out, 'rb') as f:
        f.seek(off)
        assert f.read(size) == patched

    print('done: %s' % out)
    print('patched executable CRC: %08X (original %08X)' % (elf_crc(patched), ORIGINAL_CRC))
    print('Turn the Controls2D pnach off for this copy (it is keyed to the original CRC anyway).')
    print("PCSX2's built-in widescreen patch is keyed to the original CRC too; to keep using it, copy it to")
    print('SLUS-20873_%08X.pnach in your patches folder.' % elf_crc(patched))


if __name__ == '__main__':
    main()
