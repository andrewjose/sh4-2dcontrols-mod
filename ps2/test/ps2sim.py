"""Runs SH4 PS2's real third-person input builder (0x15AA70) frame by frame in
the EE interpreter, with the pad/camera/atan2 leaf functions stubbed."""
import math
from ee import EE, f2b, b2f

PLAYER = 0x01800000
CAMYAW, HFACT, FLIP = 0x45A4B0, 0x45A4A8, 0x45A488
INPUT = 0x45A4C0               # input+0 speed, +8 walking dir, +0x70 target
STEER = 0x45A418               # steered direction state
BUILDER, CALLSITE = 0x15AA70, 0x1B53C0

class Sim:
    def __init__(self, segments, patches=()):
        self.cpu = c = EE(segments)
        self.lx = self.ly = 0.0
        self.cam = 0.0
        for a, v in patches: c.w32(a, v)
        c.w32(0x45AF10, PLAYER)         # player controller pointer
        c.w32(0x45AF14, 1)              # third person
        c.wf(HFACT, 1.0)
        c.gpr[29] = 0x01F00000          # sp
        c.gpr[28] = 0x3D1A70            # gp
        def ret_f0(v):
            def f(cpu): cpu.sf(0, v())
            return f
        def ret_v0(v):
            def f(cpu): cpu.sg(2, v)
            return f
        c.stubs[0x1AAF30] = ret_f0(lambda: self.lx)
        c.stubs[0x1AAF90] = ret_f0(lambda: self.ly)
        c.stubs[0x1AAFF0] = ret_f0(lambda: 0.0)
        c.stubs[0x1AB050] = ret_f0(lambda: 0.0)
        c.stubs[0x1AAC10] = ret_v0(0)
        c.stubs[0x1AACC0] = ret_v0(0)
        def memset(cpu):
            a, v, n = cpu.g(4) & 0xffffffff, cpu.g(5) & 0xff, cpu.g(6) & 0xffffffff
            cpu.mem[a:a + n] = bytes([v]) * n; cpu.sg(2, a)
        c.stubs[0x125358] = memset
        self.atan2_calls = 0
        def atan2(cpu):
            self.atan2_calls += 1
            cpu.sf(0, math.atan2(cpu.f(12), cpu.f(13)))
        c.stubs[0x121548] = atan2
        def camfwd(cpu):
            out = cpu.g(4) & 0xffffffff
            for i, v in enumerate((math.sin(self.cam), 0.0, math.cos(self.cam), 0.0)): cpu.wf(out + 4 * i, v)
        c.stubs[0x15A1E0] = camfwd

    def stick(self, deg, mag=1.0):
        r = math.radians(deg); self.lx = mag * math.sin(r); self.ly = -mag * math.cos(r)

    def camera(self, deg): self.cam = math.radians(deg)

    def frame(self):
        """Run what the player update runs at 0x1B53C0 (the original call, or
        whatever the patch put there), then do what third-person movement does
        with the result: yaw (+0x84) = input+8."""
        c = self.cpu
        w = c.r32(CALLSITE)
        target = (CALLSITE & 0xf0000000) | ((w & 0x3ffffff) << 2)
        c.call(target)
        c.wf(PLAYER + 0x84, c.rf(INPUT + 8))
        return math.degrees(c.rf(INPUT + 8)), math.degrees(c.rf(INPUT + 0x70))
