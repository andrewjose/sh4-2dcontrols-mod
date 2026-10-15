/* Minimal Win32 shim so fpsfix.c can be unit-tested as a 32-bit Linux binary. */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#define __stdcall
#define WINAPI
typedef uint8_t BYTE; typedef uint16_t WORD; typedef uint32_t DWORD; typedef int32_t LONG;
typedef size_t SIZE_T; typedef void *HMODULE; typedef void *HANDLE; typedef void *HWND; typedef void *LPVOID;
typedef const char *LPCSTR; typedef int BOOL; typedef unsigned int UINT;
typedef union { struct { DWORD LowPart; LONG HighPart; } u; long long QuadPart; } LARGE_INTEGER;
typedef struct { WORD wYear, wMonth, wDayOfWeek, wDay, wHour, wMinute, wSecond, wMilliseconds; } SYSTEMTIME;
typedef struct { void *BaseAddress; void *AllocationBase; DWORD AllocationProtect;
                 SIZE_T RegionSize; DWORD State; DWORD Protect; DWORD Type; } MEMORY_BASIC_INFORMATION;
typedef struct { WORD e_magic; WORD pad[29]; LONG e_lfanew; } IMAGE_DOS_HEADER;
typedef struct { WORD Machine, NumberOfSections; DWORD TimeDateStamp, a, b; WORD c, d; } IMAGE_FILE_HEADER;
typedef struct { WORD Magic; BYTE x[54]; DWORD SizeOfImage; } IMAGE_OPTIONAL_HEADER32;
typedef struct { DWORD Signature; IMAGE_FILE_HEADER FileHeader; IMAGE_OPTIONAL_HEADER32 OptionalHeader; } IMAGE_NT_HEADERS32;
#define MAX_PATH 260
#define MEM_COMMIT 0x1000
#define MEM_RESERVE 0x2000
#define MEM_RELEASE 0x8000
#define PAGE_NOACCESS 0x01
#define PAGE_READWRITE 0x04
#define PAGE_GUARD 0x100
#define PAGE_EXECUTE_READWRITE 0x40
#define INVALID_FILE_ATTRIBUTES ((DWORD)-1)
#define VK_F2 0x71
#define VK_F3 0x72
#define MB_OK 0
#define MB_ICONASTERISK 0x40
#define GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS 4
#define GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT 2
void GetLocalTime(SYSTEMTIME *);
SIZE_T VirtualQuery(const void *, MEMORY_BASIC_INFORMATION *, SIZE_T);
BOOL VirtualProtect(void *, SIZE_T, DWORD, DWORD *);
LPVOID VirtualAlloc(LPVOID, SIZE_T, DWORD, DWORD);
BOOL VirtualFree(LPVOID, SIZE_T, DWORD);
BOOL FlushInstructionCache(HANDLE, const void *, SIZE_T);
HANDLE GetCurrentProcess(void);
DWORD GetCurrentProcessId(void);
DWORD GetPrivateProfileStringA(LPCSTR, LPCSTR, LPCSTR, char *, DWORD, LPCSTR);
DWORD GetFileAttributesA(LPCSTR);
DWORD GetModuleFileNameA(HMODULE, char *, DWORD);
BOOL GetModuleHandleExA(DWORD, LPCSTR, HMODULE *);
HMODULE GetModuleHandleA(LPCSTR);
BOOL QueryPerformanceFrequency(LARGE_INTEGER *);
BOOL QueryPerformanceCounter(LARGE_INTEGER *);
HWND GetForegroundWindow(void);
DWORD GetWindowThreadProcessId(HWND, DWORD *);
short GetAsyncKeyState(int);
BOOL MessageBeep(UINT);
