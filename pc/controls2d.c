/*
 * Controls2D 1.1 - SH2/SH3-style "2D" movement for Silent Hill 4 (GOG,
 * SILENT_HILL_4.exe timestamp 0x41071F62), as a plugin for Zealot's mod loader.
 *
 * Copyright (c) 2026 andrewjose, made with Claude. MIT license (see LICENSE).
 * https://github.com/andrewjose/sh4-2dcontrols-mod
 *
 * What SH4 does (from the exe)
 *   The third-person input builder (0x52F260, called once per frame from the
 *   player controller at 0x534B2E) already turns the stick into a screen-
 *   relative direction:  target = atan2(stick) + [0x10A1918].  Henry then turns
 *   toward the target and does a turn-around if it is more than 135 degrees
 *   away (0x537B80).  But [0x10A1918] - the camera yaw - is only computed when
 *   the player controller initialises (0x52ED80 / 0x52EEA0, via the per-camera
 *   scene tables), so within a camera zone it never follows the camera, and on
 *   a re-init the meaning of the stick changes instantly under your thumb.
 *
 * What SH2 does (SILENT HILL 2 PC, function 0x547FA0, 2D control style)
 *   Every frame: camera yaw = atan2(target - eye).  On a camera cut while the
 *   stick is held, it keeps using the previous camera's yaw until the stick is
 *   released or moved more than 30 degrees from where it was at the cut.
 *
 * What this plugin does
 *   Hooks the call at 0x534B2E so that, right before the builder runs, the
 *   SH2 logic above computes the camera yaw (from the game's own camera-
 *   forward function 0x55BFC0, same atan2(x, z) the game uses) and writes it
 *   into [0x10A1918].  Everything else - walking, running, turn-arounds, the
 *   per-scene stick inversion - is still SH4's own code.
 *
 * Turning (new in 1.1)
 *   The builder doesn't point Henry at the stick direction; it steers his
 *   walking direction toward it (0x52FCDB) at
 *       rate = 6pi - speed * (4pi + run * pi)   rad/s
 *   i.e. 1080 deg/s standing, 360 deg/s walking and only 180 deg/s running,
 *   and caps running at 60% while a turn is in progress. A 90-degree change
 *   at a run takes half a second - the wide arc. When the camera looks down
 *   steeply (horizontal part of its forward vector < 0.95) a second steering
 *   stage (0x52F90D) also limits the turn to 0.2 * that part per frame.
 *   Henry's body then turns to face the walking direction at 12 rad/s
 *   (0x535062).
 *   1.1 points those instructions at its own constants: a fixed turn rate
 *   (default: instant), the steep-camera stage always takes the stick
 *   direction directly, and the body turns at facing_speed. The game's own
 *   code still does the steering, so speed, the run cap and everything else
 *   behave as before.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define PI 3.14159265358979f

/* game addresses (exe base 0x400000) */
#define VA_HOOK_CALL   0x534B2Eu  /* call 0x52F260 (input builder), only caller */
#define VA_BUILDER     0x52F260u
#define VA_REF_READ    0x52F5D5u  /* fld dword ptr [0x10A1918] inside the builder */
#define VA_REF_YAW     0x10A1918u /* camera yaw the stick is relative to */
#define VA_AXIS_FLIP   0x10A19DCu /* set by one event script: stick rotated 180 */
#define VA_CAM_FWD     0x55BFC0u  /* void GetCameraForward(float out[4]) */
#define VA_STICK_X     0x4F8610u  /* float GetLeftStickX(int port) */
#define VA_STICK_Y     0x4F8660u  /* float GetLeftStickY(int port) */

typedef void (__cdecl *CamFwdFn)(float *out);
typedef float (__cdecl *AxisFn)(int port);

static const struct { DWORD va; BYTE n; BYTE b[12]; const char *what; } kChecks[] = {
    {VA_HOOK_CALL, 5,  {0xE8,0x2D,0xA7,0xFF,0xFF}, "call to input builder"},
    {VA_REF_READ,  6,  {0xD9,0x05,0x18,0x19,0x0A,0x01}, "builder reads camera yaw"},
    {VA_CAM_FWD,   12, {0x55,0x8B,0xEC,0x8B,0x45,0x08,0x8B,0x0D,0x60,0x41,0x2E,0x01}, "GetCameraForward"},
    {VA_STICK_X,   6,  {0xD9,0x05,0x4C,0xBE,0x07,0x01}, "GetLeftStickX"},
    {VA_STICK_Y,   6,  {0xD9,0x05,0x50,0xBE,0x07,0x01}, "GetLeftStickY"},
};
#define NCHECKS ((int)(sizeof(kChecks) / sizeof(kChecks[0])))

/* Steering constants: each is the 4-byte address operand of an x87
 * instruction (D8 xx <addr>) that reads a shared float. We point the operand
 * at our own float (only that instruction changes) and back. */
static volatile float g_zero = 0.0f, g_turnRate = 18.849556f, g_always = -1.0f, g_faceRate = 12.0f;
typedef struct { DWORD va; BYTE op0, op1; DWORD orig; float origVal; volatile float *mine; int facing; const char *what; } Op;
static Op g_ops[] = {
    {0x52FCE1, 0xD8, 0x0D, 0x5B79DCu, 3.1415927f, &g_zero,     0, "turn rate: running penalty (pi)"},
    {0x52FCE7, 0xD8, 0x2D, 0x5B7D28u, 6.2831855f, &g_turnRate, 0, "turn rate: at full speed (2pi)"},
    {0x52FCED, 0xD8, 0x2D, 0x5B7ED8u, 18.849556f, &g_turnRate, 0, "turn rate: (6pi)"},
    {0x52FCF9, 0xD8, 0x2D, 0x5B7ED8u, 18.849556f, &g_turnRate, 0, "turn rate: standing (6pi)"},
    {0x52F8CE, 0xD8, 0x1D, 0x5B7DB4u, 0.95f,      &g_always,   0, "steep-camera steering threshold"},
    {0x535062, 0xD8, 0x0D, 0x5B8160u, 12.0f,      &g_faceRate, 1, "body facing speed (12 rad/s)"},
};
#define NOPS ((int)(sizeof(g_ops) / sizeof(g_ops[0])))

/* ---- state -------------------------------------------------------------- */
static BYTE *g_stub;
static BYTE g_origCall[5];
static int g_installed, g_disabled, g_inited, g_enabled, g_keyWasDown, g_opsOn, g_opsOk;
static float g_ref, g_prevCam, g_latchStick, g_lastWritten, g_gameRef;
static int g_havePrev, g_latched, g_haveWritten, g_lastFlip = -1;
static long g_frames, g_cuts, g_reinits;
static FILE *g_log;
static int g_logLines;
static char g_dir[MAX_PATH];

static int cfg_enabled = 1, cfg_key = VK_F3, cfg_beep = 1, cfg_hold = 1, cfg_strict = 1, cfg_verbose = 0;
static float cfg_release = 30.0f, cfg_cut = 20.0f, cfg_dead = 0.10f;
static int cfg_snap = 1;
static float cfg_turn = 0.0f, cfg_face = 1440.0f;   /* degrees per second; turn 0 = instant */

/* ---- helpers ------------------------------------------------------------ */
static void plog(const char *fmt, ...)
{
    if (!g_log || g_logLines > 20000) return;
    SYSTEMTIME t; GetLocalTime(&t);
    fprintf(g_log, "[%02d:%02d:%02d.%03d] ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
    if (++g_logLines == 20000) fputs("log line limit reached\n", g_log);
}

static float wrap(float a)
{
    while (a > PI) a -= 2 * PI;
    while (a < -PI) a += 2 * PI;
    return a;
}
static float deg(float r) { return r * 180.0f / PI; }

static int readable(const void *p, SIZE_T n)
{
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(p, &mbi, sizeof mbi) || mbi.State != MEM_COMMIT) return 0;
    if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;
    return (const BYTE *)p + n <= (const BYTE *)mbi.BaseAddress + mbi.RegionSize;
}

static void put32(BYTE *p, DWORD v) { memcpy(p, &v, 4); }
static volatile float *REF(void) { return (volatile float *)(uintptr_t)VA_REF_YAW; }

/* ---- steering constants ------------------------------------------------ */
static DWORD *op_addr(const Op *o) { return (DWORD *)(uintptr_t)(o->va + 2); }
static int ops_verify(void)
{
    int bad = 0;
    for (int i = 0; i < NOPS; i++) {
        Op *o = &g_ops[i];
        const BYTE *p = (const BYTE *)(uintptr_t)o->va;
        int ok = readable(p, 6) && p[0] == o->op0 && p[1] == o->op1 && *op_addr(o) == o->orig &&
                 readable((void *)(uintptr_t)o->orig, 4) && *(float *)(uintptr_t)o->orig == o->origVal;
        plog("check 0x%06lX %-34s %s", (unsigned long)o->va, o->what,
             ok ? "ok" : "FAIL (bytes differ: different exe or another mod patched it)");
        bad += !ok;
    }
    return bad;
}
static void ops_set(int on)
{
    if (!g_opsOk || on == g_opsOn) return;
    for (int i = 0; i < NOPS; i++) {
        Op *o = &g_ops[i];
        DWORD v = (on && !(o->facing && cfg_face <= 0)) ? (DWORD)(uintptr_t)o->mine : o->orig;
        DWORD old;
        VirtualProtect(op_addr(o), 4, PAGE_EXECUTE_READWRITE, &old);
        *(volatile DWORD *)op_addr(o) = v;
        FlushInstructionCache(GetCurrentProcess(), op_addr(o), 4);
    }
    g_opsOn = on;
}

/* ---- the per-frame logic (runs right before the game's input builder) ---- */
void __cdecl Controls2D_BeforeInput(void)
{
    volatile float *ref = REF();
    float cur = *ref;

    /* Did the game write its own value since our last write? That happens when
     * the player controller re-initialises (new scene / camera block). */
    int gameWrote = !g_haveWritten || memcmp(&cur, &g_lastWritten, 4) != 0;
    if (gameWrote) {
        g_gameRef = cur;
        if (g_haveWritten) {
            g_reinits++;
            if (cfg_verbose || g_reinits <= 200) plog("game re-initialised camera yaw to %.1f deg", deg(cur));
        }
    }
    g_frames++;

    int flip = *(volatile int *)(uintptr_t)VA_AXIS_FLIP;
    if (flip != g_lastFlip) { plog("scene stick inversion %s", flip ? "ON" : "off"); g_lastFlip = flip; }

    if (!g_enabled || g_disabled) {
        if (g_haveWritten) { *ref = g_gameRef; g_haveWritten = 0; }
        g_havePrev = 0; g_latched = 0;
        return;
    }

    float fwd[4] = {0, 0, 0, 0};
    ((CamFwdFn)(uintptr_t)VA_CAM_FWD)(fwd);
    float h = fwd[0] * fwd[0] + fwd[2] * fwd[2];
    if (!(h > 1e-8f)) return;               /* camera looking straight down: leave it */
    float cam = atan2f(fwd[0], fwd[2]);     /* same formula as the game (0x52ECE0) */

    float lx = ((AxisFn)(uintptr_t)VA_STICK_X)(0);
    float ly = ((AxisFn)(uintptr_t)VA_STICK_Y)(0);
    int pushed = lx * lx + ly * ly > cfg_dead * cfg_dead;
    float stick = atan2f(lx, -ly);          /* same angle the builder uses */

    if (!g_havePrev) {
        g_ref = cam;
    } else {
        float jump = fabsf(wrap(cam - g_prevCam));
        int cut = jump > cfg_cut * PI / 180.0f || (gameWrote && g_haveWritten);
        if (cut) {
            g_cuts++;
            if (pushed && cfg_hold) {
                if (!g_latched) { g_latched = 1; g_latchStick = stick; }
                if (cfg_verbose || g_cuts <= 500)
                    plog("camera cut (%.0f deg): holding direction until stick moves %.0f deg or is released",
                         deg(jump), cfg_release);
            } else {
                g_latched = 0; g_ref = cam;
            }
        } else if (!g_latched) {
            g_ref = cam;
        }
        if (g_latched && (!pushed || fabsf(wrap(stick - g_latchStick)) > cfg_release * PI / 180.0f)) {
            g_latched = 0; g_ref = cam;
            if (cfg_verbose) plog("hold released (%s)", pushed ? "stick moved" : "stick released");
        }
    }
    g_prevCam = cam; g_havePrev = 1;

    *ref = g_ref;
    memcpy(&g_lastWritten, &g_ref, 4);
    g_haveWritten = 1;
}

/* ---- config ------------------------------------------------------------- */
static const char *kDefaultIni =
"[Controls2D]\r\n"
"; 1 = SH2/SH3-style 2D movement at startup, 0 = SH4's original behaviour\r\n"
"enabled=1\r\n"
"; Virtual-key code of the on/off toggle (0x72 = F3)\r\n"
"toggle_key=0x72\r\n"
"; Beep when toggling\r\n"
"beep=1\r\n"
"; On a camera cut, keep walking the same way while the stick is held (SH2/SH3)\r\n"
"hold_on_cut=1\r\n"
"; Degrees the stick must move after a cut before the new camera takes over (SH2: 30)\r\n"
"release_angle=30\r\n"
"; A camera turn bigger than this in one frame counts as a cut (degrees)\r\n"
"cut_angle=20\r\n"
"; SH2-style turning: Henry turns straight to the stick direction instead of\r\n"
"; arcing (SH4 steers at 360 deg/s walking, 180 deg/s running). 0 = SH4's turning\r\n"
"snap_turn=1\r\n"
"; How fast his walking direction turns, degrees per second. 0 = instantly.\r\n"
"; (SH4: 1080 standing still, 360 walking, 180 running)\r\n"
"turn_speed=0\r\n"
"; How fast his body turns to face that direction, degrees per second.\r\n"
"; 0 = leave SH4's (690). Higher = snappier.\r\n"
"facing_speed=1440\r\n"
"; Stick dead zone (0..1)\r\n"
"deadzone=0.10\r\n"
"; Refuse to patch if the game code doesn't match the expected build\r\n"
"strict=1\r\n"
"; Log every cut and release (1) or just the first few hundred (0)\r\n"
"verbose_log=0\r\n";

static float ini_float(const char *path, const char *key, float def)
{
    char buf[64];
    GetPrivateProfileStringA("Controls2D", key, "", buf, sizeof buf, path);
    return buf[0] ? (float)atof(buf) : def;
}
static int ini_int(const char *path, const char *key, int def)
{
    char buf[64];
    GetPrivateProfileStringA("Controls2D", key, "", buf, sizeof buf, path);
    return buf[0] ? (int)strtol(buf, NULL, 0) : def;
}

static void load_config(void)
{
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%s\\Controls2D.ini", g_dir);
    if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES) {
        FILE *f = fopen(path, "wb");
        if (f) { fputs(kDefaultIni, f); fclose(f); }
    }
    cfg_enabled = ini_int(path, "enabled", 1);
    cfg_key     = ini_int(path, "toggle_key", VK_F3);
    cfg_beep    = ini_int(path, "beep", 1);
    cfg_hold    = ini_int(path, "hold_on_cut", 1);
    cfg_release = ini_float(path, "release_angle", 30.0f);
    cfg_cut     = ini_float(path, "cut_angle", 20.0f);
    cfg_dead    = ini_float(path, "deadzone", 0.10f);
    cfg_strict  = ini_int(path, "strict", 1);
    cfg_verbose = ini_int(path, "verbose_log", 0);
    cfg_snap    = ini_int(path, "snap_turn", 1);
    cfg_turn    = ini_float(path, "turn_speed", 0.0f);
    cfg_face    = ini_float(path, "facing_speed", 1440.0f);
    if (cfg_turn < 0) cfg_turn = 0;
    if (cfg_turn > 0 && cfg_turn < 90) cfg_turn = 90;
    if (cfg_face < 0) cfg_face = 0;
    if (cfg_face > 0 && cfg_face < 90) cfg_face = 90;
    g_turnRate = cfg_turn > 0 ? cfg_turn * PI / 180.0f : 1.0e6f;
    g_faceRate = cfg_face * PI / 180.0f;
    if (cfg_key <= 0 || cfg_key > 0xFE) cfg_key = VK_F3;
    if (cfg_release < 1) cfg_release = 1;
    if (cfg_cut < 1) cfg_cut = 1;
    if (cfg_dead < 0 || cfg_dead > 0.9f) cfg_dead = 0.10f;
    plog("config: enabled=%d toggle_key=0x%02X hold_on_cut=%d release_angle=%.0f cut_angle=%.0f deadzone=%.2f strict=%d",
         cfg_enabled, cfg_key, cfg_hold, cfg_release, cfg_cut, cfg_dead, cfg_strict);
    plog("config: snap_turn=%d turn_speed=%.0f%s facing_speed=%.0f%s", cfg_snap, cfg_turn,
         cfg_turn > 0 ? " deg/s" : " (instant)", cfg_face, cfg_face > 0 ? " deg/s" : " (SH4's)");
}

/* ---- install ------------------------------------------------------------ */
static int verify_and_install(void)
{
    int bad = 0;
    for (int i = 0; i < NCHECKS; i++) {
        const BYTE *p = (const BYTE *)(uintptr_t)kChecks[i].va;
        int ok = readable(p, kChecks[i].n) && !memcmp(p, kChecks[i].b, kChecks[i].n);
        plog("check 0x%06lX %-26s %s", (unsigned long)kChecks[i].va, kChecks[i].what,
             ok ? "ok" : "FAIL (bytes differ: different exe or another mod patched it)");
        bad += !ok;
    }
    int badOps = cfg_snap ? ops_verify() : 0;
    if (bad) {
        plog("%d check(s) failed. %s", bad, cfg_strict ? "Not installing." : "strict=0, installing anyway.");
        if (cfg_strict) return 0;
    }
    g_opsOk = cfg_snap && !badOps;
    if (cfg_snap && badOps) plog("%d turning check(s) failed: snap_turn disabled, camera-relative part still installed", badOps);
    g_stub = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_stub) { plog("VirtualAlloc failed"); return 0; }
    /* stub: call Controls2D_BeforeInput / jmp builder (it returns to the game) */
    BYTE *p = g_stub;
    p[0] = 0xE8; put32(p + 1, (DWORD)((uintptr_t)&Controls2D_BeforeInput - (uintptr_t)(p + 5))); p += 5;
    p[0] = 0xE9; put32(p + 1, (DWORD)(VA_BUILDER - (uintptr_t)(p + 5)));
    FlushInstructionCache(GetCurrentProcess(), g_stub, 64);

    BYTE *site = (BYTE *)(uintptr_t)VA_HOOK_CALL;
    DWORD old;
    VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old);
    memcpy(g_origCall, site, 5);
    BYTE call[5] = {0xE8};
    put32(call + 1, (DWORD)((uintptr_t)g_stub - (VA_HOOK_CALL + 5)));
    memcpy(site, call, 5);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    g_installed = 1;
    ops_set(g_enabled);
    plog("installed. 2D controls %s, snap turning %s, toggle key 0x%02X", g_enabled ? "ON" : "OFF",
         g_opsOk ? "ready" : "off", cfg_key);
    return 1;
}

static void uninstall(void)
{
    if (!g_installed) return;
    ops_set(0);
    BYTE *site = (BYTE *)(uintptr_t)VA_HOOK_CALL;
    if (g_haveWritten) { *REF() = g_gameRef; g_haveWritten = 0; }
    memcpy(site, g_origCall, 5);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    g_installed = 0;
    if (g_stub) { VirtualFree(g_stub, 0, MEM_RELEASE); g_stub = NULL; }
}

/* ---- plugin exports (stdcall; names match the loader's GetProcAddress) --- */
int __stdcall LoadPlugin(int base)
{
    (void)base;
    HMODULE self = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&LoadPlugin, &self);
    GetModuleFileNameA(self, g_dir, sizeof g_dir);
    char *slash = strrchr(g_dir, '\\');
    if (slash) *slash = 0;
    char logPath[MAX_PATH];
    snprintf(logPath, sizeof logPath, "%s\\Controls2D.log", g_dir);
    g_log = fopen(logPath, "w");
    plog("Controls2D 1.1 loaded");
    g_frames = g_cuts = g_reinits = 0;
    g_lastFlip = -1;
    load_config();
    g_enabled = cfg_enabled;
    return 1;
}

int __stdcall Update(void)
{
    if (g_disabled) return 0;
    if (!g_inited) {
        g_inited = 1;
        if (!verify_and_install()) { g_disabled = 1; return 0; }
    }
    DWORD pid = 0;
    GetWindowThreadProcessId(GetForegroundWindow(), &pid);
    int down = pid == GetCurrentProcessId() && (GetAsyncKeyState(cfg_key) & 0x8000);
    if (down && !g_keyWasDown) {
        g_enabled = !g_enabled;
        plog("toggle: 2D controls %s", g_enabled ? "ON" : "OFF (SH4 original)");
        if (cfg_beep) MessageBeep(g_enabled ? MB_ICONASTERISK : MB_OK);
        ops_set(g_enabled);
    }
    g_keyWasDown = down;
    return 0;
}

int __stdcall UnloadPlugin(void)
{
    uninstall();
    plog("unloaded after %ld frames, %ld cuts, %ld controller re-inits", g_frames, g_cuts, g_reinits);
    if (g_log) { fclose(g_log); g_log = NULL; }
    g_inited = 0; g_disabled = 0; g_havePrev = 0; g_latched = 0; g_opsOk = 0; g_opsOn = 0;
    return 1;
}
