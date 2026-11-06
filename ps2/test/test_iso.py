"""Tests patch_iso.py: the hard-patched executable must behave like the pnach,
load correctly, and be the only thing that changes in the ISO.

Usage:  python3 test_iso.py path/to/SLUS_208.73
(needs: pip install rabbitizer pycdlib)"""
import os, sys, io, math, random, struct, subprocess, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'src')
sys.path.insert(0, HERE); sys.path.insert(0, SRC)
import patch_iso
from ps2sim import Sim, CAMYAW

if len(sys.argv) < 2: sys.exit(__doc__)
ELF = open(sys.argv[1], 'rb').read()
fails = 0
def check(c, msg):
    global fails
    print(('  ok   ' if c else '  FAIL ') + msg); fails += not c
def near(a, b): d = (a - b) % 360; return d < 0.5 or d > 359.5

def segments(elf):
    """What a PS2 ELF loader puts in memory: every PT_LOAD with data."""
    phoff, = struct.unpack_from('<I', elf, 0x1C)
    phentsize, phnum = struct.unpack_from('<HH', elf, 0x2A)
    segs = {}
    for i in range(phnum):
        t, off, vaddr, paddr, filesz, memsz, flags, align = struct.unpack_from('<8I', elf, phoff + i * phentsize)
        if t == 1 and filesz: segs[vaddr] = elf[off:off + filesz]
    return segs

def readelf(path):
    r = subprocess.run(['readelf', '-h', '-l', '-W', path], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

tmp = tempfile.mkdtemp()
try:
    print('1. hard-patched executable (snap turning + camera)')
    P = patch_iso.hardpatch_elf(ELF)
    check(len(P) == len(ELF), 'same size as the original (%d bytes)' % len(P))
    segs = segments(P)
    check(sorted(segs) == [0x000FC000, 0x00100000], 'loads the game at 0x100000 and the routine at 0x000FC000')
    check(len(segs[0x000FC000]) == patch_iso.CAVE_SIZE, 'routine segment is 0x%X bytes' % patch_iso.CAVE_SIZE)
    p = os.path.join(tmp, 'p.elf'); open(p, 'wb').write(P)
    rc, out = readelf(p)
    check(rc == 0 and 'Warning' not in out and 'Error' not in out, 'readelf parses it cleanly')
    check(out.count('LOAD') == 4 and 'There are no sections' in subprocess.run(['readelf', '-S', p], capture_output=True, text=True).stdout,
          '4 program headers, no section table')
    diff = [i for i in range(0, patch_iso.TAIL_OFF, 4) if P[i:i + 4] != ELF[i:i + 4]]
    check(len(diff) == 10 + 3 + 8, 'outside the routine, only the 10 turning/hook words, 3 header fields and the new 8-word program header changed (%d)' % len(diff))
    check(patch_iso.elf_crc(P) != patch_iso.ORIGINAL_CRC, 'new CRC %08X' % patch_iso.elf_crc(P))

    print('2. it plays like the pnach (real input builder, no pnach applied)')
    s = Sim(segs)
    s.camera(0); s.stick(0)
    for i in range(30): s.frame()
    s.stick(90); check(near(s.frame()[0], 90), 'snap turning: 90 deg on the next frame')
    s.stick(0)
    for d in range(0, 61, 3): s.camera(d); s.frame()
    s.camera(60); check(near(s.frame()[1], 60), 'camera pan followed: stick up -> 60')
    s.camera(150); check(near(s.frame()[1], 60), 'camera cut while holding: still 60')
    s.stick(0, 0); s.frame(); s.stick(0); check(near(s.frame()[1], 150), 'released: new camera, 150')
    o = Sim(segments(ELF)); o.camera(0); o.stick(0)
    for i in range(30): o.frame()
    o.stick(90); check(o.frame()[0] < 20, 'unpatched executable still arcs (sanity)')

    print('3. options')
    T = patch_iso.hardpatch_elf(ELF, camera=False)
    check(T[patch_iso.TAIL_OFF:] == ELF[patch_iso.TAIL_OFF:] and T[:0x100] == ELF[:0x100],
          '--no-camera: headers and section table untouched')
    check(sum(T[i:i + 4] != ELF[i:i + 4] for i in range(0, len(T), 4)) == 9, '--no-camera: only the 9 turning words change')
    F = Sim(segments(patch_iso.hardpatch_elf(ELF, turn='fast'))); F.camera(0); F.stick(0)
    for i in range(30): F.frame()
    F.stick(90); t = F.frame()[0]; check(abs(t - 36) < 0.6, '--turn fast: %.1f deg per frame' % t)
    try: patch_iso.hardpatch_elf(P); check(False, 'refuses an already patched executable')
    except ValueError as e: check('already been patched' in str(e), 'refuses an already patched executable')

    print('4. on an ISO: only the executable changes')
    import pycdlib
    iso = pycdlib.PyCdlib(); iso.new(interchange_level=1, sys_ident='PLAYSTATION', vol_ident='SH4_TEST')
    cnf = b'BOOT2 = cdrom0:\\SLUS_208.73;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n'
    random.seed(4); after = bytes(random.getrandbits(8) for _ in range(300000))
    iso.add_fp(io.BytesIO(cnf), len(cnf), '/SYSTEM.CNF;1')
    iso.add_fp(io.BytesIO(ELF), len(ELF), '/SLUS_208.73;1')
    iso.add_fp(io.BytesIO(after), len(after), '/ZZDATA.BIN;1')
    src = os.path.join(tmp, 'game.iso'); iso.write(src); iso.close()
    orig_iso = open(src, 'rb').read()
    r = subprocess.run([sys.executable, os.path.join(SRC, 'patch_iso.py'), src], capture_output=True, text=True)
    out_path = os.path.join(tmp, 'game (Controls2D).iso')
    check(r.returncode == 0 and os.path.exists(out_path), 'patch_iso.py game.iso -> "game (Controls2D).iso"')
    print('     ' + r.stdout.strip().replace('\n', '\n     '))
    new_iso = open(out_path, 'rb').read()
    check(open(src, 'rb').read() == orig_iso, 'original ISO untouched')
    chk = pycdlib.PyCdlib(); chk.open(out_path)
    def get(name):
        b = io.BytesIO(); chk.get_file_from_iso_fp(b, iso_path=name); return b.getvalue()
    check(get('/SLUS_208.73;1') == P, 'the executable on the new ISO is the hard-patched one')
    check(get('/ZZDATA.BIN;1') == after and get('/SYSTEM.CNF;1') == cnf, 'other files intact')
    chk.close()
    off, size = patch_iso.find_in_iso(open(out_path, 'rb'), 'SLUS_208.73')
    changed = [i for i in range(len(new_iso)) if new_iso[i] != orig_iso[i]] if len(new_iso) == len(orig_iso) else None
    check(changed is not None and changed and off <= min(changed) and max(changed) < off + size,
          'every changed byte lies inside the executable (ISO size unchanged)')
    r2 = subprocess.run([sys.executable, os.path.join(SRC, 'patch_iso.py'), out_path, '--in-place'], capture_output=True, text=True)
    check(r2.returncode != 0 and 'already been patched' in r2.stderr, 'running it again on the patched ISO refuses')
finally:
    shutil.rmtree(tmp)

print('\n%s (%d failure%s)' % ('FAILED' if fails else 'ALL PASSED', fails, '' if fails == 1 else 's'))
sys.exit(fails != 0)
