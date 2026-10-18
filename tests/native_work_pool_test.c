#include "native_work_pool.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(_WIN32)
typedef unsigned visit_count;
#define STORE_VISIT(value, count) (*(value) = (count))
#define LOAD_VISIT(value) (*(value))
#define INCREMENT_VISIT(value) (++*(value))
#else
#include <stdatomic.h>
typedef atomic_uint visit_count;
#define STORE_VISIT(value, count) \
    atomic_store_explicit((value), (count), memory_order_relaxed)
#define LOAD_VISIT(value) \
    atomic_load_explicit((value), memory_order_relaxed)
#define INCREMENT_VISIT(value) \
    atomic_fetch_add_explicit((value), 1u, memory_order_relaxed)
#endif

enum { MAX_ITEMS = 4099, ITERATIONS = 1000 };

struct work_context {
    visit_count visits[MAX_ITEMS];
    uint32_t output[MAX_ITEMS];
    uint32_t salt;
};

static void fill_range(void *opaque, size_t first, size_t end)
{
    struct work_context *context = opaque;
    for (size_t index = first; index < end; ++index) {
        INCREMENT_VISIT(&context->visits[index]);
        context->output[index] = (uint32_t)index ^ context->salt;
    }
}

static int run_case(struct work_context *context, size_t count,
                    size_t grain, uint32_t salt)
{
    for (size_t index = 0; index < MAX_ITEMS; ++index) {
        STORE_VISIT(&context->visits[index], 0u);
        context->output[index] = UINT32_C(0xdeadbeef);
    }
    context->salt = salt;

    bluewake_parallel_range(count, grain, fill_range, context);

    for (size_t index = 0; index < count; ++index) {
        unsigned visits = LOAD_VISIT(&context->visits[index]);
        if (visits != 1u || context->output[index] != ((uint32_t)index ^ salt)) {
            fprintf(stderr, "index %zu: visits=%u output=%08x\n",
                    index, visits, context->output[index]);
            return 1;
        }
    }
    for (size_t index = count; index < MAX_ITEMS; ++index) {
        if (LOAD_VISIT(&context->visits[index]) != 0u ||
            context->output[index] != UINT32_C(0xdeadbeef)) {
            fprintf(stderr, "sentinel changed at index %zu\n", index);
            return 1;
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    unsigned expected_workers = argc == 2 ? (unsigned)strtoul(argv[1], NULL, 10) : 0;
    struct work_context *context = calloc(1, sizeof(*context));
    if (!context) {
        fputs("allocation failed\n", stderr);
        return 1;
    }

    unsigned long long batches_before = bluewake_parallel_batches();
    if (run_case(context, 0, 1, 1) ||
        run_case(context, 17, 256, 2) ||
        run_case(context, MAX_ITEMS, 1, 3)) {
        free(context);
        return 1;
    }
    for (unsigned iteration = 0; iteration < ITERATIONS; ++iteration) {
        size_t count = 257u + iteration % (MAX_ITEMS - 256u);
        if (run_case(context, count, 1, UINT32_C(0x9e3779b9) ^ iteration)) {
            free(context);
            return 1;
        }
    }

    unsigned long long batches_after = bluewake_parallel_batches();
    if ((expected_workers == 0 && batches_after != batches_before) ||
        (expected_workers != 0 && batches_after <= batches_before)) {
        fprintf(stderr, "unexpected batch count: %llu -> %llu\n",
                batches_before, batches_after);
        free(context);
        return 1;
    }

    free(context);
    return 0;
}
