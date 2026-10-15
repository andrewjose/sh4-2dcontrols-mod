/* Runs Controls2D against the real SILENT_HILL_4.exe image mapped at 0x400000
 * in a 32-bit Linux process. Each "frame" calls the installed stub, which runs
 * the plugin and then the game's REAL input builder (0x52F260); the test reads
 * the direction the game itself computes (input+0x70 = 0x10A1A70).
 *
 * Build: zig cc -target x86-linux-musl -O1 -I inc -o harness harness.c
 * Run:   ./harness sh4_image.bin      (flat image made with pefile, see README)
 */
#include <windows.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <math.h>
#include <sys/mman.h>
#include <signal.h>
#include <ucontext.h>
static void segv_handler(int sig, siginfo_t *si, void *uc_)
{
    ucontext_t *uc = (ucontext_t *)uc_;
    fprintf(stderr, "\nSIGSEGV at eip=%08x addr=%p esi=%08x edi=%08x eax=%08x ecx=%08x\n", (unsigned)uc->uc_mcontext.gregs[REG_EIP], si->si_addr, (unsigned)uc->uc_mcontext.gregs[REG_ESI], (unsigned)uc->uc_mcontext.gregs[REG_EDI], (unsigned)uc->uc_mcontext.gregs[REG_EAX], (unsigned)uc->uc_mcontext.gregs[REG_ECX]);
    (void)sig; _exit(3);
}
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
#include "../controls2d.c"

#define BASE 0x400000u
#define IMGSZ 0xFE3000u
static BYTE *img = (BYTE *)BASE;
static int key_down;
void GetLocalTime(SYSTEMTIME *t) { memset(t, 0, sizeof *t); }
SIZE_T VirtualQuery(const void *p, MEMORY_BASIC_INFORMATION *m, SIZE_T n)
{
    (void)n; memset(m, 0, sizeof *m);
    if ((BYTE *)p >= img && (BYTE *)p < img + IMGSZ) {
        m->BaseAddress = img; m->RegionSize = IMGSZ; m->State = MEM_COMMIT; m->Protect = 0x40; return sizeof *m;
    }
    return 0;
}
BOOL VirtualProtect(void *a, SIZE_T n, DWORD p, DWORD *o) { (void)a; (void)n; (void)p; *o = 0x20; return 1; }
LPVOID VirtualAlloc(LPVOID a, SIZE_T n, DWORD t, DWORD p)
{
    (void)a; (void)t; (void)p;
    void *m = mmap(NULL, n, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    return m == MAP_FAILED ? NULL : m;
}
BOOL VirtualFree(LPVOID a, SIZE_T n, DWORD t) { (void)n; (void)t; munmap(a, 64); return 1; }
BOOL FlushInstructionCache(HANDLE h, const void *a, SIZE_T n) { (void)h; (void)a; (void)n; return 1; }
HANDLE GetCurrentProcess(void) { return (HANDLE)-1; }
DWORD GetCurrentProcessId(void) { return 1234; }
DWORD GetPrivateProfileStringA(LPCSTR sec, LPCSTR key, LPCSTR def, char *out, DWORD n, LPCSTR path)
{
    (void)sec; FILE *f = fopen(path, "rb"); char line[512]; size_t kl = strlen(key);
    snprintf(out, n, "%s", def);
    if (!f) return (DWORD)strlen(out);
    while (fgets(line, sizeof line, f))
        if (!strncmp(line, key, kl) && line[kl] == '=') {
            char *v = line + kl + 1; v[strcspn(v, "\r\n")] = 0; snprintf(out, n, "%s", v); break;
        }
    fclose(f); return (DWORD)strlen(out);
}
DWORD GetFileAttributesA(LPCSTR p) { FILE *f = fopen(p, "rb"); if (!f) return INVALID_FILE_ATTRIBUTES; fclose(f); return 0x80; }
DWORD GetModuleFileNameA(HMODULE h, char *b, DWORD n) { snprintf(b, n, h ? "plugins\\Controls2D.dll" : "SILENT_HILL_4.exe"); return (DWORD)strlen(b); }
BOOL GetModuleHandleExA(DWORD f, LPCSTR a, HMODULE *m) { (void)f; (void)a; *m = (HMODULE)1; return 1; }
HMODULE GetModuleHandleA(LPCSTR n) { (void)n; return img; }
BOOL QueryPerformanceFrequency(LARGE_INTEGER *l) { l->QuadPart = 10000000; return 1; }
BOOL QueryPerformanceCounter(LARGE_INTEGER *l) { l->QuadPart = 0; return 1; }
HWND GetForegroundWindow(void) { return (HWND)7; }
DWORD GetWindowThreadProcessId(HWND w, DWORD *pid) { (void)w; *pid = 1234; return 1; }
short GetAsyncKeyState(int k) { return (k == VK_F3 && key_down) ? (short)0x8000 : 0; }
BOOL MessageBeep(UINT t) { (void)t; return 1; }

/* ---- scene setup ---- */
static float camobj[0xC0];             /* fake camera matrix object (0x300 bytes) */
static float *F(DWORD va) { return (float *)(uintptr_t)va; }
static int *I(DWORD va) { return (int *)(uintptr_t)va; }
static void camera(float yawDeg)       /* forward vector = (sin, 0, cos) */
{
    float r = yawDeg * PI / 180.0f;
    camobj[8] = sinf(r); camobj[9] = 0; camobj[10] = cosf(r); camobj[11] = 0;
}
static void stick(float screenDeg, float mag) /* 0 = up, 90 = right */
{
    float r = screenDeg * PI / 180.0f;
    *F(0x1236C44) = mag * sinf(r);     /* LX */
    *F(0x1236C48) = -mag * cosf(r);    /* LY: builder uses atan2(LX, -LY) */
}
static float frame(void)               /* run plugin + real builder, return game's target yaw in degrees */
{
    typedef void *(*Fn)(void);
    void *r = ((Fn)g_stub)();
    if (r != (void *)0x10A1A00) printf("     builder returned %p\n", r);
    Update();
    return *F(0x10A1A70) * 180.0f / PI;
}
/* what 0x534590 does with the builder's output in third person: yaw = input+8 */
static float walkdir(void) { return *F(0x10A1A08) * 180.0f / PI; }
static float step_walk(void) { frame(); *F(0x10A0FA4) = *F(0x10A1A08); return walkdir(); }
static float angdiff(float a, float b) { float d = fmodf(a - b + 540.0f, 360.0f) - 180.0f; return d; }
static int fails;
#define CHECK(c, ...) do { if (c) printf("  ok   " __VA_ARGS__); else { printf("  FAIL " __VA_ARGS__); fails++; } printf("\n"); } while (0)
static int near_deg(float a, float b) { float d = fmodf(fabsf(a - b), 360.0f); return d < 0.5f || d > 359.5f; }

int main(int argc, char **argv)
{
    { struct sigaction sa; memset(&sa,0,sizeof sa); sa.sa_sigaction=segv_handler; sa.sa_flags=SA_SIGINFO; sigaction(SIGSEGV,&sa,0); }
    if (argc < 2) { fprintf(stderr, "usage: %s sh4_image.bin\n", argv[0]); return 2; }
    if (mmap(img, IMGSZ, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) != img) {
        perror("mmap"); return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(img, 1, IMGSZ, f) < 0x1d0000) { fprintf(stderr, "cannot read image\n"); return 2; }
    fclose(f);
    BYTE pristine[5]; memcpy(pristine, img + (VA_HOOK_CALL - BASE), 5);

    /* runtime state the game sets up: player controller, camera, speed scale */
    *I(0xFD5BA0) = 0x10A0F20;
    *I(0x12E4160) = (int)(uintptr_t)camobj;
    *F(0x10A1910) = 1.0f;
    *F(0x10A1918) = 0.0f;              /* game's latched camera yaw */
    remove("plugins\\Controls2D.ini"); remove("plugins\\Controls2D.log");

    LoadPlugin(BASE);
    Update();
    CHECK(g_installed, "all code checks matched the real exe; hook installed");
    BYTE *site = img + (VA_HOOK_CALL - BASE);
    CHECK(site[0] == 0xE8 && (uintptr_t)(VA_HOOK_CALL + 5 + *(int32_t *)(site + 1)) == (uintptr_t)g_stub,
          "0x534B2E now calls the stub");

    puts("1. fixed camera: same as SH4 (up = away from camera)");
    camera(0); stick(0, 1);
    CHECK(near_deg(frame(), 0), "camera 0, stick up -> walk 0 deg");
    stick(90, 1);
    CHECK(near_deg(frame(), 90), "stick right -> walk 90 deg");

    puts("2. camera pans while you walk: direction follows the screen (SH4 kept the old yaw)");
    stick(0, 1);
    for (int d = 0; d <= 60; d += 3) { camera((float)d); frame(); }
    camera(60);
    CHECK(near_deg(frame(), 60), "after a smooth 60 deg pan, stick up -> walk 60 deg (game alone: 0)");

    puts("3. camera cut while holding the stick: keep walking the same way (SH2/SH3)");
    camera(150); /* 90 deg jump in one frame */
    CHECK(near_deg(frame(), 60), "cut to 150 deg: still walking 60 deg");
    camera(155); CHECK(near_deg(frame(), 60), "new camera keeps moving: still held at 60 deg");
    stick(20, 1); CHECK(near_deg(frame(), 80), "stick nudged 20 deg (< 30): steers relative to the old camera -> 80");
    stick(40, 1); CHECK(near_deg(frame(), 195), "stick moved 40 deg (> 30): new camera takes over -> 155+40 = 195");

    puts("4. release after a cut also hands over to the new camera");
    stick(0, 1); camera(155); frame();
    camera(245); CHECK(near_deg(frame(), 155), "cut to 245 while holding: held at 155");
    stick(0, 0); frame();
    stick(0, 1); CHECK(near_deg(frame(), 245), "released and pushed again: 245 (new camera)");

    puts("5. game re-initialises its own yaw (new scene) while holding: treated as a cut");
    *F(0x10A1918) = 1.0f; /* the game's init writes a fresh value */
    CHECK(near_deg(frame(), 245), "held through the re-init");
    CHECK(g_reinits == 1, "re-init detected (%ld)", g_reinits);

    puts("6. scene stick inversion is still honoured");
    *I(0x10A19DC) = 1; stick(0, 1); camera(0); frame(); stick(0, 0); frame(); stick(0, 1);
    CHECK(near_deg(frame(), 180), "inverted scene: stick up -> 180 deg, exactly as SH4 does it");
    *I(0x10A19DC) = 0;

    puts("7. F3 toggles back to SH4's original latched yaw");
    stick(0, 0); frame();
    *F(0x10A1918) = 0.5f; frame(); /* game writes its own value again */
    key_down = 1; frame(); key_down = 0;
    camera(90); stick(0, 1);
    float t = frame();
    CHECK(!g_enabled && near_deg(t, 0.5f * 180.0f / PI), "off: game uses its own latched yaw (%.1f deg), camera ignored", t);
    key_down = 1; frame(); key_down = 0; frame();
    CHECK(g_enabled && near_deg(frame(), 90), "on again: follows the camera (90 deg)");

    puts("8. hold_on_cut=0 switches instantly on cuts");
    UnloadPlugin();
    CHECK(!memcmp(img + (VA_HOOK_CALL - BASE), pristine, 5), "unload restored the original call");
    FILE *ini = fopen("plugins\\Controls2D.ini", "wb"); fputs("[Controls2D]\nhold_on_cut=0\n", ini); fclose(ini);
    LoadPlugin(BASE); Update();
    camera(0); stick(0, 1); frame(); camera(90);
    CHECK(near_deg(frame(), 90), "cut with hold off: walks toward the new camera's 90 deg");
    UnloadPlugin(); remove("plugins\\Controls2D.ini");

    puts("10. turning: SH4 steers in an arc, snap_turn points Henry straight at the stick");
    {
        LoadPlugin(BASE); Update();
        CHECK(g_opsOk && g_opsOn, "turning constants matched the exe and are redirected");
        CHECK(*(DWORD *)(uintptr_t)(0x52FCF9 + 2) == (DWORD)(uintptr_t)&g_turnRate &&
              *(DWORD *)(uintptr_t)(0x535062 + 2) == (DWORD)(uintptr_t)&g_faceRate, "operands point at the plugin's values");
        CHECK(fabsf(g_faceRate - 1440.0f * PI / 180.0f) < 1e-4f, "body facing speed %.1f rad/s (SH4: 12)", g_faceRate);
        camera(0); *F(0x10A1918) = 0; *F(0x10A0FA4) = 0; *F(0x10A1924) = 0;
        stick(0, 1); for (int i = 0; i < 40; i++) step_walk();
        printf("     walking up at full speed: dir %.1f, speed %.2f\n", walkdir(), *F(0x10A191C));
        stick(90, 1);
        float d1 = step_walk();
        CHECK(near_deg(d1, 90), "stick right: walking 90 deg on the very next frame (%.1f)", d1);
        stick(270, 1);
        float d2 = step_walk();
        CHECK(near_deg(d2, 270), "stick flipped left: walking 270 deg next frame (%.1f)", d2);

        key_down = 1; frame(); key_down = 0;     /* F3: SH4's original */
        CHECK(!g_enabled && !g_opsOn && *(DWORD *)(uintptr_t)(0x52FCF9 + 2) == 0x5B7ED8u, "F3 off: original constants back");
        *F(0x10A1918) = 0; stick(0, 1); for (int i = 0; i < 40; i++) step_walk();
        stick(90, 1);
        float o[12]; for (int i = 0; i < 12; i++) o[i] = step_walk();
        printf("     SH4 original, stick up -> right while walking:");
        for (int i = 0; i < 12; i++) printf(" %.0f", o[i]);
        printf("\n");
        CHECK(o[0] > 5 && o[0] < 20 && !near_deg(o[5], 90) && near_deg(o[11], 90),
              "original turns ~12 deg per frame (360 deg/s) and needs ~8 frames for 90 deg");
        key_down = 1; frame(); key_down = 0; frame();
        CHECK(g_enabled && g_opsOn, "F3 on again: snap turning back");

        /* steep camera: SH4's second steering stage */
        *F(0x10A1910) = 0.8f; stick(0, 1); for (int i = 0; i < 40; i++) step_walk();
        stick(90, 1);
        CHECK(near_deg(step_walk(), 90), "steep camera (0.8): still turns straight to 90");
        key_down = 1; frame(); key_down = 0;
        *F(0x10A1918) = 0; stick(0, 1); for (int i = 0; i < 40; i++) step_walk();
        stick(90, 1); float s1 = step_walk();
        CHECK(s1 < 20, "steep camera, original: %.1f deg after one frame", s1);
        key_down = 1; frame(); key_down = 0; frame();
        *F(0x10A1910) = 1.0f;
        UnloadPlugin();
        CHECK(*(DWORD *)(uintptr_t)(0x52FCF9 + 2) == 0x5B7ED8u && *(DWORD *)(uintptr_t)(0x535062 + 2) == 0x5B8160u &&
              *(DWORD *)(uintptr_t)(0x52F8CE + 2) == 0x5B7DB4u, "unload: all turning constants restored");

        FILE *ini2 = fopen("plugins\\Controls2D.ini", "wb");
        fputs("[Controls2D]\nturn_speed=720\nfacing_speed=0\n", ini2); fclose(ini2);
        LoadPlugin(BASE); Update();
        CHECK(*(DWORD *)(uintptr_t)(0x535062 + 2) == 0x5B8160u, "facing_speed=0 leaves SH4's body turn speed");
        camera(0); *F(0x10A1918) = 0; stick(0, 1); for (int i = 0; i < 40; i++) step_walk();
        stick(90, 1); float t1 = step_walk();
        CHECK(fabsf(t1 - 24) < 1.0f, "turn_speed=720: 24 deg per frame at 30 fps (%.1f)", t1);
        *I(0x5D5248) = 60;                       /* GetFPS() value as a 60 fps patch would set it */
        stick(0, 1); for (int i = 0; i < 80; i++) step_walk();
        stick(90, 1); float t2 = step_walk();
        CHECK(fabsf(t2 - 12) < 1.0f, "same setting at 60 fps: 12 deg per frame, same 720 deg/s (%.1f)", t2);
        *I(0x5D5248) = 30;
        UnloadPlugin(); remove("plugins\\Controls2D.ini");
    }

    puts("9. wrong bytes at the hook site -> refuses");
    BYTE save = img[VA_HOOK_CALL - BASE]; img[VA_HOOK_CALL - BASE] = 0x90;
    LoadPlugin(BASE); Update();
    CHECK(g_disabled && !g_installed, "refused and installed nothing");
    UnloadPlugin(); img[VA_HOOK_CALL - BASE] = save;

    printf("\n%s (%d failure%s)\n", fails ? "FAILED" : "ALL PASSED", fails, fails == 1 ? "" : "s");
    return fails != 0;
}
