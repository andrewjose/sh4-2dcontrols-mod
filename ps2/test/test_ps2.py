"""Tests the PS2 Controls2D patch by running SH4's real input builder from
SLUS_208.73 (and the hand-written cave) in the EE interpreter.

Usage:  python3 test_ps2.py path/to/SLUS_208.73
(needs: pip install rabbitizer; clang or zig to assemble the cave)"""
import os, sys, math, struct, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
import make_pnach
from ps2sim import Sim as _Sim, CAMYAW, FLIP, PLAYER
from ee import f2b

if len(sys.argv) < 2: sys.exit(__doc__)
SEGS = make_pnach.load_elf(sys.argv[1])
P = make_pnach.patches()
def Sim(patch=()): return _Sim(SEGS, patch)
fails = 0
def check(c, msg):
    global fails
    print(('  ok   ' if c else '  FAIL ') + msg)
    fails += not c
def near(a, b): d = (a - b) % 360; return d < 0.5 or d > 359.5
def words(p): return [(a, new) for a, orig, new, what in p]

print('0. every patched word matches the original game')
check(make_pnach.check_against(sys.argv[1], P), 'original bytes at all %d patched game addresses' % len(
    [1 for a, o, n, w in P['turn'] + P['camera'] if o is not None]))
cave_range = [a for a, o, n, w in P['camera'] if o is None]
check(all(a < 0x100000 for a in cave_range), 'cave and its data lie below the game (0x%X-0x%X)' % (min(cave_range), max(cave_range)))

print('1. camera part: fixed camera, same as SH4 (up = away from the camera)')
s = Sim(words(P['camera']))
s.camera(0); s.stick(0)
check(near(s.frame()[1], 0), 'camera 0, stick up -> target 0')
s.stick(90); check(near(s.frame()[1], 90), 'stick right -> 90')

print('2. camera pans while walking: direction follows the screen')
s.stick(0)
for d in range(0, 61, 3): s.camera(d); s.frame()
s.camera(60); t = s.frame()[1]
check(near(t, 60), 'after a smooth 60 deg pan, stick up -> %.1f (game alone: 0)' % t)

print('3. camera cut while holding the stick: keep going the same way')
s.camera(150); check(near(s.frame()[1], 60), 'cut to 150: still 60')
s.camera(155); check(near(s.frame()[1], 60), 'camera keeps moving: still 60')
s.stick(20); check(near(s.frame()[1], 80), 'stick nudged 20 (< 30): relative to the old camera -> 80')
s.stick(40); t = s.frame()[1]; check(near(t, 195), 'stick moved 40 (> 30): new camera takes over -> %.1f (155+40)' % t)

print('4. release after a cut hands over to the new camera')
s.stick(0); s.camera(155); s.frame()
s.camera(245); check(near(s.frame()[1], 155), 'cut to 245 while holding: held at 155')
s.stick(0, 0); s.frame()
s.stick(0); check(near(s.frame()[1], 245), 'released and pushed again: 245')

print('5. the game re-initialises its yaw (new scene) while holding: treated as a cut')
s.cpu.wf(CAMYAW, 1.0)
check(near(s.frame()[1], 245), 'held through the re-init')

print('6. scene stick inversion still honoured')
s.cpu.w32(FLIP, 1); s.camera(0); s.stick(0); s.frame(); s.stick(0, 0); s.frame(); s.stick(0)
t = s.frame()[1]; check(near(t, 180), 'inverted scene: stick up -> %.1f' % t)
s.cpu.w32(FLIP, 0)

print('7. camera looking straight down: leaves the yaw alone')
s.camera(10); s.stick(0); s.frame()
before = s.cpu.r32(CAMYAW)
fwd = s.cpu.stubs[0x15A1E0]
s.cpu.stubs[0x15A1E0] = lambda cpu: [cpu.wf((cpu.g(4) & 0xffffffff) + 4 * i, v) for i, v in enumerate((0.0, -1.0, 0.0, 0.0))]
s.frame(); check(s.cpu.r32(CAMYAW) == before, 'yaw unchanged')
s.cpu.stubs[0x15A1E0] = fwd

print('8. register discipline (the game must not notice the detour)')
s2 = Sim(words(P['camera']))
c = s2.cpu
import random
random.seed(1)
saved = {}
for r in list(range(16, 24)) + [28, 29, 30]:
    v = random.getrandbits(64) if r not in (28, 29) else c.gpr[r]
    c.gpr[r] = v; saved[r] = v
fsaved = {r: f2b(random.uniform(-9, 9)) for r in range(20, 32)}
for r, v in fsaved.items(): c.fpr[r] = v
s2.camera(30); s2.stick(45)
c.sg(31, 0x1B53C8)
c.pc = 0x1B53C0; c.npc = 0x1B53C4
c.step(); c.step()                            # the patched jal + its delay slot
check(c.pc == 0x000FC000, 'player update now enters the cave')
n = 0
while c.pc != 0x15AA70 and n < 5000:
    if c.pc in c.stubs:                       # run helper stubs like a call would
        c.stubs[c.pc](c); c.pc = c.g(31) & 0xffffffff; c.npc = c.pc + 4
    else:
        c.step(); n += 1
check(c.pc == 0x15AA70, 'cave ends by jumping to the builder (%d instructions)' % n)
check(c.g(31) == 0x1B53C8, 'with the original return address')
check(all(c.gpr[r] == v for r, v in saved.items()), 's0-s7, gp, sp, fp untouched')
check(all(c.fpr[r] == v for r, v in fsaved.items()), 'f20-f31 untouched')

print('9. turning part: no arcs')
for label, patch in (('SH4 original', []), ('patched', words(P['turn']))):
    s = Sim(patch)
    s.cpu.stubs[0x1AAC10] = lambda cpu: cpu.sg(2, 1 if (cpu.g(5) & 0xffffffff) == 1 else 0)  # hold run
    s.camera(0); s.stick(0)
    for i in range(40): s.frame()
    s.stick(90); seq = [s.frame()[0] for _ in range(15)]
    print('     %-12s running, stick up -> right: %s' % (label, ' '.join('%.0f' % x for x in seq)))
    if patch: check(near(seq[0], 90), 'patched: 90 on the next frame')
    else: check(seq[0] < 10 and not near(seq[10], 90), 'original: 6 deg per frame while running')
s = Sim(words(P['turn_fast']))
s.camera(0); s.stick(0)
for i in range(40): s.frame()
s.stick(90); t = s.frame()[0]
check(abs(t - 36) < 0.6, '"1080 deg/s" variant: %.1f deg per frame (36 at 30 fps)' % t)

print('10. both parts together')
s = Sim(words(P['turn']) + words(P['camera']))
s.camera(0); s.stick(0)
for i in range(20): s.frame()
s.camera(40); s.stick(0)
for i in range(3): s.frame()
s.stick(90); d = s.frame()[0]
check(near(d, 130), 'camera panned to 40, stick right -> walking %.1f at once (40+90)' % d)

print('11. the committed pnach file is exactly what this source builds')
committed = open(make_pnach.PNACH, newline='').read()
check(committed == make_pnach.pnach_text(P), os.path.basename(make_pnach.PNACH) + ' is up to date')
secs, cur = {}, None
for line in committed.splitlines():
    m = re.match(r'\[(.*)\]$', line)
    if m: cur = m.group(1); secs[cur] = []; continue
    m = re.match(r'patch=1,EE,([0-9A-F]{8}),word,([0-9A-F]{8})$', line)
    if m: secs[cur].append((int(m.group(1), 16), int(m.group(2), 16)))
s = Sim(secs['Snap turning'] + secs['Camera-relative directions (SH2 style)'])
s.camera(0); s.stick(0)
for i in range(20): s.frame()
for d in range(0, 61, 3): s.camera(d); s.frame()
s.stick(90); d = s.frame()[0]
check(near(d, 150), 'applied from the file: after a 60 deg pan, stick right walks %.1f at once' % d)

print('\n%s (%d failure%s)' % ('FAILED' if fails else 'ALL PASSED', fails, '' if fails == 1 else 's'))
sys.exit(fails != 0)
