"""Tiny Emotion Engine (PS2 R5900) interpreter: enough of the integer ISA, the
FPU (incl. EE's ACC ops) and VU0 macro mode to run SH4's input builder and a
hand-written code cave. Floats are kept as float32 bit patterns."""
import struct, math, rabbitizer

MASK64 = (1 << 64) - 1
def s32(v): v &= 0xffffffff; return v - (1 << 32) if v & 0x80000000 else v
def s64(v): v &= MASK64; return v - (1 << 64) if v >> 63 else v
def sx32(v): return s32(v) & MASK64          # sign-extend 32 -> 64 (as unsigned 64)
def f2b(f):
    try: return struct.unpack('<I', struct.pack('<f', f))[0]
    except OverflowError: return 0x7f7fffff if f > 0 else 0xff7fffff
def b2f(b): return struct.unpack('<f', struct.pack('<I', b & 0xffffffff))[0]
def r32(f): return b2f(f2b(f))

class Stop(Exception): pass

class EE:
    RET_MAGIC = 0x0BAD0000

    def __init__(self, segments, ramsize=0x2000000):
        """segments: {address: bytes} to load (e.g. an ELF's loadable segments)."""
        self.mem = bytearray(ramsize)
        for base, data in segments.items():
            self.mem[base:base + len(data)] = data
        self.gpr = [0] * 32
        self.fpr = [0] * 32
        self.cc = False
        self.acc = 0.0
        self.vf = [[0.0, 0.0, 0.0, 0.0] for _ in range(32)]
        self.vf[0] = [0.0, 0.0, 0.0, 1.0]
        self.Q = 0.0
        self.hi = self.lo = 0
        self.stubs = {}
        self.trace = None
        self.steps = 0
        self._cache = {}
        rabbitizer.config.regNames_gprAbiNames = rabbitizer.Abi.O32

    # ---- memory ----
    def r8(self, a): return self.mem[a & 0x1ffffff]
    def r32(self, a): return struct.unpack_from('<I', self.mem, a & 0x1ffffff)[0]
    def r64(self, a): return struct.unpack_from('<Q', self.mem, a & 0x1ffffff)[0]
    def w8(self, a, v): self.mem[a & 0x1ffffff] = v & 0xff
    def w16(self, a, v): struct.pack_into('<H', self.mem, a & 0x1ffffff, v & 0xffff)
    def w32(self, a, v): struct.pack_into('<I', self.mem, a & 0x1ffffff, v & 0xffffffff)
    def w64(self, a, v): struct.pack_into('<Q', self.mem, a & 0x1ffffff, v & MASK64)
    def rf(self, a): return b2f(self.r32(a))
    def wf(self, a, f): self.w32(a, f2b(f))

    # ---- registers ----
    def g(self, i): return self.gpr[i] & MASK64
    def sg(self, i, v):
        if i: self.gpr[i] = v & ((1 << 128) - 1)
    def f(self, i): return b2f(self.fpr[i])
    def sf(self, i, v): self.fpr[i] = f2b(v)

    def decode(self, a):
        w = self.r32(a)
        c = self._cache.get(a)
        if c and c[0] == w: return c[1], w
        r = rabbitizer.Instruction(w, vram=a, category=rabbitizer.InstrCategory.R5900)
        name = r.uniqueId.name
        self._cache[a] = (w, name)
        return name, w

    # ---- execution ----
    def call(self, addr, max_steps=200000):
        self.sg(31, self.RET_MAGIC)
        self.pc = addr
        self.npc = addr + 4
        n = 0
        while self.pc != self.RET_MAGIC:
            if self.pc in self.stubs:
                self.stubs[self.pc](self)
                self.pc = self.g(31) & 0xffffffff
                self.npc = self.pc + 4
                continue
            self.step()
            n += 1
            if n > max_steps: raise Stop('too many steps at %08x' % self.pc)
        self.steps += n

    def step(self):
        a = self.pc
        name, w = self.decode(a)
        if self.trace: self.trace(a, w, name)
        self.pc = self.npc
        self.npc = self.pc + 4
        self.exec(a, w, name)

    def branch(self, a, w, cond, likely=False):
        if cond:
            off = s32((w & 0xffff) << 16) >> 14
            self.npc = (a + 4 + off) & 0xffffffff
        elif likely:
            self.pc = self.npc; self.npc = self.pc + 4   # skip delay slot

    def exec(self, a, w, n):
        rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31
        sa = (w >> 6) & 31; imm = w & 0xffff; simm = imm - 0x10000 if imm & 0x8000 else imm
        ft = rt; fs = rd; fd = sa
        G = self.g
        if n in ('cpu_nop', 'cpu_sync', 'r5900_vwaitq', 'r5900_sync_p'): return
        if n == 'cpu_lui': self.sg(rt, sx32(imm << 16)); return
        if n == 'cpu_addiu': self.sg(rt, sx32(G(rs) + simm)); return
        if n == 'cpu_daddiu': self.sg(rt, G(rs) + simm); return
        if n == 'cpu_addu': self.sg(rd, sx32(G(rs) + G(rt))); return
        if n == 'cpu_subu': self.sg(rd, sx32(G(rs) - G(rt))); return
        if n in ('cpu_daddu', 'cpu_move'): self.sg(rd, G(rs) + G(rt)); return
        if n == 'cpu_dsubu': self.sg(rd, G(rs) - G(rt)); return
        if n == 'cpu_ori': self.sg(rt, G(rs) | imm); return
        if n == 'cpu_andi': self.sg(rt, G(rs) & imm); return
        if n == 'cpu_xori': self.sg(rt, G(rs) ^ imm); return
        if n == 'cpu_or': self.sg(rd, G(rs) | G(rt)); return
        if n == 'cpu_and': self.sg(rd, G(rs) & G(rt)); return
        if n == 'cpu_xor': self.sg(rd, G(rs) ^ G(rt)); return
        if n == 'cpu_nor': self.sg(rd, ~(G(rs) | G(rt))); return
        if n == 'cpu_sll': self.sg(rd, sx32(G(rt) << sa)); return
        if n == 'cpu_srl': self.sg(rd, sx32((G(rt) & 0xffffffff) >> sa)); return
        if n == 'cpu_sra': self.sg(rd, sx32(s32(G(rt)) >> sa)); return
        if n == 'cpu_dsll': self.sg(rd, G(rt) << sa); return
        if n == 'cpu_dsll32': self.sg(rd, G(rt) << (sa + 32)); return
        if n == 'cpu_dsra32': self.sg(rd, s64(G(rt)) >> (sa + 32)); return
        if n == 'cpu_slt': self.sg(rd, int(s64(G(rs)) < s64(G(rt)))); return
        if n == 'cpu_sltu': self.sg(rd, int(G(rs) < G(rt))); return
        if n == 'cpu_slti': self.sg(rt, int(s64(G(rs)) < simm)); return
        if n == 'cpu_sltiu': self.sg(rt, int(G(rs) < (simm & MASK64))); return
        if n == 'cpu_movn':
            if G(rt): self.sg(rd, G(rs))
            return
        if n == 'cpu_movz':
            if not G(rt): self.sg(rd, G(rs))
            return
        ea = (G(rs) + simm) & 0xffffffff
        if n == 'cpu_lw': self.sg(rt, sx32(self.r32(ea))); return
        if n == 'cpu_lb': v = self.r8(ea); self.sg(rt, (v - 256 if v & 0x80 else v) & MASK64); return
        if n == 'cpu_lbu': self.sg(rt, self.r8(ea)); return
        if n == 'cpu_ld': self.sg(rt, self.r64(ea)); return
        if n == 'cpu_sw': self.w32(ea, G(rt)); return
        if n == 'cpu_sb': self.w8(ea, G(rt)); return
        if n == 'cpu_sh': self.w16(ea, G(rt)); return
        if n == 'cpu_sd': self.w64(ea, G(rt)); return
        if n == 'r5900_lq':
            ea &= ~15
            self.sg(rt, self.r64(ea) | (self.r64(ea + 8) << 64)); return
        if n == 'r5900_sq':
            ea &= ~15; v = self.gpr[rt]
            self.w64(ea, v); self.w64(ea + 8, v >> 64); return
        if n == 'cpu_lwc1': self.fpr[ft] = self.r32(ea); return
        if n == 'cpu_swc1': self.w32(ea, self.fpr[ft]); return
        # ---- control flow ----
        if n == 'cpu_jal':
            self.sg(31, a + 8); self.npc = (a & 0xf0000000) | ((w & 0x3ffffff) << 2); return
        if n == 'cpu_j':
            self.npc = (a & 0xf0000000) | ((w & 0x3ffffff) << 2); return
        if n == 'cpu_jr': self.npc = G(rs) & 0xffffffff; return
        if n == 'cpu_jalr': t = G(rs); self.sg(rd, a + 8); self.npc = t & 0xffffffff; return
        if n in ('cpu_beq', 'cpu_b'): self.branch(a, w, G(rs) == G(rt)); return
        if n == 'cpu_beqz': self.branch(a, w, G(rs) == 0); return
        if n in ('cpu_bne', 'cpu_bnez'): self.branch(a, w, G(rs) != G(rt)); return
        if n == 'cpu_beql': self.branch(a, w, G(rs) == G(rt), True); return
        if n in ('cpu_bnel', 'cpu_bnezl'): self.branch(a, w, G(rs) != G(rt), True); return
        if n == 'cpu_bgtz': self.branch(a, w, s64(G(rs)) > 0); return
        if n == 'cpu_blez': self.branch(a, w, s64(G(rs)) <= 0); return
        if n == 'cpu_bltz': self.branch(a, w, s64(G(rs)) < 0); return
        if n == 'cpu_bgez': self.branch(a, w, s64(G(rs)) >= 0); return
        if n == 'cpu_bc1t': self.branch(a, w, self.cc); return
        if n == 'cpu_bc1f': self.branch(a, w, not self.cc); return
        if n == 'cpu_bc1tl': self.branch(a, w, self.cc, True); return
        if n == 'cpu_bc1fl': self.branch(a, w, not self.cc, True); return
        # ---- FPU ----
        F = self.f
        if n == 'cpu_mtc1': self.fpr[fs] = G(rt) & 0xffffffff; return
        if n == 'cpu_mfc1': self.sg(rt, sx32(self.fpr[fs])); return
        if n == 'cpu_mov_s': self.fpr[fd] = self.fpr[fs]; return
        if n == 'cpu_add_s': self.sf(fd, F(fs) + F(ft)); return
        if n == 'cpu_sub_s': self.sf(fd, F(fs) - F(ft)); return
        if n == 'cpu_mul_s': self.sf(fd, F(fs) * F(ft)); return
        if n == 'cpu_div_s': self.sf(fd, F(fs) / F(ft) if F(ft) != 0 else math.copysign(3.4028234e38, F(fs))); return
        if n == 'cpu_abs_s': self.sf(fd, abs(F(fs))); return
        if n == 'cpu_neg_s': self.sf(fd, -F(fs)); return
        if n == 'r5900_c1__sqrt_s': self.sf(fd, math.sqrt(abs(F(ft)))); return
        if n == 'cpu_cvt_s_w': self.sf(fd, float(s32(self.fpr[fs]))); return
        if n == 'cpu_cvt_w_s':
            v = F(fs); v = max(min(v, 2147483647.0), -2147483648.0); self.fpr[fd] = int(v) & 0xffffffff; return
        if n.startswith(('cpu_c_', 'r5900_c_')) and (w & 0x3f) not in (0x30, 0x32, 0x34, 0x36):
            raise Stop('FPU compare funct %02x does not exist on the EE (%08x at %08x)' % (w & 0x3f, w, a))
        if n == 'cpu_c_eq_s': self.cc = F(fs) == F(ft); return
        if n in ('r5900_c_lt_s', 'cpu_c_lt_s', 'cpu_c_olt_s'): self.cc = F(fs) < F(ft); return
        if n in ('r5900_c_le_s', 'cpu_c_le_s', 'cpu_c_ole_s'): self.cc = F(fs) <= F(ft); return
        if n == 'cpu_c_f_s': self.cc = False; return
        if n == 'r5900_mula_s': self.acc = r32(F(fs) * F(ft)); return
        if n == 'r5900_adda_s': self.acc = r32(F(fs) + F(ft)); return
        if n == 'r5900_madd_s': self.sf(fd, self.acc + F(fs) * F(ft)); return
        if n == 'r5900_msub_s': self.sf(fd, self.acc - F(fs) * F(ft)); return
        # ---- VU0 macro mode ----
        if n.startswith('r5900_v') or n in ('r5900_lqc2', 'r5900_sqc2', 'r5900_cfc2_ni', 'r5900_qmtc2_ni', 'r5900_qmfc2_ni'):
            return self.vu(a, w, n, rs, rt)
        raise Stop('unimplemented %s (%08x) at %08x' % (n, w, a))

    def vu(self, a, w, n, rs, rt):
        dest = [(w >> 24) & 1, (w >> 23) & 1, (w >> 22) & 1, (w >> 21) & 1]   # x y z w
        vft = (w >> 16) & 31; vfs = (w >> 11) & 31; vfd = (w >> 6) & 31
        V = self.vf
        def setv(i, vals):
            if i == 0: return
            for c in range(4):
                if dest[c]: V[i][c] = r32(vals[c])
        bc = w & 3
        if n in ('r5900_lqc2', 'r5900_sqc2'):
            simm = w & 0xffff; simm = simm - 0x10000 if simm & 0x8000 else simm
            ea = (self.g(rs) + simm) & 0xfffffff0
            if n == 'r5900_lqc2':
                if rt: V[rt] = [self.rf(ea + 4 * c) for c in range(4)]
            else:
                for c in range(4): self.wf(ea + 4 * c, V[rt][c])
            return
        if n == 'r5900_qmtc2_ni':
            v = self.gpr[rt]
            if rs and False: pass
            idx = (w >> 11) & 31
            if idx: V[idx] = [b2f((v >> (32 * c)) & 0xffffffff) for c in range(4)]
            return
        if n == 'r5900_qmfc2_ni':
            idx = (w >> 11) & 31
            self.sg(rt, sum(f2b(V[idx][c]) << (32 * c) for c in range(4))); return
        if n == 'r5900_cfc2_ni':
            idx = (w >> 11) & 31
            if idx == 22: self.sg(rt, sx32(f2b(self.Q)))
            else: self.sg(rt, 0)
            return
        s, t = V[vfs], V[vft]
        if n == 'r5900_vmul': setv(vfd, [s[c] * t[c] for c in range(4)]); return
        if n == 'r5900_vadd': setv(vfd, [s[c] + t[c] for c in range(4)]); return
        if n == 'r5900_vsub': setv(vfd, [s[c] - t[c] for c in range(4)]); return
        for op, fn in (('add', lambda x, y: x + y), ('sub', lambda x, y: x - y), ('mul', lambda x, y: x * y)):
            for i, ch in enumerate('xyzw'):
                if n == 'r5900_v%s%s' % (op, ch): setv(vfd, [fn(s[c], t[i]) for c in range(4)]); return
        if n == 'r5900_vmulq': setv(vfd, [s[c] * self.Q for c in range(4)]); return
        if n == 'r5900_vmove': setv(vft, s); return
        fsf = (w >> 21) & 3; ftf = (w >> 23) & 3
        if n == 'r5900_vsqrt': self.Q = r32(math.sqrt(abs(V[vft][ftf]))); return
        if n == 'r5900_vrsqrt':
            d = math.sqrt(abs(V[vft][ftf])); self.Q = r32(V[vfs][fsf] / d if d else 3.4e38); return
        if n == 'r5900_vdiv':
            d = V[vft][ftf]; self.Q = r32(V[vfs][fsf] / d if d else 3.4e38); return
        raise Stop('unimplemented VU %s (%08x) at %08x' % (n, w, a))
