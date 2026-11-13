#ifndef BLUEWAKE_COMPOSITE_SHADOW_TRACE_H
#define BLUEWAKE_COMPOSITE_SHADOW_TRACE_H

/* The guest memory accesses of one region, for the shadow-batch limit study
 * (docs/planning/2026-11-03-parallel_guest_execution/TECH_PLAN.md).
 *
 * Built only with BLUEWAKE_SHADOW_TRACE. The host switches a region on at
 * fpcLnIt_MethodCall's entry and reads it at the return into cNdIt_Method,
 * through bluewake_composite_shadow_trace(). Loads are logged by cache line
 * through a small direct-mapped filter (a region's distinct lines, not its
 * load count); stores by address and size, in order. Flags mark what a shadow
 * run could not keep private: the hardware, an interpreter fallback, a
 * timebase read. Accesses outside MEM1 (the REL modules' alias storage) are
 * logged like the others and counted, for the side buffer's cost.
 *
 * No identifier here may be `ctx`: the chunks define it as a macro. */

#include "core/cpu.h"
#include <string.h>

enum {
    BW_TRACE_READS = 1u << 16,
    BW_TRACE_WRITES = 1u << 17,
    BW_TRACE_FILTER = 1u << 10,
    BW_TRACE_FLAG_READ_OVERFLOW = 1u << 0,
    BW_TRACE_FLAG_WRITE_OVERFLOW = 1u << 1,
    BW_TRACE_FLAG_HARDWARE_READ = 1u << 2,
    BW_TRACE_FLAG_HARDWARE_WRITE = 1u << 3,
    BW_TRACE_FLAG_ALIAS = 1u << 4,
    BW_TRACE_FLAG_FALLBACK = 1u << 5,
    BW_TRACE_FLAG_TIMER = 1u << 6,
    BW_TRACE_FLAG_PSQ_FALLBACK = 1u << 7,
    BW_TRACE_FLAG_DCBZ = 1u << 8,
    BW_TRACE_FLAG_INTERRUPT = 1u << 9   /* set by the host: a delivery inside the region */
};

typedef struct BwShadowTrace {
    u32 version;
    u32 on;
    u32 read_count;
    u32 write_count;
    u32 flags;
    u32 alias_accesses;
    u32 hardware_accesses;
    u32 reserved;
    u32 read_lines[BW_TRACE_READS];
    u32 write_addr[BW_TRACE_WRITES];
    u8 write_size[BW_TRACE_WRITES];
    u32 filter[BW_TRACE_FILTER];
} BwShadowTrace;

extern BwShadowTrace bw_shadow_trace;

static inline void bw_trace_reset(void) {
    bw_shadow_trace.read_count = 0u;
    bw_shadow_trace.write_count = 0u;
    bw_shadow_trace.flags = 0u;
    bw_shadow_trace.alias_accesses = 0u;
    bw_shadow_trace.hardware_accesses = 0u;
    memset(bw_shadow_trace.filter, 0xFF, sizeof bw_shadow_trace.filter);
}

static inline void bw_trace_lines(u32 addr, u32 size) {
    u32 line = addr >> 6;
    const u32 last = (addr + size - 1u) >> 6;
    for (; line <= last; ++line) {
        const u32 slot = line & (BW_TRACE_FILTER - 1u);
        if (bw_shadow_trace.filter[slot] == line)
            continue;
        bw_shadow_trace.filter[slot] = line;
        if (bw_shadow_trace.read_count < BW_TRACE_READS)
            bw_shadow_trace.read_lines[bw_shadow_trace.read_count++] = line;
        else
            bw_shadow_trace.flags |= BW_TRACE_FLAG_READ_OVERFLOW;
    }
}

static inline void bw_trace_read(u32 addr, u32 size) {
    if (__builtin_expect(bw_shadow_trace.on == 0u, 1))
        return;
    bw_trace_lines(addr, size);
}

static inline void bw_trace_write(u32 addr, u32 size) {
    if (__builtin_expect(bw_shadow_trace.on == 0u, 1))
        return;
    if (bw_shadow_trace.write_count < BW_TRACE_WRITES) {
        bw_shadow_trace.write_addr[bw_shadow_trace.write_count] = addr;
        bw_shadow_trace.write_size[bw_shadow_trace.write_count] = (u8)size;
        bw_shadow_trace.write_count++;
    } else {
        bw_shadow_trace.flags |= BW_TRACE_FLAG_WRITE_OVERFLOW;
    }
}

static inline void bw_trace_flag(u32 flag) {
    if (bw_shadow_trace.on != 0u)
        bw_shadow_trace.flags |= flag;
}

/* An access that left the inline MEM1 path: the hardware (counted, flagged,
 * not logged: a shadow would abort there), or MEM1 for another reason, or
 * the alias storage (logged like MEM1, and counted). */
static inline void bw_trace_slow(const CPUState* cpu, u32 addr, u32 size, bool store) {
    if (bw_shadow_trace.on == 0u)
        return;
    if ((addr & 0x40000000u) != 0u && (addr & 0xF8000000u) == 0xC8000000u) {
        bw_shadow_trace.hardware_accesses++;
        bw_shadow_trace.flags |= store ? BW_TRACE_FLAG_HARDWARE_WRITE : BW_TRACE_FLAG_HARDWARE_READ;
        return;
    }
    if ((u32)((addr & ~0x40000000u) - GC_RAM_BASE) >= cpu->ram_size) {
        bw_shadow_trace.alias_accesses++;
        bw_shadow_trace.flags |= BW_TRACE_FLAG_ALIAS;
    }
    if (store)
        bw_trace_write(addr, size);
    else
        bw_trace_lines(addr, size);
}

#endif
