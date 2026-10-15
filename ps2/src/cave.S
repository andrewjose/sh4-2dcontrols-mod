# Copyright (c) 2026 andrewjose, made with Claude. MIT license (see LICENSE).
# https://github.com/andrewjose/sh4-2dcontrols-mod
#
# Controls2D for Silent Hill 4 (PS2, SLUS-20873) - SH2-style camera-relative
# directions. Runs right before the third-person input builder (0x15AA70)
# every frame: the call at 0x1B53C0 is redirected here, and this code ends by
# jumping to the builder with the original return address.
#
# The builder computes  target = atan2(stick) + [0x45A4B0]  where 0x45A4B0 is
# a camera yaw the game only sets when a scene initialises (0x15A3C0). This
# recomputes it every frame from the camera (SH2 0x547FA0 rule): on a camera
# cut while the stick is held, keep the old yaw until the stick is released
# or moves more than 30 degrees.
#
# Lives at 0x000FC000 (code) / 0x000FC400 (data); the game never touches
# 0x80000-0xFFFFF. Only caller-saved registers are used, values that must
# survive calls are kept in the data block, and ra is saved there too.

        .set noreorder
        .set noat
        .set mips2
        .set oddspreg           # the EE has 32 single-precision FPU registers

        .equ DATA,      0x000FC400
        .equ CAMYAW,    0x0045A4B0      # camera yaw the builder adds to the stick
        .equ BUILDER,   0x0015AA70
        .equ CAMFWD,    0x0015A1E0      # void GetCameraForward(float out[4])
        .equ ATAN2,     0x00121548      # float atan2f(f12 = y, f13 = x)
        .equ STICKX,    0x001AAF30      # float LeftStickX(a0 = port)
        .equ STICKY,    0x001AAF90      # float LeftStickY(a0 = port)

        # data block offsets
        .equ D_REF,     0x00
        .equ D_PREV,    0x04
        .equ D_LATCHST, 0x08
        .equ D_LASTWR,  0x0C
        .equ D_HAVEPRV, 0x10
        .equ D_LATCHED, 0x14
        .equ D_HAVEWR,  0x18
        .equ D_GWROTE,  0x1C
        .equ D_CAM,     0x20
        .equ D_LX,      0x24
        .equ D_LY,      0x28
        .equ D_STICK,   0x2C
        .equ D_PUSHED,  0x30
        .equ D_MAGIC,   0x34
        .equ D_RA,      0x38
        .equ D_FWD,     0x40            # 16 bytes
        .equ K_PI,      0x60
        .equ K_2PI,     0x64
        .equ K_CUT,     0x68            # camera turn per frame that counts as a cut (20 deg)
        .equ K_RELEASE, 0x6C            # stick change that ends the hold (30 deg)
        .equ K_DEAD2,   0x70            # dead zone squared
        .equ K_EPS,     0x74
        .equ K_MAGIC,   0x78

        .macro BASE
        lui     $t9, 0x0010
        addiu   $t9, $t9, -0x3C00       # 0x000FC400
        .endm
        .macro JAL target
        .word   0x0C000000 | (\target >> 2)
        .endm
        .macro J target
        .word   0x08000000 | (\target >> 2)
        .endm
        # f0 = wrap(f0) to (-pi, pi]; clobbers f1, f2. Inputs are within (-2pi, 2pi).
        .macro WRAP
        lwc1    $f1, K_PI($t9)
        lwc1    $f2, K_2PI($t9)
        c.olt.s  $f1, $f0
        bc1f    1f
        nop
        sub.s   $f0, $f0, $f2
1:      neg.s   $f1, $f1
        c.olt.s  $f0, $f1
        bc1f    2f
        nop
        add.s   $f0, $f0, $f2
2:
        .endm

        .text
        .globl  cave
cave:
        BASE
        sw      $ra, D_RA($t9)

        # first run (or memory left over from boot): reset the state
        lw      $t0, D_MAGIC($t9)
        lw      $t1, K_MAGIC($t9)
        beq     $t0, $t1, 1f
        nop
        sw      $zero, D_HAVEPRV($t9)
        sw      $zero, D_LATCHED($t9)
        sw      $zero, D_HAVEWR($t9)
        sw      $t1, D_MAGIC($t9)
1:
        # did the game write its own yaw since our last write? (scene init)
        lui     $t0, %hi(CAMYAW)
        lw      $t1, %lo(CAMYAW)($t0)
        lw      $t2, D_HAVEWR($t9)
        lw      $t3, D_LASTWR($t9)
        sltiu   $t4, $t2, 1             # !haveWritten
        xor     $t5, $t1, $t3
        sltu    $t5, $zero, $t5         # cur != lastWritten
        or      $t4, $t4, $t5
        sw      $t4, D_GWROTE($t9)

        # camera direction
        JAL     CAMFWD
        addiu   $a0, $t9, D_FWD
        BASE
        lwc1    $f12, D_FWD+0($t9)      # x
        lwc1    $f13, D_FWD+8($t9)      # z
        mul.s   $f0, $f12, $f12
        mul.s   $f1, $f13, $f13
        add.s   $f0, $f0, $f1
        lwc1    $f1, K_EPS($t9)
        c.ole.s  $f0, $f1
        bc1t    done                    # looking straight down: leave the game's value
        nop
        JAL     ATAN2                   # cam = atan2(x, z), as the game does at 0x15A400
        nop
        BASE
        swc1    $f0, D_CAM($t9)

        # stick
        JAL     STICKX
        move    $a0, $zero
        BASE
        swc1    $f0, D_LX($t9)
        JAL     STICKY
        move    $a0, $zero
        BASE
        swc1    $f0, D_LY($t9)
        lwc1    $f12, D_LX($t9)
        neg.s   $f13, $f0               # builder: atan2(X, -Y)
        mul.s   $f1, $f12, $f12
        mul.s   $f2, $f0, $f0
        add.s   $f1, $f1, $f2
        lwc1    $f2, K_DEAD2($t9)
        c.olt.s  $f2, $f1
        li      $t0, 0
        bc1f    1f
        nop
        li      $t0, 1
1:      sw      $t0, D_PUSHED($t9)
        JAL     ATAN2
        nop
        BASE
        swc1    $f0, D_STICK($t9)

        # SH2 rule
        lw      $t0, D_HAVEPRV($t9)
        bnez    $t0, have_prev
        nop
        lwc1    $f0, D_CAM($t9)         # first frame: follow the camera
        b       after
        swc1    $f0, D_REF($t9)

have_prev:
        lwc1    $f0, D_CAM($t9)
        lwc1    $f3, D_PREV($t9)
        sub.s   $f0, $f0, $f3
        WRAP
        abs.s   $f0, $f0
        lwc1    $f1, K_CUT($t9)
        c.olt.s  $f1, $f0                # camera jumped: a cut
        bc1t    is_cut
        nop
        lw      $t0, D_GWROTE($t9)      # the game re-initialised its yaw: also a cut
        lw      $t1, D_HAVEWR($t9)
        and     $t0, $t0, $t1
        bnez    $t0, is_cut
        nop
        lw      $t0, D_LATCHED($t9)     # no cut: follow the camera unless holding
        bnez    $t0, check_release
        nop
        lwc1    $f0, D_CAM($t9)
        b       check_release
        swc1    $f0, D_REF($t9)

is_cut:
        lw      $t0, D_PUSHED($t9)
        beqz    $t0, cut_free
        nop
        lw      $t1, D_LATCHED($t9)     # holding the stick: keep the old yaw
        bnez    $t1, check_release
        nop
        li      $t1, 1
        sw      $t1, D_LATCHED($t9)
        lwc1    $f0, D_STICK($t9)
        b       check_release
        swc1    $f0, D_LATCHST($t9)
cut_free:
        sw      $zero, D_LATCHED($t9)   # stick released: switch at once
        lwc1    $f0, D_CAM($t9)
        swc1    $f0, D_REF($t9)

check_release:
        lw      $t0, D_LATCHED($t9)
        beqz    $t0, after
        nop
        lw      $t1, D_PUSHED($t9)
        beqz    $t1, release
        nop
        lwc1    $f0, D_STICK($t9)
        lwc1    $f3, D_LATCHST($t9)
        sub.s   $f0, $f0, $f3
        WRAP
        abs.s   $f0, $f0
        lwc1    $f1, K_RELEASE($t9)
        c.olt.s  $f1, $f0
        bc1f    after
        nop
release:
        sw      $zero, D_LATCHED($t9)
        lwc1    $f0, D_CAM($t9)
        swc1    $f0, D_REF($t9)

after:
        lwc1    $f0, D_CAM($t9)
        swc1    $f0, D_PREV($t9)
        li      $t0, 1
        sw      $t0, D_HAVEPRV($t9)
        lw      $t1, D_REF($t9)
        lui     $t0, %hi(CAMYAW)
        sw      $t1, %lo(CAMYAW)($t0)
        sw      $t1, D_LASTWR($t9)
        li      $t0, 1
        sw      $t0, D_HAVEWR($t9)

done:
        BASE
        lw      $ra, D_RA($t9)
        J       BUILDER
        nop
cave_end:
